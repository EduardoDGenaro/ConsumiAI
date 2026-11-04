"""
Interface Web Interativa do Assistente RAG do Codigo de Defesa do Consumidor (CDC)
Base normativa e chave de API integradas nativamente, sem necessidade de upload manual.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import streamlit as st
from google import genai

# Adiciona o diretorio raiz ao PYTHONPATH
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from backend.paths import CDC_PDF_PATH
from backend.rag_engine import (
    ErroConsultaCDC,
    IndiceHibridoCDC,
    RespostaJuridicaCDC,
    consultar_cdc,
    extrair_chunks_cdc,
    formatar_resposta_estruturada,
)

# Caminho nativo do PDF oficial do CDC (PROCON-SP 2025)
CAMINHO_PDF_NATIVO = str(CDC_PDF_PATH)

# Configuracao da pagina Streamlit
st.set_page_config(
    page_title="Consultor Inteligente do CDC - RAG Juridico",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# Estilizacao visual limpa e sem emojis
st.markdown(
    """
    <style>
    .status-badge {
        display: inline-block;
        padding: 4px 10px;
        font-size: 0.82rem;
        font-weight: 600;
        border-radius: 4px;
        margin-right: 6px;
    }
    .status-online {
        background-color: #e6f4ea;
        color: #137333;
        border: 1px solid #ceead6;
    }
    .status-warning {
        background-color: #fef7e0;
        color: #b06000;
        border: 1px solid #feefc3;
    }
    .legal-chip {
        display: inline-block;
        background-color: #e8f0fe;
        color: #1a73e8;
        padding: 2px 8px;
        border-radius: 3px;
        font-size: 0.85rem;
        font-weight: 500;
        margin-right: 4px;
    }
    .page-chip {
        display: inline-block;
        background-color: #f1f3f4;
        color: #3c4043;
        padding: 2px 8px;
        border-radius: 3px;
        font-size: 0.85rem;
        font-weight: 500;
        margin-right: 4px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def obter_chave_gemini_nativa() -> str:
    """Obtem a chave da API do Gemini de forma nativa e transparente."""
    # 1. Variavel de ambiente
    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if chave:
        return chave

    # 2. Arquivo .env local
    env_path = os.path.join(ROOT_DIR, ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for linha in f:
                    linha = linha.strip()
                    if linha.startswith("GEMINI_API_KEY="):
                        chave = linha.split("=", 1)[1].strip(" \"'")
                        if chave:
                            return chave
        except Exception:
            pass

    # 3. Streamlit secrets
    try:
        chave = st.secrets.get("GEMINI_API_KEY", "").strip()
        if chave:
            return chave
    except Exception:
        pass

    return ""


@st.cache_resource(show_spinner=False)
def carregar_base_cdc_nativa(caminho_pdf: str) -> list[dict[str, Any]]:
    """Extrai e estrutura os chunks juridicos nativos com cache em memoria."""
    if not os.path.exists(caminho_pdf):
        raise FileNotFoundError(f"Arquivo PDF do CDC nao encontrado em: {caminho_pdf}")
    return extrair_chunks_cdc(caminho_pdf)


@st.cache_resource(show_spinner=False)
def obter_indice_hibrido_nativo(caminho_pdf: str, api_key: str) -> IndiceHibridoCDC:
    """Inicializa o indice hibrido (Embeddings + BM25Okapi + RRF) com cache."""
    chunks = carregar_base_cdc_nativa(caminho_pdf)
    cliente = genai.Client(api_key=api_key) if api_key else None
    return IndiceHibridoCDC(chunks, cliente)


# Inicializacao do estado da sessao
if "messages" not in st.session_state:
    st.session_state.messages = []

api_key = obter_chave_gemini_nativa()

# Carregamento nativo da base documental e do indice
chunks_nativos = []
indice_hibrido = None
erro_carregamento = None

if not os.path.exists(CAMINHO_PDF_NATIVO):
    erro_carregamento = f"Documento nativo 'codigo_defesa_consumidor.pdf' ausente no diretorio {ROOT_DIR}."
else:
    try:
        chunks_nativos = carregar_base_cdc_nativa(CAMINHO_PDF_NATIVO)
        if api_key:
            indice_hibrido = obter_indice_hibrido_nativo(CAMINHO_PDF_NATIVO, api_key)
    except Exception as e:
        erro_carregamento = f"Falha ao carregar a base nativa do CDC: {e}"

# ==============================================================================
# BARRA LATERAL (STATUS NATIVO E CONFIGURACOES)
# ==============================================================================
with st.sidebar:
    st.markdown("### Consultor Juridico RAG")
    st.caption("Base normativa e autenticacao integradas nativamente.")

    st.markdown("#### Status do Sistema")
    if api_key:
        st.markdown(
            '<span class="status-badge status-online">[API CONECTADA]</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span class="status-badge status-warning">[CHAVE PENDENTE EM .ENV / AMBIENTE]</span>',
            unsafe_allow_html=True,
        )

    if chunks_nativos:
        artigos_count = sum(1 for c in chunks_nativos if str(c.get("artigo", "")).startswith("Art."))
        st.markdown(
            f"""
            <div style="font-size: 0.85rem; line-height: 1.4; margin-top: 8px;">
                <strong>Documento Nativo:</strong> CDC 2025 (PROCON-SP)<br>
                <strong>Extensao:</strong> 130 Paginas<br>
                <strong>Segmentacao:</strong> {len(chunks_nativos)} Chunks Normativos<br>
                <strong>Artigos Rastreados:</strong> {artigos_count} Artigos<br>
                <strong>Motor de Busca:</strong> Hibrido (Embeddings + BM25 + RRF)
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    st.markdown("#### Parametros")
    modelo_selecionado = st.selectbox(
        "Modelo de Geracao",
        ["gemini-3.5-flash-lite", "gemini-3.8-flash"],
        index=0,
        help="Modelos otimizados com suporte a saida estruturada Pydantic.",
    )

    if st.button("Limpar Historico da Conversa"):
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    st.caption("Lei Federal nº 8.078/1990 e decretos complementares.")

# ==============================================================================
# AREA PRINCIPAL
# ==============================================================================
st.markdown("## Consultor Inteligente do Codigo de Defesa do Consumidor")
st.markdown(
    "Orientacao juridica fundamentada exclusivamente no texto oficial da Lei 8.078/1990, com citacao expressa de artigos e paginas do documento."
)

if erro_carregamento:
    st.error(erro_carregamento)
    st.stop()

if not api_key:
    st.warning(
        "Para realizar consultas, defina a variavel de ambiente GEMINI_API_KEY ou configure-a no arquivo .env do projeto."
    )

# Atalhos para os 4 casos de teste obrigatorios
with st.expander("Casos de Teste Padronizados (Clique para preencher e testar)", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Caso 1: Direito de Arrependimento (Internet)"):
            st.session_state["pergunta_predefinida"] = (
                "Qual e o prazo para o consumidor desistir de um contrato feito pela internet ou telefone?"
            )
        if st.button("Caso 2: Prazo de Assistencia Tecnica (30 dias)"):
            st.session_state["pergunta_predefinida"] = (
                "Qual e o prazo maximo para o fornecedor sanar o vicio ou defeito de um produto?"
            )
    with col2:
        if st.button("Caso 3: Devolucao em Dobro de Cobranca"):
            st.session_state["pergunta_predefinida"] = (
                "O que o consumidor tem direito de receber caso seja cobrado em quantia indevida?"
            )
        if st.button("Caso 4: Fora do Escopo do CDC (Regra CLT)"):
            st.session_state["pergunta_predefinida"] = (
                "Qual e o prazo de aviso previo para demissao sem justa causa de acordo com a CLT?"
            )

# Exibicao do historico da conversa
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.write(msg["content"])
        else:
            dados: RespostaJuridicaCDC | None = msg.get("dados_estruturados")
            if dados is not None and dados.fundamentacao_encontrada:
                if dados.resposta_didatica:
                    st.markdown("#### Em palavras simples")
                    st.write(dados.resposta_didatica)
                    st.markdown("#### Analise detalhada")
                st.write(dados.resposta_orientativa)
                st.markdown("<div style='margin-top: 8px;'>", unsafe_allow_html=True)
                for art in dados.artigos_citados:
                    st.markdown(f'<span class="legal-chip">[{art}]</span>', unsafe_allow_html=True)
                for pag in dados.paginas_pdf:
                    st.markdown(f'<span class="page-chip">[Página {pag}]</span>', unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

                if dados.trecho_literal:
                    with st.expander("Citação Literal do CDC"):
                        st.markdown(f'*{dados.trecho_literal}*')

                trechos_recup = msg.get("trechos_recuperados", [])
                if trechos_recup:
                    with st.expander("Auditoria de Recuperacao Hibrida (Top Chunks)"):
                        for i, tr in enumerate(trechos_recup, start=1):
                            st.markdown(
                                f"**Chunk {i}** | Artigo: `{tr.get('artigo', 'Geral')}` | "
                                f"Página: `{tr.get('page')}` | RRF: `{tr.get('score_rrf', 0)}` | "
                                f"Cosseno: `{tr.get('score_cosine', 0)}` | BM25: `{tr.get('score_bm25', 0)}`"
                            )
                            st.text(tr.get("text", "")[:300] + ("..." if len(tr.get("text", "")) > 300 else ""))
            else:
                st.write(msg["content"])

# Entrada do chat
pergunta_prompt = st.chat_input("Digite sua dúvida sobre direitos do consumidor...")

if "pergunta_predefinida" in st.session_state and st.session_state["pergunta_predefinida"]:
    pergunta_prompt = st.session_state.pop("pergunta_predefinida")

if pergunta_prompt:
    if not api_key:
        st.error("Chave GEMINI_API_KEY nao configurada no ambiente ou no arquivo .env.")
        st.stop()

    if indice_hibrido is None:
        st.error("Indice de busca nao inicializado.")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": pergunta_prompt})
    with st.chat_message("user"):
        st.write(pergunta_prompt)

    with st.chat_message("assistant"):
        with st.spinner("Consultando base juridica nativa e sintetizando resposta..."):
            cliente = genai.Client(api_key=api_key)
            try:
                dados_resposta, trechos_recuperados = consultar_cdc(
                    pergunta=pergunta_prompt,
                    indice=indice_hibrido,
                    client_genai=cliente,
                    model_name=modelo_selecionado,
                    historico_conversa=st.session_state.messages[:-1],
                )
            except ErroConsultaCDC:
                st.error("Falha tecnica ao consultar o modelo. Isso nao indica falta de fundamento no CDC. Tente novamente em instantes.")
                st.stop()

            texto_exibicao = formatar_resposta_estruturada(dados_resposta)

            if dados_resposta.fundamentacao_encontrada:
                if dados_resposta.resposta_didatica:
                    st.markdown("#### Em palavras simples")
                    st.write(dados_resposta.resposta_didatica)
                    st.markdown("#### Analise detalhada")
                st.write(dados_resposta.resposta_orientativa)
                st.markdown("<div style='margin-top: 8px;'>", unsafe_allow_html=True)
                for art in dados_resposta.artigos_citados:
                    st.markdown(f'<span class="legal-chip">[{art}]</span>', unsafe_allow_html=True)
                for pag in dados_resposta.paginas_pdf:
                    st.markdown(f'<span class="page-chip">[Página {pag}]</span>', unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

                if dados_resposta.trecho_literal:
                    with st.expander("Citação Literal do CDC"):
                        st.markdown(f'*{dados_resposta.trecho_literal}*')

                if trechos_recuperados:
                    with st.expander("Auditoria de Recuperacao Hibrida (Top Chunks)"):
                        for i, tr in enumerate(trechos_recuperados, start=1):
                            st.markdown(
                                f"**Chunk {i}** | Artigo: `{tr.get('artigo', 'Geral')}` | "
                                f"Página: `{tr.get('page')}` | RRF: `{tr.get('score_rrf', 0)}` | "
                                f"Cosseno: `{tr.get('score_cosine', 0)}` | BM25: `{tr.get('score_bm25', 0)}`"
                            )
                            st.text(tr.get("text", "")[:300] + ("..." if len(tr.get("text", "")) > 300 else ""))
            else:
                st.write(texto_exibicao)

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": texto_exibicao,
                "dados_estruturados": dados_resposta,
                "trechos_recuperados": trechos_recuperados,
            }
        )
