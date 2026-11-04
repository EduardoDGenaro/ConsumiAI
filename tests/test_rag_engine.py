import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.paths import CDC_PDF_PATH
from backend.rag_engine import (
    ErroConsultaCDC,
    IndiceHibridoCDC,
    PlanoConsultaCDC,
    RespostaJuridicaCDC,
    SelecaoTrechosCDC,
    _recuperar_candidatos,
    _validar_fundamentacao,
    consultar_cdc,
    extrair_chunks_cdc,
    formatar_resposta_estruturada,
)


class RagEngineTests(unittest.TestCase):
    def setUp(self):
        self.plan = PlanoConsultaCDC(
            acao="consultar",
            pergunta_interpretada="Restaurante pode cobrar taxa de desperdicio de comida deixada no prato?",
            consultas_busca=["exigir do consumidor vantagem manifestamente excessiva", "obrigacoes iniquas abusivas desvantagem exagerada"],
        )
        self.rule = {"artigo": "Art. 39", "page": 25, "text": "Art. 39. E vedado ao fornecedor exigir do consumidor vantagem manifestamente excessiva."}
        self.noise = {"artigo": "Art. 40", "page": 26, "text": "O fornecedor de servico sera obrigado a entregar orcamento previo."}
        self.answer = RespostaJuridicaCDC(
            fundamentacao_encontrada=True,
            resposta_orientativa="A cobranca pode ser analisada a luz da vedacao de vantagem manifestamente excessiva; nao ha aqui proibicao especifica dessa taxa.",
            resposta_didatica="A taxa nao pode colocar voce em uma situacao injusta. Mas so com esses trechos nao da para afirmar se voce precisa pagar. Peca ao restaurante que explique como calculou a cobranca.",
            natureza_fundamentacao="interpretacao",
            artigos_citados=["Art. 39, V"],
            paginas_pdf=[25],
            trecho_literal="exigir do consumidor vantagem manifestamente excessiva",
            limitacoes=["A aplicacao depende das circunstancias da cobranca."],
        )
        self.index = Mock()
        self.index.buscar.return_value = [self.noise, self.rule]

    def client_with(self, *outputs):
        return SimpleNamespace(models=SimpleNamespace(generate_content=Mock(
            side_effect=[output if isinstance(output, Exception) else SimpleNamespace(parsed=output, text=None) for output in outputs]
        )))

    def test_api_failure_is_not_a_legal_refusal(self):
        index = Mock()
        index.buscar.return_value = [{"artigo": "Art. 49", "page": 29, "text": "O consumidor pode desistir do contrato."}]
        client = SimpleNamespace(
            interactions=SimpleNamespace(create=Mock(side_effect=TimeoutError("timeout"))),
            models=SimpleNamespace(generate_content=Mock(side_effect=TimeoutError("timeout"))),
        )
        with self.assertRaises(ErroConsultaCDC):
            consultar_cdc("Posso devolver uma compra pela internet?", index, client)

    def test_restaurant_typo_uses_reformulation_and_reranking(self):
        client = self.client_with(self.plan, SelecaoTrechosCDC(indices_ordenados=[1]), self.answer)
        answer, sources = consultar_cdc('sou obrigado a apagar o "disperdicio" mencionado em alguns restaurantes? como funciona?', self.index, client)
        self.assertEqual(answer.status, "fundamentada")
        self.assertEqual(answer.natureza_fundamentacao, "interpretacao")
        self.assertEqual(answer.pergunta_interpretada, self.plan.pergunta_interpretada)
        self.assertEqual(sources[0]["artigo"], "Art. 39")
        self.assertTrue(any(call.args[0] == self.plan.pergunta_interpretada for call in self.index.buscar.call_args_list))
        self.assertTrue(all(call.kwargs["top_k"] == 20 for call in self.index.buscar.call_args_list))
        prompt = client.models.generate_content.call_args.kwargs["contents"]
        self.assertIn("nao transforme", prompt.lower())
        self.assertNotIn(self.noise["text"], prompt)

    def test_two_answer_sections_are_generated_in_the_same_call(self):
        client = self.client_with(self.plan, SelecaoTrechosCDC(indices_ordenados=[1]), self.answer)
        answer, _ = consultar_cdc("Tenho que pagar taxa de desperdicio?", self.index, client)
        self.assertEqual(answer.resposta_didatica, self.answer.resposta_didatica)
        self.assertEqual(answer.resposta_orientativa, self.answer.resposta_orientativa)
        self.assertNotEqual(answer.resposta_didatica, answer.resposta_orientativa)
        self.assertEqual(client.models.generate_content.call_count, 3)
        prompt = client.models.generate_content.call_args.kwargs["contents"]
        self.assertIn("mesma conclusao", prompt)
        formatted = formatar_resposta_estruturada(answer)
        self.assertIn("## Em palavras simples", formatted)
        self.assertIn("## Analise detalhada", formatted)
        self.assertLess(formatted.index(answer.resposta_didatica), formatted.index(answer.resposta_orientativa))

    def test_complaint_action_requires_a_ready_to_send_message(self):
        draft = "Assunto: reclamacao sobre [numero do pedido]\nPrezados, recebi um celular com defeito. Solicito uma solucao para o problema e retorno sobre o atendimento. Atenciosamente, [seu nome]."
        answer = self.answer.model_copy(update={"texto_reclamacao": draft})
        client = self.client_with(self.plan, SelecaoTrechosCDC(indices_ordenados=[1]), answer)
        result, _ = consultar_cdc("Gere a reclamacao", self.index, client, acao="reclamacao")
        self.assertEqual(result.texto_reclamacao, draft)
        self.assertIn(draft, formatar_resposta_estruturada(result))
        prompt = client.models.generate_content.call_args.kwargs["contents"]
        self.assertIn("mensagem completa pronta para enviar", prompt)
        self.assertIn("primeira pessoa", prompt)
        self.assertIn("nao comprovam fatos", prompt)

    def test_advice_alone_does_not_satisfy_complaint_action(self):
        client = self.client_with(self.plan, SelecaoTrechosCDC(indices_ordenados=[1]), self.answer)
        with self.assertRaises(ErroConsultaCDC):
            consultar_cdc("Gere a reclamacao", self.index, client, acao="reclamacao")

    def test_deadline_and_procon_actions_have_specific_instructions(self):
        for action, expected in [("prazo", "Distinga prazo"), ("procon", "procedimento dependem da localidade")]:
            with self.subTest(action=action):
                client = self.client_with(self.plan, SelecaoTrechosCDC(indices_ordenados=[1]), self.answer.model_copy())
                result, _ = consultar_cdc("Ajude com o caso", self.index, client, acao=action)
                self.assertIn(expected, client.models.generate_content.call_args.kwargs["contents"])
                self.assertEqual(result.texto_reclamacao, "")

    def test_original_case_remains_available_after_follow_up_actions(self):
        context = "Comprei um celular e ele chegou com a tela quebrada."
        draft = "Prezados, recebi um celular com a tela quebrada. Solicito uma solucao para esse problema e informacoes sobre o atendimento do pedido [numero]. Atenciosamente, [seu nome]."
        plan = self.plan.model_copy(update={"acao_sugerida": "reclamacao"})
        client = self.client_with(plan, SelecaoTrechosCDC(indices_ordenados=[1]), self.answer.model_copy(update={"texto_reclamacao": draft}))
        result, _ = consultar_cdc("Escreva a mensagem para a loja", self.index, client, contexto_caso=context)
        self.assertEqual(result.texto_reclamacao, draft)
        self.assertIn(context, client.models.generate_content.call_args_list[0].kwargs["contents"])
        self.assertIn(context, client.models.generate_content.call_args.kwargs["contents"])

    def test_factual_complaint_can_be_written_without_legal_sources(self):
        self.index.buscar.return_value = []
        answer = RespostaJuridicaCDC(fundamentacao_encontrada=False, resposta_orientativa="Rascunho factual sem fundamento legal confirmado.", texto_reclamacao="Prezados, informo que tive um problema com [produto ou servico]. Solicito [solucao desejada] e um retorno sobre o atendimento. Atenciosamente, [seu nome].")
        client = self.client_with(self.plan, answer)
        result, sources = consultar_cdc("Gere a reclamacao", self.index, client, acao="reclamacao")
        self.assertTrue(result.texto_reclamacao)
        self.assertFalse(result.fundamentacao_encontrada)
        self.assertEqual(result.artigos_citados, [])
        self.assertEqual(sources, [])

    def test_grounded_answer_missing_one_section_is_technical_failure(self):
        for field in ["resposta_didatica", "resposta_orientativa"]:
            with self.subTest(field=field):
                answer = self.answer.model_copy(update={field: "  "})
                client = self.client_with(self.plan, SelecaoTrechosCDC(indices_ordenados=[1]), answer)
                with self.assertRaises(ErroConsultaCDC):
                    consultar_cdc("Taxa de desperdicio", self.index, client)

    def test_real_pdf_retrieval_includes_material_rules(self):
        path = CDC_PDF_PATH
        if not path.is_file():
            self.skipTest("PDF oficial nao disponivel neste ambiente")
        with patch.object(IndiceHibridoCDC, "_carregar_ou_gerar_embeddings", return_value=None):
            index = IndiceHibridoCDC(extrair_chunks_cdc(str(path)), None)
        candidates = _recuperar_candidatos("sou obrigado a apagar o disperdicio no restaurante?", self.plan, index)
        articles = {item["artigo"] for item in candidates}
        self.assertIn("Art. 39", articles)
        self.assertIn("Art. 51", articles)
        self.assertLessEqual(len(candidates), 30)

    def test_embeddings_cache_uses_configured_data_directory(self):
        client = SimpleNamespace(models=SimpleNamespace(embed_content=Mock(
            return_value=SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0, 0.0])])
        )))
        with TemporaryDirectory() as directory:
            cache = Path(directory) / "cache"
            with patch("backend.rag_engine.CACHE_DIR", cache):
                index = IndiceHibridoCDC([self.rule], client)
                self.assertIsNotNone(index.embeddings)
                self.assertTrue(list(cache.glob("cache_embeddings_cdc_*.json")))
                IndiceHibridoCDC([self.rule], client)
                client.models.embed_content.assert_called_once()

    def test_follow_up_is_searched_as_standalone_question(self):
        plan = PlanoConsultaCDC(acao="consultar", pergunta_interpretada="Qual o prazo para reparar o celular com defeito?")
        client = self.client_with(plan, SelecaoTrechosCDC(indices_ordenados=[]))
        history = [{"role": "user", "content": "Meu celular chegou com defeito"}]
        consultar_cdc("E qual o prazo?", self.index, client, historico_conversa=history)
        planning_prompt = client.models.generate_content.call_args_list[0].kwargs["contents"]
        self.assertIn(history[0]["content"], planning_prompt)
        self.assertTrue(any(call.args[0] == plan.pergunta_interpretada for call in self.index.buscar.call_args_list))

    def test_partial_embedding_cache_resumes_after_quota_error(self):
        success = SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0, 0.0])])
        client = SimpleNamespace(models=SimpleNamespace(embed_content=Mock(side_effect=[success, RuntimeError("429 RESOURCE_EXHAUSTED"), success])))
        with TemporaryDirectory() as directory, patch.dict("os.environ", {"EMBEDDING_BATCH_SIZE": "1"}):
            with patch("backend.rag_engine.CACHE_DIR", Path(directory)):
                index = IndiceHibridoCDC([self.rule, self.noise], client)
                self.assertIsNone(index.embeddings)
                self.assertEqual(index.indexed_chunks, 1)
                self.assertEqual(index.index_error, "quota")
                index.retomar_indexacao()
                self.assertEqual(index.indexed_chunks, 2)
                self.assertEqual(index.embeddings.shape, (2, 2))
                self.assertEqual(client.models.embed_content.call_args.kwargs["contents"], [self.noise["text"]])

    def test_clarification_is_preserved_and_does_not_search(self):
        plan = PlanoConsultaCDC(acao="esclarecer", pergunta_interpretada="Uma cobranca nao especificada", esclarecimento="Qual taxa foi cobrada e por qual servico?")
        answer, sources = consultar_cdc("Tenho que pagar isso?", self.index, self.client_with(plan))
        self.assertEqual(answer.status, "esclarecimento")
        self.assertEqual(formatar_resposta_estruturada(answer), plan.esclarecimento)
        self.assertEqual(sources, [])
        self.index.buscar.assert_not_called()

    def test_labor_question_is_out_of_scope(self):
        plan = PlanoConsultaCDC(acao="fora_escopo", pergunta_interpretada="Qual o prazo de aviso previo na CLT?")
        answer, _ = consultar_cdc(plan.pergunta_interpretada, self.index, self.client_with(plan))
        self.assertEqual(answer.status, "fora_escopo")
        self.assertFalse(answer.fundamentacao_encontrada)
        self.index.buscar.assert_not_called()

    def test_no_candidates_is_insufficient_evidence_not_absence_from_document(self):
        self.index.buscar.return_value = []
        answer, _ = consultar_cdc("Taxa de desperdicio", self.index, self.client_with(self.plan))
        self.assertEqual(answer.status, "evidencia_insuficiente")
        self.assertIn("nao significa", answer.resposta_orientativa)

    def test_reranker_can_reject_irrelevant_candidates(self):
        client = self.client_with(self.plan, SelecaoTrechosCDC(indices_ordenados=[]))
        answer, sources = consultar_cdc("Taxa de desperdicio", self.index, client)
        self.assertEqual(answer.status, "evidencia_insuficiente")
        self.assertEqual(sources, [])
        self.assertEqual(client.models.generate_content.call_count, 2)

    def test_reranker_invalid_index_is_technical_failure(self):
        client = self.client_with(self.plan, SelecaoTrechosCDC(indices_ordenados=[999]))
        with self.assertRaises(ErroConsultaCDC):
            consultar_cdc("Taxa de desperdicio", self.index, client)

    def test_invented_citations_are_not_replaced_by_first_page(self):
        for field, value in [("paginas_pdf", [999]), ("artigos_citados", ["Art. 999"]), ("trecho_literal", "Uma taxa de desperdicio e sempre proibida")]:
            with self.subTest(field=field):
                answer = self.answer.model_copy(update={field: value})
                client = self.client_with(self.plan, SelecaoTrechosCDC(indices_ordenados=[1]), answer)
                result, _ = consultar_cdc("Taxa de desperdicio", self.index, client)
                self.assertEqual(result.status, "evidencia_insuficiente")
                self.assertEqual(result.paginas_pdf, [])
                self.assertEqual(result.artigos_citados, [])

    def test_answer_generation_timeout_is_technical_failure(self):
        client = self.client_with(self.plan, SelecaoTrechosCDC(indices_ordenados=[1]), TimeoutError("provider timeout"))
        with self.assertRaises(ErroConsultaCDC):
            consultar_cdc("Taxa de desperdicio", self.index, client)

    def test_pdf_soft_hyphen_does_not_invalidate_real_quote(self):
        source = dict(self.rule, text="Art. 39. exigir do consumidor vantagem mani\u00ad\nfestamente excessiva")
        self.assertTrue(_validar_fundamentacao(self.answer, [source]))
        source["text"] = "Art. 39. exigir do consumidor vantagem mani-\nfestamente excessiva"
        self.assertTrue(_validar_fundamentacao(self.answer, [source]))

    def test_invalid_structured_output_is_technical_failure(self):
        client = self.client_with(None)
        with self.assertRaises(ErroConsultaCDC):
            consultar_cdc("Taxa de desperdicio", self.index, client)

    def test_standard_questions_preserve_articles_and_pages(self):
        for article, page, question, excerpt in [
            ("Art. 18", 16, "Minha TV esta ha mais de trinta dias na assistencia", "Nao sendo o vicio sanado no prazo maximo de trinta dias"),
            ("Art. 49", 29, "Posso desistir da compra pela internet?", "O consumidor pode desistir do contrato no prazo de sete dias"),
            ("Art. 42", 26, "Paguei uma cobranca indevida. Tenho direito ao dobro?", "O consumidor cobrado em quantia indevida tem direito a repeticao do indebito"),
        ]:
            with self.subTest(article=article):
                index = Mock()
                index.buscar.return_value = [{"artigo": article, "page": page, "text": excerpt}]
                plan = PlanoConsultaCDC(acao="consultar", pergunta_interpretada=question)
                answer = RespostaJuridicaCDC(fundamentacao_encontrada=True, resposta_orientativa=excerpt, resposta_didatica="Voce tem direitos nessa situacao. Veja abaixo a regra aplicavel e os cuidados necessarios.", artigos_citados=[article], paginas_pdf=[page], trecho_literal=excerpt)
                result, _ = consultar_cdc(question, index, self.client_with(plan, SelecaoTrechosCDC(indices_ordenados=[0]), answer))
                self.assertTrue(result.fundamentacao_encontrada)
                self.assertEqual(result.artigos_citados, [article])
                self.assertEqual(result.paginas_pdf, [page])


if __name__ == "__main__":
    unittest.main()