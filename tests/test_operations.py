import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from backend.telemetry import CURRENT_TRACE, ConsultaTrace, medir_etapa, registrar_tentativa, registrar_uso
from backend.api import app
from backend.security import RequestLimiter
from fastapi.testclient import TestClient
from backend.evaluate import load_cases, readability, run_evaluation
from backend.rag_engine import ErroConsultaCDC, RespostaJuridicaCDC


class OperationsTests(unittest.TestCase):
    def test_privacy_notice_allows_request_without_checkbox_consent(self):
        response = TestClient(app).post("/api/chat", json={"question": " "}, headers={"X-Privacy-Notice": "displayed"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("Digite uma pergunta", response.json()["detail"])

    def test_stream_reports_real_stages_and_terminal_result(self):
        def consult(**kwargs):
            with medir_etapa("understanding"):
                pass
            with medir_etapa("preparing"):
                pass
            return RespostaJuridicaCDC(fundamentacao_encontrada=False, status="esclarecimento", resposta_orientativa="Qual foi a taxa?"), []
        with patch("backend.api.get_engine", return_value=(object(), object())), patch("backend.api.consultar_cdc", side_effect=consult), patch("backend.api.RATE_LIMITER", RequestLimiter(limit=1000)), TemporaryDirectory() as directory, patch("backend.telemetry.CACHE_DIR", Path(directory)):
            response = TestClient(app, headers={"X-Data-Consent": "accepted"}).post("/api/chat/stream", json={"question": "Tenho que pagar?"})
        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertEqual(response.status_code, 200)
        self.assertEqual([event["stage"] for event in events if event["type"] == "progress"], ["indexing", "understanding", "preparing"])
        self.assertEqual(events[-1]["type"], "result")
        self.assertEqual(events[-1]["data"]["content"], "Qual foi a taxa?")

    def test_stream_failure_has_terminal_error(self):
        with patch("backend.api.get_engine", side_effect=ErroConsultaCDC("unavailable")), patch("backend.api.RATE_LIMITER", RequestLimiter(limit=1000)), TemporaryDirectory() as directory, patch("backend.telemetry.CACHE_DIR", Path(directory)):
            response = TestClient(app, headers={"X-Data-Consent": "accepted"}).post("/api/chat/stream", json={"question": "Uma duvida"})
        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertEqual(events[-1]["type"], "error")
        self.assertNotIn("unavailable", response.text)

    def test_evaluation_cases_are_explicitly_pending_review(self):
        cases = load_cases()
        self.assertGreaterEqual(len(cases), 15)
        self.assertTrue(all(case["review"]["status"] == "pending" for case in cases))
        self.assertIn("desperdicio-erros", {case["id"] for case in cases})

    def test_offline_evaluation_does_not_call_provider(self):
        case = next(case for case in load_cases() if case["id"] == "desperdicio-erros")
        with patch("backend.rag_engine.IndiceHibridoCDC._carregar_ou_gerar_embeddings", return_value=None):
            report = run_evaluation([case])
        self.assertEqual(report["mode"], "lexical")
        self.assertTrue(report["cases"][0]["curated_expansion_hit"])
        self.assertEqual(report["summary"]["approved"], 0)
        self.assertIn("nao comprovam", readability("Uma cobranca indevida.")["note"])

    def test_consent_required_before_sending_data(self):
        response = TestClient(app).post("/api/chat", json={"question": "Uma duvida"})
        self.assertEqual(response.status_code, 403)

    def test_unknown_origin_is_rejected(self):
        response = TestClient(app).post("/api/chat", json={"question": "Uma duvida"}, headers={"X-Data-Consent": "accepted", "Origin": "https://untrusted.invalid"})
        self.assertEqual(response.status_code, 403)

    def test_rate_limit_has_retry_after(self):
        with patch("backend.api.RATE_LIMITER", RequestLimiter(limit=1)):
            client = TestClient(app, headers={"X-Data-Consent": "accepted"})
            client.post("/api/chat", json={"question": " "})
            response = client.post("/api/chat", json={"question": " "})
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)

    def test_pdf_source_is_served_inline(self):
        response = TestClient(app).get("/api/sources/cdc.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn("inline", response.headers["content-disposition"])

    def test_metrics_store_only_operational_fields(self):
        events = []
        trace = ConsultaTrace(model="test-model", notify=events.append)
        token = CURRENT_TRACE.set(trace)
        try:
            with TemporaryDirectory() as directory, patch("backend.telemetry.CACHE_DIR", Path(directory)):
                with medir_etapa("understanding"):
                    registrar_tentativa()
                    registrar_uso(SimpleNamespace(usage_metadata=SimpleNamespace(prompt_token_count=12, candidates_token_count=4)))
                record = trace.finish("fundamentada")
                with closing(sqlite3.connect(Path(directory) / "metrics.sqlite3")) as database:
                    stored = json.loads(database.execute("SELECT metrics FROM requests").fetchone()[0])
                self.assertEqual(stored["input_tokens"], 12)
                self.assertEqual(record["output_tokens"], 4)
                self.assertIsNone(record["generation_cost_usd_estimate"])
                self.assertNotIn("question", stored)
                self.assertNotIn("history", stored)
                self.assertEqual(events[0]["stage"], "understanding")
        finally:
            CURRENT_TRACE.reset(token)


if __name__ == "__main__":
    unittest.main()