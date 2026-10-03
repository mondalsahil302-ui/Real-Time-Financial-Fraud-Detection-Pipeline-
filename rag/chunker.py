"""Deterministic Markdown section chunking and metadata extraction."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

HEADING = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*$")


def chunk_markdown(text: str, max_words: int = 850, overlap_words: int = 120) -> list[str]:
    """Chunk Markdown on heading boundaries, keeping each heading with its body."""
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []
    matches = list(HEADING.finditer(text))
    if not matches:
        sections = [text]
    else:
        sections = []
        if text[:matches[0].start()].strip():
            sections.append(text[:matches[0].start()].strip())
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            section = text[match.start():end].strip()
            if section:
                sections.append(section)

    chunks: list[str] = []
    current = ""
    for section in sections:
        if len(section.split()) > max_words:
            # Split long sections at paragraph boundaries, then at word boundaries.
            heading_match = HEADING.match(section)
            section_heading = heading_match.group(0) if heading_match else ""
            pieces: list[str] = []
            paragraph_buffer = ""
            for para in re.split(r"\n\s*\n", section):
                candidate = f"{paragraph_buffer}\n\n{para}".strip()
                if len(candidate.split()) > max_words and paragraph_buffer:
                    pieces.append(paragraph_buffer)
                    paragraph_buffer = para
                else:
                    paragraph_buffer = candidate
            if paragraph_buffer:
                pieces.append(paragraph_buffer)
            expanded: list[str] = []
            for piece in pieces:
                words = piece.split()
                if len(words) <= max_words:
                    expanded.append(piece)
                else:
                    expanded.extend(" ".join(words[i:i + max_words]) for i in range(0, len(words), max_words))
            if section_heading:
                expanded = [part if part.startswith(section_heading) else f"{section_heading}\n\n{part}" for part in expanded]
            sections_for_merge = expanded
        else:
            sections_for_merge = [section]
        for piece in sections_for_merge:
            candidate = f"{current}\n\n{piece}".strip()
            if current and len(candidate.split()) > max_words:
                chunks.append(current)
                prior = current.split()
                current = " ".join(prior[-overlap_words:]) if overlap_words else ""
            current = f"{current}\n\n{piece}".strip()
    if current.strip():
        chunks.append(current.strip())
    return [re.sub(r"\n{3,}", "\n\n", c).strip() for c in chunks if c.strip()]


def deterministic_id(relative_path: str, chunk_index: int, text: str, prefix: str = "knowledge") -> str:
    payload = f"{relative_path}{chunk_index}{text}".encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()}"


def knowledge_metadata(path: Path, root: Path, chunk_index: int, source_text: str = "") -> dict:
    rel = path.relative_to(root).as_posix()
    parts = Path(rel).parts
    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---(?:\s*\n|$)", source_text, re.DOTALL)
    frontmatter = {}
    if frontmatter_match:
        for line in frontmatter_match.group(1).splitlines():
            match = re.match(r"^([\w-]+):\s*(.*?)\s*$", line)
            if match:
                frontmatter[match.group(1)] = match.group(2).strip().strip("\"'")
    source_type = frontmatter.get("source_type")
    historical = source_type == "historical_reference" or any(p.lower() == "historical" for p in parts[:-1]) or "old_guidelines" in path.name.lower()
    top = parts[0] if parts else ""
    topics = {
        "01_rbi_2024_master_direction": "rbi_master_direction",
        "02_early_warning_signals_ews_rfa": "early_warning_signals",
        "03_transaction_monitoring_and_analytics": "transaction_monitoring",
        "04_fraud_classification": "fraud_classification",
        "05_investigation": "investigation",
        "06_governance_accountability_controls": "governance",
        "07_reporting": "reporting",
        "08_fraud_case_lifecycle": "case_lifecycle",
        "09_cheque_related_fraud": "cheque_fraud",
        "10_digital_banking_and_payment_fraud": "digital_payment_fraud",
        "11_physical_security_incidents": "physical_security",
        "12_other_rbi_fraud_risk_topics": "other_rbi_topics",
    }
    source_file = frontmatter.get("source_file", path.name)
    publisher = frontmatter.get("publisher")
    version = "historical" if historical else ("2024" if "2024" in rel or "15-07-24" in source_file or top.startswith("01_rbi") else "unspecified")
    authority = publisher or ("RBI" if "rbi" in source_file.lower() or historical else ("PwC" if "pwc" in rel.lower() else "knowledge_base"))
    status = "historical" if historical else ("current" if version == "2024" and source_type != "secondary_analysis" else "reference")
    raw_pages = frontmatter.get("source_pages", frontmatter.get("source_page"))
    source_pages = re.sub(r"[\[\]]", "", raw_pages) if raw_pages else None
    return {
        "source_type": "historical_reference" if historical else (source_type or "regulatory_knowledge"),
        "document_type": "historical_guidance" if historical else topics.get(top, "fraud_knowledge"),
        "topic": topics.get(top, "metadata_policy" if top == "00_metadata" else top),
        "authority": authority,
        "current_authority": status == "current",
        "version": version,
        "status": status,
        "relative_path": rel,
        "source_file": source_file,
        "chunk_index": int(chunk_index),
        **({"subtopic": frontmatter["subtopic"]} if frontmatter.get("subtopic") else {}),
        **({"publisher": publisher} if publisher else {}),
        **({"source_pages": source_pages} if source_pages else {}),
    }
