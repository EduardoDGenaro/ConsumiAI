# Assistente RAG do Código de Defesa do Consumidor (CDC)

Este repositório contém o escopo do projeto e o notebook Jupyter executável projetado para atuar como um consultor inteligente de direitos do consumidor, respondendo a dúvidas reais com base na Lei 8.078/1990 e decretos complementares (edição oficial PROCON-SP 2025).

---

## Arquitetura de Ingestão Jurídica e Busca Híbrida Real

O projeto utiliza um pipeline de processamento jurídico estruturado aliado a recuperação híbrida:
- **Chunking Jurídico por Artigos (`PyMuPDF` / `fitz`):** Extrai o PDF corrigindo hifenizações de fim de linha, rastreia a hierarquia normativa (`TÍTULO`, `CAPÍTULO` e `SEÇÃO`) e segmenta o texto por unidade de artigo (`Art. X`), mantendo o *caput* unido aos seus parágrafos (`§`), incisos e alíneas (mesmo na virada de página) e preservando o metadado exato de página (`page` e `pages`).
- **Busca Semântica Vetorial (`gemini-embedding-001`):** Indexa todos os chunks extraídos do PDF com embeddings normalizados (`RETRIEVAL_DOCUMENT`) e cache automático em disco (`cache_embeddings_cdc_*.json`), consultando por similaridade de cosseno (`RETRIEVAL_QUERY`).
- **Busca Lexical Probabilística (`BM25Okapi`):** Pontua termos exatos, números de artigos (`Art. 18`, `Art. 42`, `Art. 49`) e prazos legais.
- **Fusão de Ranking (`Reciprocal Rank Fusion - RRF`):** Unifica os resultados semânticos e lexicais com filtro de corte para recusar perguntas fora do escopo do CDC.
- **Interpretacao Contextual:** Reformula a pergunta com o historico recente quando pertinente, corrige erros pelo contexto e pede esclarecimento quando falta informacao essencial. Uma mudanca de assunto nao deve herdar o tema anterior.
- **Busca Ampliada e Reranking:** Consulta a pergunta original, a reformulada e ate tres buscas complementares. Recupera ate 20 candidatos por busca, combina e deduplica ate 30 trechos e usa o modelo para selecionar ate seis por relevancia juridica, incluindo regras gerais aplicaveis.
- **Saída Estruturada com Pydantic (`RespostaJuridicaCDC`):** Utiliza JSON Schema e diferencia resposta fundamentada, esclarecimento, evidencia insuficiente e fora de escopo. Distingue regra expressa de interpretacao juridica e informa limitacoes. Confere artigos, paginas e citacao literal contra os trechos selecionados, normalizando hifenizacao do PDF sem inventar paginas substitutas.
- **Falhas Tecnicas Separadas:** Falhas de comunicacao ou saida estruturada invalida geram `ErroConsultaCDC` e HTTP 502 na API, nao uma recusa juridica.

---

## Arquivos do Projeto

```text
backend/
   api.py                   API FastAPI e publicacao da interface
   rag_engine.py            Extracao, busca, selecao e respostas do RAG
   paths.py                 Caminhos compartilhados do projeto
   requirements.txt         Dependencias Python
frontend/
   index.html               Entrada da aplicacao web
   src/
      App.tsx                Chat e componentes da interface
      main.tsx               Inicializacao do React
      styles.css             Estilos e responsividade
      assets/brand/
         consumiai.png        Logo otimizada usada na interface
         original.jfif        Imagem original fornecida
   dist/                    Build gerado por npm run build
data/
   documents/               PDF oficial do CDC (PROCON-SP 2025)
   cache/                   Cache gerado dos embeddings
docs/images/               Referencias visuais do projeto
legacy/streamlit_app.py    Interface anterior em Streamlit
notebooks/                Experimentos em Jupyter e Colab
tests/                    Testes do motor RAG e da API
```

A raiz mantem README, configuracoes do Vite/TypeScript, manifestos npm e
`.env`/`.env.example`. `node_modules/`, builds e caches sao gerados e ignorados
pelo Git. O notebook e a interface Streamlit anteriores foram preservados.

---

## Interface ConsumiAI (React + Tailwind)

A interface principal utiliza React, TypeScript, Tailwind CSS e icones Lucide,
conectados ao mesmo motor RAG por uma API FastAPI. Inclui historico local,
sidebar recolhivel no celular, sugestoes clicaveis, copia das respostas,
citacoes legais e anexos PDF/TXT como contexto do relato. O ditado depende
do suporte e da permissao de microfone do navegador.

1. Instale as dependencias Python e frontend:
   ```powershell
   py -3.13 -m pip install -r backend/requirements.txt
   npm install
   ```
