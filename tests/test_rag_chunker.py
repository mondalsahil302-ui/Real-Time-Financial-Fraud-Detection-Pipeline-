from pathlib import Path

from rag.chunker import chunk_markdown, deterministic_id, knowledge_metadata


def test_markdown_chunks_are_nonempty_and_keep_headings():
    text = "# Title\n\n" + "alpha beta gamma " * 40 + "\n\n## Details\n\n" + "delta epsilon " * 40
    chunks = chunk_markdown(text, max_words=30, overlap_words=5)
    assert chunks
    assert all(chunk.strip() for chunk in chunks)
    assert chunks[0].startswith("# Title")
    assert any("## Details" in chunk for chunk in chunks)


def test_knowledge_ids_and_status_are_deterministic(tmp_path: Path):
    root = tmp_path / "kb"
    current = root / "01_rbi_2024_master_direction" / "rules.md"
    current.parent.mkdir(parents=True)
    current.write_text("# Rule\n\nCurrent text")
    historical = root / "00_metadata" / "historical" / "old_guidelines.md"
    historical.parent.mkdir(parents=True)
    historical.write_text("# Old\n\nPrior text")
    assert deterministic_id("a.md", 0, "same") == deterministic_id("a.md", 0, "same")
    assert deterministic_id("a.md", 0, "same") != deterministic_id("a.md", 1, "same")
    assert knowledge_metadata(current, root, 0)["status"] == "current"
    assert knowledge_metadata(historical, root, 0)["status"] == "historical"
