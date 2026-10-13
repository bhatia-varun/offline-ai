from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")

LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "local-demo-key")
GENERAL_MODEL = os.getenv("GENERAL_MODEL", "general")
AGENT_MODEL = os.getenv("AGENT_MODEL", "agent")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
CHROMA_PATH = BASE_DIR / os.getenv("CHROMA_PATH", "rag/chroma")
DOCUMENTS_PATH = BASE_DIR / "rag" / "documents"