2. Configure `GEMINI_API_KEY` no arquivo `.env` da raiz. Opcionalmente,
   configure `GEMINI_MODEL` para substituir o modelo padrao do projeto.
   A chave permanece exclusivamente no servidor.
3. Compile a interface e inicie a aplicacao integrada:
   ```powershell
   npm run build
   py -3.13 -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
   ```
4. Acesse **http://127.0.0.1:8000**.

Em outros sistemas, substitua `py -3.13` pelo comando do seu interpretador
Python. Para desenvolver com recarregamento automatico, mantenha a API na
porta 8000 e execute `npm run dev` em outro terminal; o Vite encaminha
`/api` para o servidor Python. Abra o endereco informado pelo Vite.

### Arquivos da nova interface

- `frontend/src/App.tsx`: componentes `Sidebar`, `ChatMessage`, `SuggestionChip`
  e `ChatInput`, com estados de envio, erro, selecao e armazenamento.
- `frontend/src/styles.css`: estilos responsivos e tokens visuais do ConsumiAI.
- `frontend/src/assets/brand/`: logo fornecida, original e versao otimizada.
- `backend/api.py`: API de consultas, leitura de anexos e publicacao de `frontend/dist`.
- `backend/paths.py`: caminhos do PDF, do cache e do build, independentes da pasta atual.
- `tests/test_server.py`: testes locais da API, sem chamadas pagas ao Gemini.

O historico e salvo neste navegador, nao em uma conta autenticada. Excluir
uma conversa remove seus dados locais. O anexo e enviado ao servidor e ao
modelo como parte do relato; ele nao substitui a base normativa oficial.
Limites: 5 MB e 12.000 caracteres extraidos; PDFs digitalizados sem texto
precisam de OCR externo. A interface abre com uma conversa de exemplo
identificada. O indicador de conexao verifica a presenca da chave e do PDF,
nao a disponibilidade do provedor nem a validade da chave.

O badge informa **PROCON-SP 2025**, correspondente ao PDF fornecido.
Ele nao alega uma revisao normativa de 2026 sem um documento atualizado.

### Duas Secoes de Resposta

Novas respostas fundamentadas sao geradas com duas versoes na mesma chamada:

- **Em palavras simples:** explicacao para quem nao conhece direito, com
   frases curtas, palavras comuns e um proximo passo pratico. Fica aberta no chat.
- **Analise detalhada:** fundamentos, aplicacao ao caso, condicoes, limitacoes,
   artigos e citacoes. Fica em uma secao expansivel logo abaixo da explicacao simples.

O modelo e instruido a manter as mesmas conclusoes e incertezas nas duas
versoes, sem remover ressalvas importantes para simplificar. Esclarecimentos,
assuntos fora do escopo e falta de evidencia continuam com uma unica mensagem
curta. O historico antigo permanece no formato original; nao e reescrito.

A API retorna `simple_content` e `detailed_content`, alem de `content` com o
texto completo para copia e historico. A versao Streamlit tambem exibe ambas
as secoes. Isso nao adiciona uma chamada ao Gemini, embora a geracao de duas
versoes possa aumentar o numero de tokens de saida.

### Validacao

Os atalhos do chat possuem acoes especificas: `reclamacao`, `prazo` e `procon`.
O primeiro entrega `complaint_text`, uma mensagem em primeira pessoa pronta
para revisar, preencher e copiar, separada das orientacoes. O botao **Copiar
reclamacao** copia apenas a carta. Nada e enviado automaticamente a empresa.
Dados ausentes ficam entre colchetes; nao sao inventados nomes, datas,
valores ou protocolos. O relato de referencia e preservado separadamente
das perguntas dos atalhos. Um rascunho factual pode ser gerado sem fundamento
legal confirmado, mas nao deve afirmar ilegalidade ou citar normas nesse caso.

O atalho de prazo distingue as regras pertinentes e seu marco inicial; o de
PROCON separa orientacoes gerais de procedimentos locais nao verificados.
Nao sao inventados canais, prazos de atendimento ou garantias de resultado.

```powershell
npm run build
py -3.13 -m pip install httpx
py -3.13 -m unittest discover -s tests -v
```

Os testes incluem a pergunta com erros de digitacao sobre taxa de desperdicio
em restaurante, recuperacao dos artigos 39 e 51 no PDF real sem embeddings,
perguntas de continuacao, esclarecimento, materias fora do escopo, citacoes
invalidas e falhas do provedor. A geracao nos testes automatizados e simulada;
eles nao comprovam a qualidade de todas as respostas reais do modelo.

### Custo, Limites e Diagnostico

