# backend/core/vectorstore.py
# ─────────────────────────────────────────────────────────
# FAISS vector store — embedding and search.
#
# Two main operations:
#   1. embed_all_pdfs()  → reads PDFs, creates embeddings, saves FAISS index
#   2. search()          → finds the most relevant chunks for a query
#
# Called by:
#   api/embed.py  → triggers embed_all_pdfs()
#   core/rag.py   → calls search() before sending to LLM
# ─────────────────────────────────────────────────────────

import sys
import os
from pathlib import Path
from typing import Optional

# LangChain PDF loader — reads PDF pages into Document objects
from langchain_community.document_loaders import PyPDFLoader

# Splits large documents into smaller overlapping chunks
from langchain_text_splitters import RecursiveCharacterTextSplitter

# FAISS vector store wrapper from LangChain
from langchain_community.vectorstores import FAISS

# Ollama embeddings — converts text to vectors using nomic-embed-text
from langchain_ollama import OllamaEmbeddings

# LangChain Document type — represents one chunk of text with metadata
from langchain_core.documents import Document

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings


# ── Module-level cache ────────────────────────────────────
# The FAISS index is loaded once and kept in memory.
# Without this, every query would reload the index from disk
# which takes 5-10 seconds and kills performance.
_vector_store: Optional[FAISS] = None


def get_embeddings() -> OllamaEmbeddings:
    """
    Creates an Ollama embeddings instance.
    Uses nomic-embed-text model — good multilingual support.
    Called internally — not used outside this file.
    """
    return OllamaEmbeddings(
        model=settings.EMBEDDING_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
    )


def is_ready() -> bool:
    """
    Checks if the FAISS index exists on disk.
    Used by the frontend to show "Vector Store Ready" status.

    Returns:
        True if index.faiss exists, False otherwise
    """
    index_file = settings.VECTORSTORE_PATH / "index.faiss"
    return index_file.exists()


def load_store() -> Optional[FAISS]:
    """
    Loads FAISS index from disk into memory.
    Uses module-level cache so it only loads once per session.

    Returns:
        FAISS instance if index exists, None otherwise
    """
    global _vector_store

    # Return cached version if already loaded
    if _vector_store is not None:
        return _vector_store

    # Check if index exists on disk
    if not is_ready():
        return None

    try:
        embeddings = get_embeddings()
        _vector_store = FAISS.load_local(
            str(settings.VECTORSTORE_PATH),
            embeddings,
            # This flag is required by LangChain for security
            # We set it True because we trust our own saved index
            allow_dangerous_deserialization=True,
        )
        return _vector_store
    except Exception as e:
        print(f"❌ Failed to load vector store: {e}")
        return None


def clear_cache():
    """
    Clears the in-memory cache.
    Called after embed_all_pdfs() so the next query
    loads the fresh index instead of the old cached one.
    """
    global _vector_store
    _vector_store = None


