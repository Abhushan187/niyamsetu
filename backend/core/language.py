# backend/core/language.py
# ─────────────────────────────────────────────────────────
# Language detection and text utilities.
# Called before every query to decide how to handle it.
# Keeps all language logic in one place — nothing else
# needs to know HOW detection works, just the result.
# ─────────────────────────────────────────────────────────

import re


# ── Unicode ranges for Devanagari script ──────────────────
# Marathi is written in Devanagari script
# Unicode block U+0900 to U+097F covers all Devanagari characters
# Any text with enough of these characters is Marathi
DEVANAGARI_PATTERN = re.compile(r'[\u0900-\u097F]')

# If more than this % of characters are Devanagari → classify as Marathi
MARATHI_THRESHOLD = 0.15   # 15% — even mixed text with some Marathi counts


def detect_language(text: str) -> str:
    """
    Detects whether text is English or Marathi.
    Uses Unicode character analysis — no ML model needed.

    How it works:
        Counts Devanagari characters vs total characters.
        If ratio exceeds threshold → Marathi, else → English.

    Args:
        text : the query string from the user

    Returns:
        'marathi' or 'english'

    Examples:
        detect_language("What is this GR about?")           → 'english'
        detect_language("या निर्णयाचा विषय काय आहे?")      → 'marathi'
        detect_language("या GR मध्ये what is the date?")   → 'marathi'
    """
    if not text or not text.strip():
        return "english"   # default to English for empty input

    # Count Devanagari characters in the text
    devanagari_chars = len(DEVANAGARI_PATTERN.findall(text))

    # Count only meaningful characters (ignore spaces, punctuation)
    total_chars = len([c for c in text if c.strip() and not c.isspace()])

    if total_chars == 0:
        return "english"

    ratio = devanagari_chars / total_chars

    return "marathi" if ratio >= MARATHI_THRESHOLD else "english"


def clean_text(text: str) -> str:
    """
    Basic text cleaning before sending to the LLM.
    Removes extra whitespace and normalizes line breaks.

    Args:
        text : raw extracted text from PDF or user input

    Returns:
        Cleaned text string
    """
    if not text:
        return ""

    # Replace multiple spaces with single space
    text = re.sub(r' +', ' ', text)

    # Replace 3+ consecutive newlines with 2 newlines
    # Preserves paragraph breaks but removes excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Strip leading and trailing whitespace
    text = text.strip()

    return text


def truncate_for_context(text: str, max_chars: int = 12000) -> str:
    """
    Truncates text to fit within LLM context window.
    Cuts at a sentence boundary where possible to avoid mid-sentence cuts.

    Args:
        text     : input text to truncate
        max_chars: maximum characters to keep (default 12000)

    Returns:
        Truncated text string
    """
    if len(text) <= max_chars:
        return text

    # Cut at max_chars
    truncated = text[:max_chars]

    # Try to find the last sentence boundary (. ! ?)
    # so we don't cut mid-sentence
    last_boundary = max(
        truncated.rfind('.'),
        truncated.rfind('।'),   # Devanagari full stop
        truncated.rfind('!'),
        truncated.rfind('?'),
    )

    if last_boundary > max_chars * 0.8:
        # Only cut at boundary if it's not too far back
        return truncated[:last_boundary + 1]

    return truncated


def format_chat_history(history: list, context_window: int = 6) -> str:
    """
    Formats previous chat turns into a string for the LLM prompt.
    The LLM reads this to understand conversation context.

    Args:
        history       : list of {"role": "user"/"assistant", "content": str}
        context_window: how many recent turns to include

    Returns:
        Formatted string like:
            User: What is this GR about?
            Assistant: This GR is about transfer policy...
            User: Who signed it?
            Assistant: It was signed by...

    Example:
        history = [
            {"role": "user", "content": "What is this GR about?"},
            {"role": "assistant", "content": "This GR concerns..."},
        ]
        → "User: What is this GR about?\nAssistant: This GR concerns..."
    """
    if not history:
        return ""

    # Keep only the most recent turns to avoid overloading context
    # context_window * 2 because each turn has user + assistant message
    recent = history[-(context_window * 2):]

    lines = []
    for turn in recent:
        role = "User" if turn["role"] == "user" else "Assistant"
        content = turn["content"].strip()

        # Truncate very long assistant responses in history
        # to save context window space for the actual query
        if turn["role"] == "assistant" and len(content) > 500:
            content = content[:500] + "..."

        lines.append(f"{role}: {content}")

    return "\n".join(lines)