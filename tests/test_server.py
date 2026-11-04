import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient

from backend.api import app
from backend.rag_engine import ErroConsultaCDC, RespostaJuridicaCDC
from backend.security import RequestLimiter


class ConsumiApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.headers["X-Data-Consent"] = "accepted"
        limiter = patch("backend.api.RATE_LIMITER", RequestLimiter(limit=1000))
        limiter.start()
        self.addCleanup(limiter.stop)
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        metrics = patch("backend.telemetry.CACHE_DIR", Path(directory.name))
        metrics.start()
        self.addCleanup(metrics.stop)

    def test_status_does_not_expose_key(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["ready"])
        self.assertNotIn("GEMINI_API_KEY", response.text)

    def test_chat_preserves_citations_and_history(self):
        answer = RespostaJuridicaCDC(
            fundamentacao_encontrada=True,
            resposta_orientativa="O prazo e de sete dias.",
            resposta_didatica="Voce tem sete dias para desistir dessa compra pela internet.",
            artigos_citados=["Art. 49"],
            paginas_pdf=[29],
            trecho_literal="O consumidor pode desistir do contrato",
        )
        with patch("backend.api.get_engine", return_value=(object(), object())), patch("backend.api.consultar_cdc", return_value=(answer, [])) as query:
            response = self.client.post("/api/chat", json={"question": "Posso devolver?", "history": [{"role": "user", "content": "Comprei pela internet"}]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["articles"], ["Art. 49"])
        self.assertEqual(response.json()["pages"], [29])
        self.assertEqual(response.json()["status"], "fundamentada")
        self.assertEqual(response.json()["simple_content"], answer.resposta_didatica)
        self.assertEqual(response.json()["detailed_content"], answer.resposta_orientativa)
        self.assertIn("## Em palavras simples", response.json()["content"])
        self.assertIn("## Analise detalhada", response.json()["content"])
        self.assertEqual(response.json()["sources"][0]["url"], "/api/sources/cdc.pdf#page=29")
        self.assertEqual(response.json()["sources"][0]["edition"], "PROCON-SP 2025")
        self.assertEqual(query.call_args.kwargs["historico_conversa"][0]["content"], "Comprei pela internet")

    def test_technical_error_is_not_a_successful_legal_refusal(self):
        with patch("backend.api.get_engine", return_value=(object(), object())), patch("backend.api.consultar_cdc", side_effect=ErroConsultaCDC("provider unavailable")):
            response = self.client.post("/api/chat", json={"question": "Posso devolver?"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["status"], "erro_tecnico")
        self.assertNotIn("provider unavailable", response.text)

    def test_clarification_is_exposed_without_fake_citations(self):
        answer = RespostaJuridicaCDC(fundamentacao_encontrada=False, status="esclarecimento", resposta_orientativa="Qual taxa foi cobrada?", pergunta_interpretada="Uma cobranca nao especificada")
        with patch("backend.api.get_engine", return_value=(object(), object())), patch("backend.api.consultar_cdc", return_value=(answer, [])):
            response = self.client.post("/api/chat", json={"question": "Tenho que pagar?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "esclarecimento")
        self.assertEqual(response.json()["content"], "Qual taxa foi cobrada?")
        self.assertEqual(response.json()["articles"], [])
        self.assertEqual(response.json()["simple_content"], "")
        self.assertEqual(response.json()["detailed_content"], "")
        self.assertEqual(response.json()["interpretation"], answer.pergunta_interpretada)

    def test_blank_question_is_rejected(self):
        self.assertEqual(self.client.post("/api/chat", json={"question": "   "}).status_code, 422)

    def test_complaint_action_and_case_context_reach_the_engine(self):
        draft = "Prezados, recebi o produto com defeito. Solicito uma solucao e retorno sobre o pedido [numero]. Atenciosamente, [seu nome]."
        answer = RespostaJuridicaCDC(fundamentacao_encontrada=False, resposta_orientativa="Rascunho factual; revise antes de enviar.", texto_reclamacao=draft)
        with patch("backend.api.get_engine", return_value=(object(), object())), patch("backend.api.consultar_cdc", return_value=(answer, [])) as query:
            response = self.client.post("/api/chat", json={"question": "Escreva a reclamacao", "action": "reclamacao", "case_context": "O celular chegou quebrado."})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["complaint_text"], draft)
        self.assertEqual(response.json()["detailed_content"], answer.resposta_orientativa)
        self.assertEqual(response.json()["articles"], [])
        self.assertEqual(query.call_args.kwargs["acao"], "reclamacao")
        self.assertEqual(query.call_args.kwargs["contexto_caso"], "O celular chegou quebrado.")

    def test_txt_attachment(self):
        response = self.client.post("/api/attachment", content=b"Meu celular chegou com defeito", headers={"X-Filename": "relato.txt"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("celular", response.json()["text"])

    def test_pdf_attachment(self):
        with fitz.open() as document:
            document.new_page().insert_text((50, 50), "Produto com defeito")
            data = document.tobytes()
        response = self.client.post("/api/attachment", content=data, headers={"X-Filename": "relato.pdf"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("defeito", response.json()["text"])

    def test_invalid_attachment(self):
        for filename, data, expected in [("foto.png", b"image", 415), ("relato.pdf", b"invalid", 422), ("relato.txt", b"", 422), ("relato.txt", b"a" * 12001, 422), ("relato.txt", b"a" * (5 * 1024 * 1024 + 1), 413)]:
            with self.subTest(filename=filename, expected=expected):
                response = self.client.post("/api/attachment", content=data, headers={"X-Filename": filename})
                self.assertEqual(response.status_code, expected)


if __name__ == "__main__":
    unittest.main()