#### Preparacao e Retomada do Indice

```powershell
py -3.13 -m backend.index_documents
```

O motor usa lotes de dois trechos por padrao (`EMBEDDING_BATCH_SIZE`, de 1 a 5),
salva cada lote com substituicao atomica e valida modelo, corpus, dimensoes e
normalizacao dos vetores. Se houver erro de cota, o comando termina com codigo
1 e preserva o progresso. Execute novamente depois de liberar a cota; ele
continua do lote pendente. Nao ha repeticao automatica infinita nem garantia
de ultrapassar limites do provedor. Prefira preparar antes de iniciar a API.
Para atualizar um servidor ja iniciado com indice parcial, reinicie-o apos a preparacao.

#### Avaliacao e Revisao Juridica

```powershell
py -3.13 -m backend.evaluate --mode lexical
py -3.13 -m backend.evaluate --mode live
py -3.13 -m backend.evaluate --approved-only
py -3.13 -m backend.evaluate --require-reviewed
```

`lexical` e offline. `live` consome a API e deve ser usado deliberadamente.
Os 15 casos em `data/evaluation/cases.json` sao casos de desenvolvimento,
incluindo exemplos sinteticos, ambiguidades, contexto e erros de digitacao.
Todos comecam pendentes de revisao. Artigos candidatos e estados esperados
NAO sao referencias juridicas aprovadas. A expansao offline usa consultas
predefinidas, nao o planejamento real do LLM. Os relatorios ficam em
`data/evaluation/reports/`, fora do Git.

O processo e a rubrica de revisao estao em [docs/legal-review.md](docs/legal-review.md).
E necessario um profissional qualificado para revisar, justificar e registrar
a aprovacao. O software nao autentica credenciais nem substitui essa revisao.

#### Progresso, Fontes e Privacidade

O chat usa `POST /api/chat/stream` (NDJSON) com eventos de etapas reais e
resultado ou erro terminal. `POST /api/chat` permanece disponivel sem streaming.
O botao de nova tentativa reutiliza o relato e nao duplica a pergunta.
As referencias ficam em uma secao independente e recolhida, **Fontes utilizadas**,
em cada resposta. Ela reune artigos, paginas, citacao literal e, quando informado,
o modo de busca. As paginas abrem `/api/sources/cdc.pdf#page=N`, com a edicao da fonte.
O navegador pode baixar o PDF se nao tiver visualizador integrado.

O chat exibe um aviso discreto sobre o envio de relatos e anexos ao Google,
sem checkbox ou bloqueio de envio. O frontend informa `X-Privacy-Notice: displayed`
nas chamadas POST. Esse cabecalho indica exibicao de aviso, NAO consentimento
juridico nem autenticacao. `X-Data-Consent: accepted` continua aceito por
compatibilidade com clientes anteriores. Nao envie dados sensiveis. O backend
nao persiste relatos ou anexos, mas o navegador salva o historico e o provedor
de IA pode manter os dados segundo sua politica. O ditado pode usar um servico
de voz do navegador. Apagar o historico remove os dados locais, nao os ja
enviados ao provedor. A interface nao registra consentimento explicito; avalie a
base legal e os requisitos de privacidade antes de publicar o servico.

Requisicoes POST aceitam apenas origens configuradas em `ALLOWED_ORIGINS`,
exigem `Content-Length` e limitam o corpo a 256 KiB no chat e 5 MiB no anexo.
O limite e de 12 envios/minuto por cliente e duas consultas simultaneas por
processo. As contagens de clientes ficam somente em memoria. Nao ha controle
distribuido entre processos; atras de proxy, configure corretamente o IP de
origem para evitar agrupar todos os usuarios. Para publicar, ainda sao
necessarios HTTPS, autenticacao quando aplicavel, gateway com limites
distribuidos e analise de privacidade/seguranca. A interface Streamlit e o
notebook continuam experimentais e nao devem ser expostos como servico publico.

Interromper a conexao ou exceder o tempo de espera da interface nao cancela
necessariamente uma chamada ja enviada ao Google. Uma tentativa manual pode
gerar consumo adicional; nao ha repeticao automatica de consultas pagas.

#### Metricas Locais

```powershell
py -3.13 -m backend.telemetry
```

O SQLite em `data/cache/metrics.sqlite3` armazena identificador aleatorio,
data, modelo, estado, duracao total/por etapa, tentativas, tokens informados
e uso de fallback. Nao grava perguntas, respostas, anexos, IPs nem chaves.
Registros com mais de 30 dias sao eliminados quando chegam novas metricas.
O resumo considera as ultimas mil consultas. O banco e local, sem endpoint
publico de metricas. Os logs de acesso do servidor podem registrar IPs e
precisam de politica de retencao propria na implantacao.

