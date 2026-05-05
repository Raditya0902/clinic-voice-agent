"""
Ingest clinic knowledge markdown files into ChromaDB.

Run once (or re-run to update):
    python -m rag.ingestion
"""
import os
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from rag.vectorstore import CHROMA_PERSIST_DIR, COLLECTION_NAME, _EMBED_MODEL

KNOWLEDGE_DIR = Path(__file__).parent / "clinic_knowledge"


def _chunk_markdown(content: str, min_len: int = 20) -> list[str]:
    """Split on blank lines; drop chunks that are too short to be useful."""
    return [c.strip() for c in content.split("\n\n") if len(c.strip()) >= min_len]


def ingest_clinic_knowledge(
    knowledge_dir: Path = KNOWLEDGE_DIR,
    persist_dir: str = CHROMA_PERSIST_DIR,
    collection_name: str = COLLECTION_NAME,
) -> int:
    """
    Chunk and embed all .md files in knowledge_dir, upsert into ChromaDB.
    Returns the total number of chunks stored.
    """
    model = SentenceTransformer(_EMBED_MODEL)
    client = chromadb.PersistentClient(path=persist_dir)
    collection = client.get_or_create_collection(collection_name)

    total = 0
    for md_file in sorted(Path(knowledge_dir).glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        chunks = _chunk_markdown(content)

        for i, chunk in enumerate(chunks):
            doc_id = f"{md_file.name}_{i}"
            embedding = model.encode(chunk).tolist()
            collection.upsert(
                documents=[chunk],
                embeddings=[embedding],
                ids=[doc_id],
                metadatas=[{"source": md_file.name}],
            )
            total += 1

        print(f"  {md_file.name}: {len(chunks)} chunks")

    print(f"Ingested {total} total chunks into '{collection_name}' ({persist_dir})")
    return total


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    ingest_clinic_knowledge()