async def embed_all_pdfs(progress_callback=None) -> dict:
    """
    Main embedding function — processes all PDFs in GRDOCS folder.

    Steps:
        1. Find all PDFs in grdocs/ folder
        2. Load each PDF into pages using PyPDFLoader
        3. Split pages into chunks using RecursiveCharacterTextSplitter
        4. Generate embeddings for each chunk via Ollama
        5. Save FAISS index to disk
        6. Clear cache so next query uses fresh index

    Args:
        progress_callback : optional function called with (filename, current, total)
                           Used to stream progress to the frontend

    Returns:
        dict with success, message, total_chunks, failed_files
    """
    # Find all PDFs
    pdf_files = list(settings.GRDOCS_PATH.glob("*.pdf"))

    if not pdf_files:
        return {
            "success": False,
            "message": "No PDF files found in grdocs folder. Upload some GRs first.",
            "total_chunks": 0,
            "failed_files": [],
        }

    all_documents = []
    failed_files   = []

    # ── Step 1 & 2: Load each PDF ─────────────────────────
    for i, pdf_path in enumerate(pdf_files):
        if progress_callback:
            progress_callback(pdf_path.name, i + 1, len(pdf_files))

        try:
            from core.ocr import load_pdf_with_ocr_fallback
            pages = load_pdf_with_ocr_fallback(str(pdf_path))

            # Add filename to each page's metadata
            # This is what powers citations later —
            # we know which file and which page each chunk came from
            for page in pages:
                page.metadata["source_file"] = pdf_path.name

            all_documents.extend(pages)
            print(f"  ✅ Loaded: {pdf_path.name} ({len(pages)} pages)")

        except Exception as e:
            failed_files.append(pdf_path.name)
            print(f"  ❌ Failed to load {pdf_path.name}: {e}")

    if not all_documents:
        return {
            "success": False,
            "message": "All PDFs failed to load. Check if files are valid PDFs.",
            "total_chunks": 0,
            "failed_files": failed_files,
        }

    # ── Step 3: Split into chunks ─────────────────────────
    # RecursiveCharacterTextSplitter tries to split at:
    # paragraphs → sentences → words → characters (in that order)
    # This preserves meaning better than hard character cuts
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,         # max characters per chunk
        chunk_overlap=settings.CHUNK_OVERLAP,   # overlap prevents losing context at boundaries
        separators=["\n\n", "\n", "।", ". ", " ", ""],  # । is Devanagari sentence end
    )

    chunks = splitter.split_documents(all_documents)
    print(f"  📄 Total chunks created: {len(chunks)}")

    # ── Step 4 & 5: Embed and save ────────────────────────
    try:
        embeddings = get_embeddings()

        # FAISS.from_documents() does two things:
        #   - calls Ollama to get vector for each chunk
        #   - stores all vectors in a FAISS index
        # This is the slow step — takes 2-5 min depending on doc count
        print("  🔄 Generating embeddings via Ollama (this takes a few minutes)...")
        vector_store = FAISS.from_documents(chunks, embeddings)

        # Save index to disk so it survives app restarts
        settings.VECTORSTORE_PATH.mkdir(parents=True, exist_ok=True)
        vector_store.save_local(str(settings.VECTORSTORE_PATH))
        print(f"  💾 Vector store saved to: {settings.VECTORSTORE_PATH}")

        # ── Step 6: Clear cache ───────────────────────────
        # Force next search() call to reload fresh index
        clear_cache()

        msg = f"Successfully embedded {len(pdf_files) - len(failed_files)} PDFs — {len(chunks)} chunks created."
        if failed_files:
            msg += f" Failed: {', '.join(failed_files)}"

        return {
            "success":      True,
            "message":      msg,
            "total_chunks": len(chunks),
            "failed_files": failed_files,
        }

    except Exception as e:
        return {
            "success":      False,
            "message":      f"Embedding failed: {str(e)}. Is Ollama running?",
            "total_chunks": 0,
            "failed_files": failed_files,
        }


def search(query: str, top_k: int = None) -> list[Document]:
    """
    Searches the FAISS index for chunks most relevant to the query.
    Uses FAISS built-in similarity search — no manual vector loops.

    Args:
        query : the user's question
        top_k : number of chunks to retrieve (defaults to settings.TOP_K)

    Returns:
        List of Document objects with page_content and metadata
        Empty list if vector store not ready or search fails

    Each Document looks like:
        Document(
            page_content = "...relevant text from the GR...",
            metadata = {
                "source_file": "GR_2024_transfer.pdf",
                "page": 3,
            }
        )
    """
    if top_k is None:
        top_k = settings.TOP_K

    db = load_store()

    if db is None:
        # Vector store not ready — return empty list
        # rag.py handles this gracefully
        return []

    try:
        docs = db.similarity_search(query, k=top_k)
        return docs
    except Exception as e:
        print(f"❌ Search failed: {e}")
        return []


def cosine_search_with_scores(query: str, top_k: int = 5) -> list[tuple]:
    """
    Like search() but also returns similarity scores.
    Used on the Search page to show relevance scores to users.

    Returns:
        List of (Document, score) tuples
        Score is between 0 and 1 — higher means more relevant
        (FAISS returns L2 distance, we convert to similarity)
    """
    db = load_store()

    if db is None:
        return []

    try:
        # Returns list of (Document, distance) tuples
        # Lower distance = more similar in FAISS
        results_with_scores = db.similarity_search_with_score(query, k=top_k)

        # Convert L2 distance to similarity score between 0 and 1
        # Formula: similarity = 1 / (1 + distance)
        converted = []
        for doc, distance in results_with_scores:
            similarity = round(1 / (1 + float(distance)), 4)
            converted.append((doc, similarity))

        return converted

    except Exception as e:
        print(f"❌ Scored search failed: {e}")
        return []