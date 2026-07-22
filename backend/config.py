# backend/config.py
# ─────────────────────────────────────────────────────────
# Central configuration for Niyamsetu backend.
# All settings are loaded from the .env file.
# Every other module imports from here — never hardcode values elsewhere.
# ─────────────────────────────────────────────────────────

from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # ── MongoDB ───────────────────────────────────────────
    # Connection string from Atlas (stored in .env, never hardcoded)
    MONGODB_URL: str
    # Name of the database inside your Atlas cluster
    DATABASE_NAME: str = "niyamsetu"

    # ── JWT Authentication ────────────────────────────────
    # Secret key used to sign tokens — anyone with this can forge tokens
    # So it stays in .env and never touches GitHub
    JWT_SECRET: str
    # How many hours before a login token expires (user gets logged out)
    JWT_EXPIRE_HOURS: int = 24

    # ── Ollama (local LLM) ────────────────────────────────
    # Where Ollama is running — always localhost for on-premise
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    # Model used to generate embeddings (converts text to vectors)
    EMBEDDING_MODEL: str = "nomic-embed-text"
    # Model used to generate answers (the actual LLM)
    LLM_MODEL: str = "phi4-mini"

    # ── RAG settings ──────────────────────────────────────
    # How many characters per chunk when splitting PDFs
    CHUNK_SIZE: int = 800
    # How many characters overlap between chunks (prevents cutting mid-sentence)
    CHUNK_OVERLAP: int = 150
    # How many chunks to retrieve per query
    TOP_K: int = 3
    # How many previous chat turns to include for context
    CONTEXT_WINDOW: int = 6

    # ── Local file storage ────────────────────────────────
    # Base data directory — relative to backend/ folder
    DATA_DIR: str = "./data"

    # ── Computed paths (derived from DATA_DIR) ────────────
    # These are properties, not .env variables
    # They give you Path objects you can use directly in code
    @property
    def GRDOCS_PATH(self) -> Path:
        # Where uploaded GR PDFs are stored
        return Path(self.DATA_DIR) / "grdocs"

    @property
    def VECTORSTORE_PATH(self) -> Path:
        # Where FAISS index files are saved
        return Path(self.DATA_DIR) / "vectorstore"

    @property
    def SUMMARIES_PATH(self) -> Path:
        # Where generated summary files are saved
        return Path(self.DATA_DIR) / "summaries"

    class Config:
        # Tells pydantic to read values from the .env file automatically
        env_file = ".env"
        # If a variable is in .env but not defined above, ignore it
        extra = "ignore"


# ── Single instance used across the entire app ────────────
# Every file does: from config import settings
# Then uses: settings.LLM_MODEL, settings.MONGODB_URL etc.
settings = Settings()

# ── Ensure data directories exist on startup ──────────────
# Creates the folders if they don't exist yet
# exist_ok=True means no error if folder already exists
settings.GRDOCS_PATH.mkdir(parents=True, exist_ok=True)
settings.VECTORSTORE_PATH.mkdir(parents=True, exist_ok=True)
settings.SUMMARIES_PATH.mkdir(parents=True, exist_ok=True)