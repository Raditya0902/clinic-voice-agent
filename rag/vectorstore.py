import os

import chromadb
from sentence_transformers import SentenceTransformer

CHROMA_PERSIST_DIR = os.environ.get("CHROMA_PERSIST_DIR", "./rag/chroma_db")
COLLECTION_NAME = "clinic_faq"
_EMBED_MODEL = "all-MiniLM-L6-v2"

# Module-level cache — loaded once per process.
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(_EMBED_MODEL)
    return _model


def _get_collection(
    persist_dir: str = CHROMA_PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
) -> chromadb.Collection:
    client = chromadb.PersistentClient(path=persist_dir)
    return client.get_or_create_collection(collection_name)


def query(
    text: str,
    top_k: int = 3,
    persist_dir: str = CHROMA_PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
) -> list[dict]:
    """
    Return the top_k most relevant knowledge-base chunks for a query.

    Each result dict has:
      - text: the chunk content
      - source: the markdown filename it came from
      - distance: L2 distance (lower = more similar)
    """
    model = _get_model()
    collection = _get_collection(persist_dir, collection_name)

    if collection.count() == 0:
        return []

    embedding = model.encode(text).tolist()
    results = collection.query(
        query_embeddings=[embedding],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append(
            {
                "text": doc,
                "source": meta.get("source", ""),
                "distance": round(dist, 4),
            }
        )
    return chunks


def format_context(chunks: list[dict]) -> str:
    """Join retrieved chunks into a single context string for the LLM prompt."""
    return "\n\n".join(c["text"] for c in chunks)
