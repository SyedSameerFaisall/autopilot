from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Any

import httpx

from .browser_worker import InspectedField
from .knowledge import similarity

DEFAULT_MODEL = "gpt-5.4-mini"


class AIConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class GroundedAnswer:
    value: str
    confidence: float
    source_reference: str
    evidence: str


def ai_status() -> dict[str, Any]:
    return {
        "provider": "openai",
        "configured": bool(os.getenv("OPENAI_API_KEY")),
        "model": os.getenv("APPLYPILOT_OPENAI_MODEL", DEFAULT_MODEL),
    }


def _memory_context(conn: sqlite3.Connection, fields: list[InspectedField]) -> str:
    questions = [field.label for field in fields]
    chunks = conn.execute("SELECT source_label, content FROM knowledge_chunks ORDER BY id DESC").fetchall()
    memories = conn.execute("SELECT question, answer FROM answer_memory ORDER BY updated_at DESC").fetchall()
    def rank(chunk: sqlite3.Row) -> float:
        content = chunk["content"]
        score = max((similarity(question, f"{chunk['source_label']} {content}") for question in questions), default=0)
        lowered_questions = " ".join(questions).lower()
        if "email" in lowered_questions and re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", content):
            score += 2
        if any(term in lowered_questions for term in ("phone", "mobile", "telephone")) and re.search(r"(?:\+?\d[\d ()-]{7,}\d)", content):
            score += 2
        return score

    ranked = sorted(chunks, key=rank, reverse=True)
    passages: list[str] = []
    size = 0
    for chunk in ranked:
        passage = f"[Source: {chunk['source_label']}]\n{chunk['content']}"
        if size + len(passage) > 18_000:
            break
        passages.append(passage)
        size += len(passage)
    reviewed = "\n\n".join(f"[Reviewed answer]\nQuestion: {item['question']}\nAnswer: {item['answer']}" for item in memories[:12])
    return "\n\n".join([*passages, reviewed]).strip()


def _output_text(response: dict[str, Any]) -> str:
    if response.get("output_text"):
        return str(response["output_text"])
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                return str(content.get("text", ""))
    raise ValueError("OpenAI returned no text output.")


def answer_form_fields(conn: sqlite3.Connection, fields: list[InspectedField]) -> dict[int, GroundedAnswer]:
    if not fields:
        return {}
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise AIConfigurationError("Set OPENAI_API_KEY before using AI form filling.")
    context = _memory_context(conn, fields)
    if not context:
        return {}
    field_payload = [
        {"id": index, "question": field.label, "field_type": field.field_type, "required": field.required}
        for index, field in enumerate(fields)
    ]
    schema = {
        "type": "object",
        "properties": {
            "answers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "supported": {"type": "boolean"},
                        "answer": {"type": "string"},
                        "confidence": {"type": "number"},
                        "source_reference": {"type": "string"},
                        "evidence": {"type": "string"},
                    },
                    "required": ["id", "supported", "answer", "confidence", "source_reference", "evidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["answers"],
        "additionalProperties": False,
    }
    prompt = f"""Answer application form questions using only the private memory context below.
Do not infer, guess, or invent facts. If the context does not directly support an answer, set supported to false and answer to an empty string.
Use concise direct values for contact fields. For narrative questions, write a polished answer grounded only in the supplied memory.
Return one result for every field id. Evidence must be a brief excerpt or explanation of the supporting source.

FORM FIELDS:
{json.dumps(field_payload)}

PRIVATE MEMORY CONTEXT:
{context}"""
    with httpx.Client(timeout=45) as client:
        response = client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": os.getenv("APPLYPILOT_OPENAI_MODEL", DEFAULT_MODEL),
                "input": prompt,
                "text": {"format": {"type": "json_schema", "name": "applypilot_answers", "strict": True, "schema": schema}},
            },
        )
    if response.status_code >= 400:
        raise ValueError(f"OpenAI request failed ({response.status_code}). Check your API key and model access.")
    payload = json.loads(_output_text(response.json()))
    answers: dict[int, GroundedAnswer] = {}
    for item in payload.get("answers", []):
        if item["supported"] and item["answer"].strip() and float(item["confidence"]) >= 0.7:
            answers[int(item["id"])] = GroundedAnswer(
                item["answer"].strip(),
                round(float(item["confidence"]), 2),
                item["source_reference"].strip(),
                item["evidence"].strip(),
            )
    return answers
