"""API local do ConsumiAI e publicacao do frontend React compilado."""

from __future__ import annotations

import logging
import os
import asyncio
import json
import threading
from queue import Queue
from pathlib import Path
from typing import Literal
from urllib.parse import unquote

import fitz
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from .paths import CDC_PDF_PATH, FRONTEND_DIST_DIR, PROJECT_ROOT
from .security import RequestLimiter
from .telemetry import CURRENT_TRACE, ConsultaTrace, medir_etapa
from .rag_engine import (
    ErroConsultaCDC,
    IndiceHibridoCDC,
    consultar_cdc,
    extrair_chunks_cdc,
    formatar_resposta_estruturada,
)

PDF_PATH = CDC_PDF_PATH
MAX_UPLOAD = 5 * 1024 * 1024
load_dotenv(PROJECT_ROOT / ".env")
logger = logging.getLogger(__name__)
app = FastAPI(title="ConsumiAI", docs_url="/api/docs", openapi_url="/api/openapi.json")
RATE_LIMITER = RequestLimiter()
_SLOTS = threading.BoundedSemaphore(2)
_ENGINE_LOCK = threading.Lock()
_ENGINE = None
_TASKS: set[asyncio.Task] = set()


@app.middleware("http")
async def protect_requests(request: Request, call_next):
    if request.method == "POST" and request.url.path.startswith("/api/"):
        if request.headers.get("X-Privacy-Notice") != "displayed" and request.headers.get("X-Data-Consent") != "accepted":
            return JSONResponse(status_code=403, content={"detail": "O aviso de privacidade deve estar disponivel antes do envio."})
        origins = set(os.environ.get("ALLOWED_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000,http://127.0.0.1:5173,http://localhost:5173,http://testserver").split(","))
        req_origin = request.headers.get("origin")
        if req_origin and "*" not in origins and req_origin not in origins:
            host_header = request.headers.get("host")
            if not (host_header and req_origin.endswith(host_header)):
                return JSONResponse(status_code=403, content={"detail": "Origem nao autorizada."})
        try:
            length = int(request.headers.get("content-length", "-1"))
        except ValueError:
            length = -1
        maximum = MAX_UPLOAD if request.url.path == "/api/attachment" else 256 * 1024
        if length < 0:
            return JSONResponse(status_code=411, content={"detail": "Informe Content-Length para enviar dados."})
        if length > maximum:
            return JSONResponse(status_code=413, content={"detail": "O envio excede o tamanho permitido."})
        if not RATE_LIMITER.allow(request.client.host if request.client else "unknown"):
            return JSONResponse(status_code=429, content={"detail": "Muitas solicitacoes. Aguarde um minuto antes de tentar novamente."}, headers={"Retry-After": "60"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith("/api/") and request.url.path != "/api/sources/cdc.pdf":
        response.headers["Cache-Control"] = "no-store"
    return response


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=22000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=22000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=4)
    action: Literal["orientacao", "reclamacao", "prazo", "procon"] = "orientacao"
    case_context: str = Field(default="", max_length=12000)


def get_engine() -> tuple[genai.Client, IndiceHibridoCDC]:
    global _ENGINE
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise HTTPException(503, "Configure GEMINI_API_KEY no arquivo .env do servidor.")
    if not PDF_PATH.is_file():
        raise HTTPException(503, "O PDF oficial do CDC nao foi encontrado no servidor.")
    with _ENGINE_LOCK:
        if _ENGINE is None:
            client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=60000))
            _ENGINE = client, IndiceHibridoCDC(extrair_chunks_cdc(str(PDF_PATH)), client)
    return _ENGINE


@app.get("/api/status")
def status() -> dict:
    key_present = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    pdf_present = PDF_PATH.is_file()
    ready = key_present and pdf_present
    detail = "Configurado" if ready else "Chave de API pendente" if not key_present else "Base CDC ausente"
    index = _ENGINE[1] if _ENGINE else None
    return {"ready": ready, "detail": detail, "edition": "CDC | PROCON-SP 2025",
            "retrieval_mode": "hybrid" if index and index.embeddings is not None else "lexical" if index else "not_initialized",
            "indexed_chunks": index.indexed_chunks if index else 0, "total_chunks": len(index.chunks) if index else 0}


