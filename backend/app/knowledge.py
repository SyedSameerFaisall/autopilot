from __future__ import annotations

import math
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from .database import now_iso
from .profile_extractor import extract_github_export_candidates, extract_text

TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9+#]{1,}")
STOP_WORDS = {
    "about", "also", "and", "are", "been", "can", "could", "describe", "do", "for", "from",
    "have", "how", "in", "is", "it", "of", "on", "or", "please", "tell", "that", "the", "this",
    "to", "use", "what", "when", "where", "why", "with", "would", "you", "your",
}
def tokens(value: str) -> list[str]:
    return [token for token in TOKEN_PATTERN.findall(value.lower()) if token not in STOP_WORDS]


def similarity(query: str, text: str) -> float:
    query_terms = Counter(tokens(query))
    text_terms = Counter(tokens(text))
    if not query_terms or not text_terms:
        return 0.0
    overlap = sum(min(count, text_terms[term]) for term, count in query_terms.items())
    return overlap / math.sqrt(sum(query_terms.values()) * sum(text_terms.values()))


def chunk_text(text: str, max_chars: int = 700) -> list[str]:
    blocks = [re.sub(r"\s+", " ", block).strip() for block in re.split(r"\n\s*\n|\r\n\s*\r\n", text)]
    blocks = [block for block in blocks if block]
    chunks: list[str] = []
    current = ""
    for block in blocks:
        for start in range(0, len(block), max_chars):
            piece = block[start:start + max_chars].strip()
            if not piece:
                continue
            if current and len(current) + len(piece) + 1 <= max_chars:
                current = f"{current} {piece}"
            else:
                if current:
                    chunks.append(current)
                current = piece
    if current:
        chunks.append(current)
    return chunks


def index_document(conn: sqlite3.Connection, document_id: int, filename: str, text: str) -> int:
    conn.execute("DELETE FROM knowledge_chunks WHERE document_id = ?", (document_id,))
    chunks = chunk_text(text)
    conn.executemany(
        """INSERT INTO knowledge_chunks(document_id, source_type, source_label, content, created_at)
           VALUES (?, 'document', ?, ?, ?)""",
        [(document_id, filename, content, now_iso()) for content in chunks],
    )
    return len(chunks)


def index_github_projects(conn: sqlite3.Connection, document_id: int, _filename: str, projects: list[Any]) -> int:
    conn.execute("DELETE FROM knowledge_chunks WHERE document_id = ?", (document_id,))
    conn.executemany(
        """INSERT INTO knowledge_chunks(document_id, source_type, source_label, content, created_at)
           VALUES (?, 'github', ?, ?, ?)""",
        [(document_id, project.label, f"Project: {project.label}. Repository: {project.value}", now_iso()) for project in projects],
    )
    return len(projects)


def reindex_documents(conn: sqlite3.Connection) -> int:
    indexed = 0
    for document in conn.execute("SELECT * FROM profile_documents ORDER BY id").fetchall():
        path = Path(document["stored_path"])
        if not path.exists():
            continue
        try:
            if path.name.lower().endswith(".tar.gz"):
                indexed += index_github_projects(conn, document["id"], document["filename"], extract_github_export_candidates(path))
            else:
                indexed += index_document(conn, document["id"], document["filename"], extract_text(path))
        except (OSError, ValueError):
            continue
    return indexed


def save_answer_memory(conn: sqlite3.Connection, question: str, answer: str, source: str = "reviewed") -> None:
    if not question.strip() or not answer.strip():
        return
    conn.execute(
        """INSERT INTO answer_memory(question, answer, source, updated_at) VALUES (?, ?, ?, ?)
           ON CONFLICT(question) DO UPDATE SET answer = excluded.answer, source = excluded.source, updated_at = excluded.updated_at""",
        (question.strip(), answer.strip(), source, now_iso()),
    )
