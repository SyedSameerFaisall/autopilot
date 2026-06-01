from __future__ import annotations

import math
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
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


@dataclass(frozen=True)
class RetrievedAnswer:
    value: str
    confidence: float
    source_kind: str
    source_reference: str
    reason: str


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


def retrieve_answer(conn: sqlite3.Connection, question: str, field_type: str) -> RetrievedAnswer | None:
    memories = conn.execute("SELECT * FROM answer_memory ORDER BY updated_at DESC").fetchall()
    ranked_memories = sorted(
        ((similarity(question, memory["question"]), memory) for memory in memories),
        key=lambda item: item[0],
        reverse=True,
    )
    if ranked_memories and ranked_memories[0][0] >= 0.62:
        score, memory = ranked_memories[0]
        return RetrievedAnswer(
            memory["answer"],
            min(0.93, round(0.72 + score * 0.2, 2)),
            "answer_memory",
            memory["question"],
            "Reused a similar answer that you previously reviewed.",
        )

    if field_type != "textarea":
        return None
    chunks = conn.execute("SELECT * FROM knowledge_chunks ORDER BY id").fetchall()
    ranked_chunks = sorted(
        ((similarity(question, f"{chunk['source_label']} {chunk['content']}"), chunk) for chunk in chunks),
        key=lambda item: item[0],
        reverse=True,
    )
    if not ranked_chunks or ranked_chunks[0][0] < 0.2:
        return None
    score, chunk = ranked_chunks[0]
    value = chunk["content"][:600].strip()
    return RetrievedAnswer(
        value,
        min(0.78, round(0.5 + score * 0.35, 2)),
        "knowledge_chunk",
        chunk["source_label"],
        f"Drafted from local source evidence in {chunk['source_label']}. Review before use.",
    )
