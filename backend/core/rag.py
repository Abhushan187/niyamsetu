# backend/core/rag.py
# ─────────────────────────────────────────────────────────
# RAG (Retrieval Augmented Generation) query engine.
#
# Flow for every chat message:
#   1. Detect language (English or Marathi)
#   2. Search FAISS for relevant chunks
#   3. Extract citations from chunk metadata
#   4. Build prompt with context + history + query
#   5. Send to LLM via Ollama
#   6. Return answer + citations + timing
#
# Called by:
#   api/query.py → passes user query and chat history here
# ─────────────────────────────────────────────────────────

import sys
import os
import time
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings
from core.vectorstore import search
from core.language import detect_language, format_chat_history, clean_text


def get_llm() -> ChatOllama:
    """
    Creates a ChatOllama instance pointing to local Ollama server.
    temperature=0 means deterministic responses — same question
    gets consistent answers, important for government documents.
    """
    return ChatOllama(
        model=settings.LLM_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=0,
    )


def build_citations(docs: list) -> list:
    """
    Extracts citation information from retrieved document chunks.
    Deduplicates — same file+page combination appears only once.

    Args:
        docs : list of LangChain Document objects from FAISS search

    Returns:
        List of citation dicts:
        [
            {
                "file": "GR_2024_transfer.pdf",
                "page": "4",           ← displayed as human-readable page number
                "preview": "First 200 chars of the chunk..."
            },
            ...
        ]
    """
    citations = []
    seen      = set()   # tracks file+page combos we've already added

    for doc in docs:
        filename = doc.metadata.get("source_file", "Unknown Document")

        # LangChain pages are 0-indexed internally
        # We add 1 so users see "Page 4" instead of "Page 3"
        raw_page = doc.metadata.get("page", None)
        if raw_page is not None:
            page_display = str(int(raw_page) + 1)
        else:
            page_display = "?"

        # Create a unique key for deduplication
        key = f"{filename}_p{page_display}"

        if key not in seen:
            seen.add(key)
            citations.append({
                "file":    filename,
                "page":    page_display,
                # Preview helps user understand why this source was cited
                "preview": doc.page_content[:200].strip(),
            })

    return citations


def build_prompt(
    query: str,
    context: str,
    history_text: str,
    language: str,
) -> str:
    """
    Builds the full prompt sent to the LLM.
    Two versions — English and Marathi — with different instructions.

    The prompt has 4 parts:
        1. Role instruction  → tells LLM what it is
        2. Rules             → how to behave
        3. Conversation history → previous turns for context
        4. Retrieved context → the actual GR text chunks
        5. Current question  → what to answer right now

    Args:
        query        : current user question
        context      : concatenated FAISS chunks (the GR text)
        history_text : formatted previous conversation turns
        language     : 'english' or 'marathi'

    Returns:
        Complete prompt string ready to send to LLM
    """
    if language == "marathi":
        return f"""तुम्ही महाराष्ट्र शासन निर्णय (Government Resolution) तज्ञ आहात.

नियम:
- फक्त खालील संदर्भातून उत्तर द्या
- माहिती नसल्यास सांगा: "हे माहिती दिलेल्या दस्तऐवजात आढळली नाही."
- उत्तर मराठीत द्या
- स्पष्ट आणि संक्षिप्त उत्तर द्या

मागील संवाद:
{history_text if history_text else "नाही"}

शासन निर्णयातील संदर्भ:
{context}

प्रश्न: {query}

उत्तर:"""

    else:
        return f"""You are an expert assistant for Maharashtra Government Resolution (GR) documents.

Rules:
- Answer ONLY from the provided context below
- If the answer is not in the context, say exactly: "This information was not found in the uploaded documents."
- Be concise and precise
- Use bullet points when listing multiple items
- Always refer to specific GR details when available

Previous conversation:
{history_text if history_text else "None"}

Context from GR documents:
{context}

Current question: {query}

Answer:"""


async def query(
    user_query: str,
    chat_history: list,
    top_k: int = None,
    language: str = None,
) -> dict:
    """
    Main RAG pipeline — called for every chat message.

    Args:
        user_query   : the question the user typed
        chat_history : list of previous {"role", "content"} turns
        top_k        : chunks to retrieve (defaults to settings.TOP_K)
        language     : force a language, or None for auto-detect

    Returns dict:
        success      : bool
        answer       : the LLM's response text
        citations    : list of {file, page, preview}
        language     : detected or forced language
        elapsed_sec  : how long the full pipeline took
        query        : the original question (for logging)
    """
    start_time = time.time()

    if top_k is None:
        top_k = settings.TOP_K

    # ── Step 1: Detect language ───────────────────────────
    if language is None:
        language = detect_language(user_query)

    # ── Step 2: Search FAISS ──────────────────────────────
    docs = search(user_query, top_k=top_k)

    # If no docs returned, vector store is not ready
    if not docs:
        elapsed = round(time.time() - start_time, 2)
        return {
            "success":     False,
            "answer":      "⚠️ Vector store is not ready. Please ask admin to embed the GR documents first.",
            "citations":   [],
            "language":    language,
            "elapsed_sec": elapsed,
            "query":       user_query,
        }

    # ── Step 3: Build context string ─────────────────────
    # Join all retrieved chunks into one context block
    # Each chunk separated by a divider so LLM can distinguish them
    context_parts = []
    for i, doc in enumerate(docs, 1):
        fname = doc.metadata.get("source_file", "Unknown")
        page  = doc.metadata.get("page", "?")
        # Label each chunk with its source for better LLM grounding
        context_parts.append(
            f"[Source {i}: {fname}, Page {page}]\n{doc.page_content}"
        )
    context = "\n\n---\n\n".join(context_parts)

    # ── Step 4: Extract citations ─────────────────────────
    citations = build_citations(docs)

    # ── Step 5: Format history ────────────────────────────
    history_text = format_chat_history(
        chat_history,
        context_window=settings.CONTEXT_WINDOW,
    )

    # ── Step 6: Build prompt ──────────────────────────────
    prompt = build_prompt(
        query=user_query,
        context=context,
        history_text=history_text,
        language=language,
    )

    # ── Step 7: Call LLM ──────────────────────────────────
    try:
        llm      = get_llm()
        response = llm.invoke([HumanMessage(content=prompt)])
        answer   = response.content.strip()

    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        return {
            "success":     False,
            "answer":      f"⚠️ LLM error: {str(e)}. Is Ollama running with {settings.LLM_MODEL}?",
            "citations":   citations,
            "language":    language,
            "elapsed_sec": elapsed,
            "query":       user_query,
        }

    elapsed = round(time.time() - start_time, 2)

    return {
        "success":     True,
        "answer":      answer,
        "citations":   citations,
        "language":    language,
        "elapsed_sec": elapsed,
        "query":       user_query,
    }