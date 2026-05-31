from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from pypdf import PdfReader


@dataclass(frozen=True)
class CandidateFact:
    section: str
    label: str
    value: str
    confidence: float


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    if suffix == ".docx":
        document = Document(path)
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError("Upload a PDF, DOCX, TXT, or Markdown document.")


def extract_candidates(text: str) -> list[CandidateFact]:
    candidates: list[CandidateFact] = []
    normalized_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if normalized_lines:
        first_line = normalized_lines[0]
        if re.fullmatch(r"[A-Za-z][A-Za-z .'-]{2,70}", first_line) and len(first_line.split()) <= 5:
            candidates.append(CandidateFact("Personal", "Full name", first_line, 0.72))

    patterns = [
        ("Personal", "Email", r"[\w.+-]+@[\w-]+\.[\w.-]+", 0.99),
        ("Personal", "Phone", r"(?:\+?\d[\d ()-]{7,}\d)", 0.88),
        ("Links", "LinkedIn", r"https?://(?:www\.)?linkedin\.com/[^\s,)]+", 0.98),
        ("Links", "GitHub", r"https?://(?:www\.)?github\.com/[^\s,)]+", 0.98),
        ("Links", "Portfolio", r"https?://(?![^/\s]*(?:linkedin\.com|github\.com))[^\s,)]+", 0.68),
    ]
    seen = {(candidate.label, candidate.value.lower()) for candidate in candidates}
    for section, label, pattern, confidence in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            value = match.strip().rstrip(".")
            key = (label, value.lower())
            if key not in seen:
                candidates.append(CandidateFact(section, label, value, confidence))
                seen.add(key)
    return candidates
