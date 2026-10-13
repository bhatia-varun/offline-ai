from __future__ import annotations

import hashlib
from pathlib import Path

import chromadb
import requests
from pypdf import PdfReader

from app.llm import complete
from app.settings import CHROMA_PATH, DOCUMENTS_PATH, EMBEDDING_MODEL, GENERAL_MODEL, OLLAMA_BASE_URL

COLLECTION_NAME = "offline_ai_demo_documents"


def _collection():
    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return client.get_or_create_collection(name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"})


def _embed(texts: list[str]) -> list[list[float]]:
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/embed",
        json={"model": EMBEDDING_MODEL, "input": texts},
        timeout=180,
    )
    response.raise_for_status()
    return response.json()["embeddings"]


def _read_document(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    return path.read_text(encoding="utf-8")


def _chunks(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    normalized = " ".join(text.split())
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + size, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = max(end - overlap, start + 1)
    return chunks


def ingest_documents(directory: Path = DOCUMENTS_PATH) -> dict[str, int]:
    collection = _collection()
    files = [path for path in sorted(directory.iterdir()) if path.suffix.lower() in {".md", ".txt", ".pdf"}]
    documents: list[str] = []
    ids: list[str] = []
    metadatas: list[dict[str, str | int]] = []
    for path in files:
        for index, chunk in enumerate(_chunks(_read_document(path))):
            ids.append(hashlib.sha256(f"{path.name}:{index}:{chunk}".encode()).hexdigest()[:24])
            documents.append(chunk)
            metadatas.append({"source": path.name, "chunk": index})
    if documents:
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=_embed(documents))
    return {"files": len(files), "chunks": len(documents), "collection_total": collection.count()}


def answer_question(question: str, top_k: int = 4) -> dict[str, object]:
    collection = _collection()
    if collection.count() == 0:
        raise ValueError("No documents are indexed. Call POST /rag/ingest first.")
    result = collection.query(query_embeddings=_embed([question]), n_results=min(top_k, collection.count()))
    documents = result["documents"][0]
    metadatas = result["metadatas"][0]
    context = "\n\n".join(
        f"[Source: {metadata['source']}, chunk {metadata['chunk']}]\n{document}"
        for document, metadata in zip(documents, metadatas)
    )
    answer = complete(
        GENERAL_MODEL,
        [
            {"role": "system", "content": "Answer only from the supplied context. If absent, say you do not know. Cite source file names."},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
        ],
        temperature=0.1,
    )
    return {
        "answer": answer,
        "sources": sorted({str(metadata["source"]) for metadata in metadatas}),
        "retrieved_chunks": len(documents),
    }