def execute_query(payload: ChatRequest, notify=None):
    if not payload.question.strip():
        raise HTTPException(422, "Digite uma pergunta antes de enviar.")
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    trace = ConsultaTrace(model=model, notify=notify)
    token = CURRENT_TRACE.set(trace)
    result_status = "erro_tecnico"
    try:
        with medir_etapa("indexing"):
            client, index = get_engine()
        answer, _ = consultar_cdc(
            pergunta=payload.question.strip(),
            indice=index,
            client_genai=client,
            model_name=model,
            historico_conversa=[message.model_dump() for message in payload.history[-4:]],
            acao=payload.action,
            contexto_caso=payload.case_context,
        )
        grounded = answer.fundamentacao_encontrada
        result_status = answer.status
        output = {
            "content": formatar_resposta_estruturada(answer),
            "simple_content": answer.resposta_didatica if grounded else "",
            "detailed_content": answer.resposta_orientativa if grounded or answer.texto_reclamacao else "",
            "complaint_text": answer.texto_reclamacao,
            "articles": answer.artigos_citados if grounded else [],
            "pages": answer.paginas_pdf if grounded else [],
            "quote": answer.trecho_literal if grounded else "",
            "status": answer.status,
            "interpretation": answer.pergunta_interpretada,
            "basis": answer.natureza_fundamentacao,
            "limitations": answer.limitacoes,
            "sources": [{"title": "Codigo de Defesa do Consumidor e decretos complementares",
                         "edition": "PROCON-SP 2025", "page": page,
                         "url": f"/api/sources/cdc.pdf#page={page}"} for page in answer.paginas_pdf] if grounded else [],
        }
    finally:
        metrics = trace.finish(result_status)
        CURRENT_TRACE.reset(token)
    output["diagnostics"] = {key: metrics[key] for key in ("request_id", "duration_ms", "retrieval_mode", "fallback")}
    return output


def query_result(payload: ChatRequest, notify=None):
    try:
        return execute_query(payload, notify), 200
    except HTTPException:
        raise
    except ErroConsultaCDC as error:
        logger.error("Falha tecnica na consulta CDC: %s", error)
        return {
            "status": "erro_tecnico",
            "detail": "Ocorreu uma falha tecnica ao consultar o modelo. Isso nao indica falta de fundamento no CDC. Tente novamente em instantes.",
        }, 502
    except Exception:
        logger.error("Falha tecnica nao classificada na consulta ao CDC")
        return {"status": "erro_tecnico", "detail": "Nao foi possivel consultar o assistente. Tente novamente."}, 502


@app.post("/api/chat")
def chat(payload: ChatRequest):
    if not _SLOTS.acquire(blocking=False):
        raise HTTPException(429, "O assistente esta ocupado. Tente novamente em instantes.")
    try:
        result, code = query_result(payload)
        return JSONResponse(result, status_code=code)
    finally:
        _SLOTS.release()


@app.post("/api/chat/stream")
async def chat_stream(payload: ChatRequest):
    if not payload.question.strip():
        raise HTTPException(422, "Digite uma pergunta antes de enviar.")
    if not _SLOTS.acquire(blocking=False):
        raise HTTPException(429, "O assistente esta ocupado. Tente novamente em instantes.")
    events = Queue()

    def worker():
        try:
            result, code = query_result(payload, events.put)
            events.put({"type": "result" if code == 200 else "error", "data": result})
        except HTTPException as error:
            events.put({"type": "error", "data": {"detail": error.detail}})
        except Exception:
            events.put({"type": "error", "data": {"detail": "Falha ao preparar a consulta."}})
        finally:
            _SLOTS.release()

    task = asyncio.create_task(run_in_threadpool(worker))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)

    async def stream():
        while True:
            event = await run_in_threadpool(events.get)
            yield json.dumps(event, ensure_ascii=False) + "\n"
            if event["type"] in {"result", "error"}:
                break

    return StreamingResponse(stream(), media_type="application/x-ndjson", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"})


@app.get("/api/sources/cdc.pdf")
def source_pdf():
    if not PDF_PATH.is_file():
        raise HTTPException(404, "Documento indisponivel.")
    return FileResponse(PDF_PATH, media_type="application/pdf", filename="codigo_defesa_consumidor.pdf", content_disposition_type="inline")


def extract_attachment(data: bytes, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    try:
        if suffix == ".txt":
            text = data.decode("utf-8-sig")
        elif suffix == ".pdf":
            with fitz.open(stream=data, filetype="pdf") as document:
                if document.needs_pass:
                    raise HTTPException(422, "O PDF esta protegido por senha.")
                parts = []
                length = 0
                for page in document:
                    part = page.get_text()
                    parts.append(part)
                    length += len(part)
                    if length > 12000:
                        break
                text = "\n".join(parts)
        else:
            raise HTTPException(415, "Anexe um PDF ou um arquivo TXT em UTF-8.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "Nao foi possivel ler o arquivo. Use um PDF com texto ou TXT em UTF-8.") from None
    text = text.strip()
    if not text:
        raise HTTPException(422, "O arquivo nao contem texto legivel. PDFs digitalizados precisam de OCR.")
    if len(text) > 12000:
        raise HTTPException(422, "O anexo excede 12.000 caracteres. Envie apenas o trecho relevante ao seu caso.")
    return text


@app.post("/api/attachment")
async def attachment(request: Request) -> dict[str, str]:
    filename = unquote(request.headers.get("X-Filename", ""))
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "O anexo deve ter no maximo 5 MB.")
    text = await run_in_threadpool(extract_attachment, bytes(data), filename)
    return {"text": text}


if FRONTEND_DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend")