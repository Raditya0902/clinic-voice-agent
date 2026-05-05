"""Tests for Phase 2: RAG ingestion and retrieval."""
import pytest
from pathlib import Path


KNOWLEDGE_DIR = Path(__file__).parent.parent / "rag" / "clinic_knowledge"


def test_knowledge_files_exist():
    """All 5 required knowledge markdown files must be present."""
    expected = [
        "hours_and_location.md",
        "insurance_policies.md",
        "appointment_prep.md",
        "services_offered.md",
        "parking_and_directions.md",
    ]
    for filename in expected:
        assert (KNOWLEDGE_DIR / filename).exists(), f"Missing: {filename}"


def test_knowledge_files_nonempty():
    for md in KNOWLEDGE_DIR.glob("*.md"):
        assert md.stat().st_size > 100, f"{md.name} is suspiciously short"


def test_chunk_markdown():
    from rag.ingestion import _chunk_markdown

    content = "# Title\n\nFirst paragraph.\n\nSecond paragraph.\n\nOk\n\nFourth paragraph."
    chunks = _chunk_markdown(content, min_len=10)
    assert "First paragraph." in chunks
    assert "Second paragraph." in chunks
    assert "Ok" not in chunks  # too short


def test_ingest_and_query(tmp_path):
    """
    Full round-trip: ingest the real knowledge files into a temp ChromaDB,
    then verify that semantically relevant queries return the right content.
    """
    from rag.ingestion import ingest_clinic_knowledge
    from rag.vectorstore import query, format_context

    persist_dir = str(tmp_path / "chroma")
    collection_name = "test_faq"

    count = ingest_clinic_knowledge(
        knowledge_dir=KNOWLEDGE_DIR,
        persist_dir=persist_dir,
        collection_name=collection_name,
    )
    assert count > 0, "No chunks were ingested"

    # Hours query
    results = query("what are your hours?", top_k=3, persist_dir=persist_dir, collection_name=collection_name)
    assert len(results) > 0
    context = format_context(results)
    assert any(kw in context for kw in ["8:00 AM", "Monday", "weekday", "Saturday"]), (
        f"Hours not found in top results. Got: {context[:300]}"
    )

    # Insurance query
    results = query("do you accept Blue Cross insurance?", top_k=3, persist_dir=persist_dir, collection_name=collection_name)
    context = format_context(results)
    assert any(kw in context for kw in ["Blue Cross", "insurance", "Aetna"]), (
        f"Insurance info not found. Got: {context[:300]}"
    )

    # Parking query
    results = query("where do I park?", top_k=3, persist_dir=persist_dir, collection_name=collection_name)
    context = format_context(results)
    assert any(kw in context for kw in ["parking", "Parking", "lot", "garage"]), (
        f"Parking info not found. Got: {context[:300]}"
    )

    # Metadata is populated
    assert all(r["source"].endswith(".md") for r in results)
    assert all("distance" in r for r in results)


def test_query_empty_collection(tmp_path):
    """query() on an empty collection returns [] rather than crashing."""
    from rag.vectorstore import query

    persist_dir = str(tmp_path / "empty_chroma")
    results = query("anything", top_k=3, persist_dir=persist_dir, collection_name="empty")
    assert results == []


def test_format_context():
    from rag.vectorstore import format_context

    chunks = [
        {"text": "Chunk one.", "source": "a.md", "distance": 0.1},
        {"text": "Chunk two.", "source": "b.md", "distance": 0.2},
    ]
    ctx = format_context(chunks)
    assert "Chunk one." in ctx
    assert "Chunk two." in ctx
