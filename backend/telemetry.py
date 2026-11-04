"""Metricas operacionais locais sem perguntas, anexos, IPs ou respostas."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from contextlib import closing, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from .paths import CACHE_DIR

logger = logging.getLogger(__name__)


@dataclass
class ConsultaTrace:
    model: str
    notify: Callable[[dict], None] | None = None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started: float = field(default_factory=time.monotonic)
    stages: dict[str, float] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    usage_calls: int = 0
    generation_calls: int = 0
    embedding_tokens: int = 0
    embedding_calls: int = 0
    embedding_usage_calls: int = 0
    mode: str = "not_searched"
    fallback: bool = False

    def usage(self, result, embedding: bool = False) -> None:
        usage = getattr(result, "usage_metadata", None)
        if embedding:
            if getattr(usage, "total_token_count", None) is not None:
                self.embedding_usage_calls += 1
            self.embedding_tokens += int(getattr(usage, "total_token_count", 0) or 0)
        else:
            if usage is not None:
                self.usage_calls += 1
                self.input_tokens += int(getattr(usage, "prompt_token_count", 0) or 0)
                self.output_tokens += int(getattr(usage, "candidates_token_count", 0) or 0) + int(getattr(usage, "thoughts_token_count", 0) or 0)

    def finish(self, status: str) -> dict:
        estimate = None
        try:
            input_price = float(os.environ["GENERATION_INPUT_USD_PER_MILLION"])
            output_price = float(os.environ["GENERATION_OUTPUT_USD_PER_MILLION"])
            if self.usage_calls == self.generation_calls and self.generation_calls and status != "erro_tecnico" and input_price >= 0 and output_price >= 0:
                estimate = round((self.input_tokens * input_price + self.output_tokens * output_price) / 1_000_000, 8)
        except (KeyError, ValueError):
            pass
        record = {
            "request_id": self.request_id, "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": self.model, "status": status, "duration_ms": round((time.monotonic() - self.started) * 1000),
            "stages_ms": self.stages, "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
            "generation_calls": self.generation_calls, "usage_complete": self.usage_calls == self.generation_calls and status != "erro_tecnico",
            "embedding_calls": self.embedding_calls, "embedding_tokens": self.embedding_tokens if self.embedding_usage_calls == self.embedding_calls else None,
            "retrieval_mode": self.mode, "fallback": self.fallback,
            "generation_cost_usd_estimate": estimate,
        }
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(CACHE_DIR / "metrics.sqlite3", timeout=5)) as database, database:
                database.execute("CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, created_at TEXT, metrics TEXT)")
                database.execute("INSERT INTO requests VALUES (?, ?, ?)", (self.request_id, record["timestamp"], json.dumps(record)))
                database.execute("DELETE FROM requests WHERE julianday(created_at) < julianday('now', '-30 days')")
        except (OSError, sqlite3.Error):
            logger.warning("Metricas indisponiveis; consulta preservada")
        return record


CURRENT_TRACE: ContextVar[ConsultaTrace | None] = ContextVar("consumiai_trace", default=None)


@contextmanager
def medir_etapa(stage: str):
    trace = CURRENT_TRACE.get()
    started = time.monotonic()
    if trace and trace.notify:
        trace.notify({"type": "progress", "stage": stage})
    try:
        yield
    finally:
        if trace:
            trace.stages[stage] = round(trace.stages.get(stage, 0) + (time.monotonic() - started) * 1000, 1)


def registrar_uso(result, embedding: bool = False) -> None:
    trace = CURRENT_TRACE.get()
    if trace:
        trace.usage(result, embedding)


def registrar_tentativa(embedding: bool = False) -> None:
    trace = CURRENT_TRACE.get()
    if trace:
        if embedding:
            trace.embedding_calls += 1
        else:
            trace.generation_calls += 1


def resumo_metricas() -> dict:
    path = CACHE_DIR / "metrics.sqlite3"
    if not path.is_file():
        return {"requests": 0}
    with closing(sqlite3.connect(path)) as database:
        rows = [json.loads(row[0]) for row in database.execute("SELECT metrics FROM requests ORDER BY created_at DESC LIMIT 1000")]
    return {
        "requests": len(rows), "average_duration_ms": round(sum(row["duration_ms"] for row in rows) / len(rows)) if rows else 0,
        "technical_errors": sum(row["status"] == "erro_tecnico" for row in rows),
        "fallback_requests": sum(row["fallback"] for row in rows),
        "input_tokens": sum(row["input_tokens"] for row in rows), "output_tokens": sum(row["output_tokens"] for row in rows),
        "note": "Ultimas 1000 consultas; custos estimados somente com precos configurados. Sem textos de usuarios.",
    }


if __name__ == "__main__":
    print(json.dumps(resumo_metricas(), indent=2, ensure_ascii=False))