Configure os precos efetivos em `GENERATION_INPUT_USD_PER_MILLION` e
`GENERATION_OUTPUT_USD_PER_MILLION` para estimar custo de geracao. Sem precos
ou metadados completos, o custo fica desconhecido, nao zero. A estimativa nao
inclui embeddings, impostos, descontos de cache nem outras regras comerciais;
nao substitui o faturamento do provedor.

Uma consulta completa usa tres chamadas de geracao: planejamento da busca,
selecao dos trechos e resposta. Esclarecimentos e perguntas fora do escopo
podem encerrar antes. As buscas hibridas tambem usam embeddings de consulta
quando o indice vetorial esta disponivel. Esse fluxo pode aumentar latencia
e consumo em relacao a uma unica chamada de resposta.

Se a cota de embeddings for excedida ou a indexacao falhar, o motor registra
um aviso e utiliza BM25. Nao confunda esse modo lexical com busca semantica
ativa. Verifique a cota do provedor se aparecer `429 RESOURCE_EXHAUSTED`.
Falhas nas etapas de geracao sao exibidas como erro tecnico. Os logs do novo
fluxo registram quantidades de candidatos e trechos, sem registrar o relato.

Interpretacao de regras gerais nao equivale a parecer juridico nem comprova
que uma pratica e permitida ou proibida. O modelo deve explicitar limites;
aviso previo de uma taxa nao e tratado como prova suficiente de validade.

## Interface Anterior (Streamlit)

1. **Instalação das Dependências:**
   ```bash
   pip install -r backend/requirements.txt
   ```

2. **Configuração Nativa da Chave da API:**
   Crie ou edite o arquivo `.env` na raiz do projeto:
   ```env
   GEMINI_API_KEY=sua_chave_aqui
   ```
   *(Ou configure via variável de ambiente do sistema `$env:GEMINI_API_KEY="sua_chave"`)*

3. **Inicialização do Servidor Streamlit:**
   ```bash
   streamlit run legacy/streamlit_app.py
   ```

4. **Uso da Interface:**
   - O documento oficial em `data/documents/codigo_defesa_consumidor.pdf` e a chave da raiz são carregados nativamente na inicialização.
   - Não há formulários manuais de upload nem campos para colar chaves.
   - Utilize a área de chat para enviar dúvidas em linguagem natural ou acione os botões de **Casos de Teste Padronizados** para conferência imediata.
   - Analise os dispositivos legais e páginas citadas, além do painel de auditoria com os scores de similaridade de cada trecho normativo.

---

## Como Executar no Google Colab

1. **Upload no Colab:**
   - Acesse [colab.research.google.com](https://colab.research.google.com).
   - Envie o arquivo `notebooks/chat_com_pdf_rag.ipynb` e o documento `data/documents/codigo_defesa_consumidor.pdf` para a pasta atual do Colab.
   - Localmente, o notebook encontra o PDF em `data/documents/` e o `.env` na raiz, mesmo quando iniciado pela pasta `notebooks/`.
2. **Configuração de Segredos:**
   - No Colab, clique no ícone de chave (**Secrets**) na barra lateral esquerda.
   - Adicione `GEMINI_API_KEY` com o valor da chave obtida no [Google AI Studio](https://aistudio.google.com/app/apikey) e habilite o acesso para o notebook.
3. **Execução:**
   - Execute as células de 1 a 7 sequencialmente. O documento e a chave serão identificados nativamente, sem telas de upload interativo.

---

## Casos de Teste Mapeados

1. **Teste 1 (Vício do produto / Prazo de 30 dias):**
   - Pergunta: TV com defeito deixada há mais de 30 dias na assistência técnica.
   - Resposta esperada: Art. 18, § 1º (troca, restituição do valor pago ou abatimento do preço), citando a **Página 16**.
2. **Teste 2 (Direito de arrependimento):**
   - Pergunta: Devolução de compra realizada pela internet dentro do prazo legal.
   - Resposta esperada: Art. 49 (direito de arrependimento em até 7 dias com devolução integral e atualizada), citando a **Página 29**.
3. **Teste 3 (Cobrança indevida em dobro):**
   - Pergunta: Fatura com cobrança indevida já quitada pelo consumidor.
   - Resposta esperada: Art. 42, parágrafo único (repetição do indébito em dobro corrigido monetariamente), citando a **Página 26**.
4. **Teste 4 (Fora do escopo / Negativa):**
   - Pergunta: Dúvida sobre rescisão trabalhista sob a CLT.
   - Resposta esperada: `"Não encontrei essa informação no documento."`
