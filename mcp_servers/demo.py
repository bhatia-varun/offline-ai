"""Read-only, offline MCP tools for the demo (stdio transport)."""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = ROOT / "rag" / "documents"
server = FastMCP("offline-demo-tools")


@server.tool()
def list_demo_documents() -> dict[str, list[str]]:
    """List the names of demo documents, without reading their contents."""
    return {"documents": sorted(p.name for p in DOCUMENTS.iterdir() if p.is_file() and p.suffix.lower() in {".md", ".txt", ".pdf"})}


@server.tool()
def get_demo_stack_status() -> dict[str, str]:
    """Report the configured local stack components, without running commands or accessing the network."""
    return {"gateway": "LiteLLM :4000", "api": "FastAPI :8000", "ui": "Streamlit :8501", "runtime": "Ollama :11434", "status": "configured; not a live health check"}


if __name__ == "__main__":
    server.run(transport="stdio")
