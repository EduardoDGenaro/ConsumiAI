---
title: ConsumiAI
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# Consumer Defense Code (CDC) RAG Assistant - ConsumiAI

This repository contains the project scope and executable application designed to act as an intelligent consumer rights consultant, answering real inquiries grounded in Brazilian Federal Law 8,078/1990 and complementary regulatory decrees (official PROCON-SP 2025 edition).

---

## Legal Ingestion Architecture and Hybrid Retrieval

The project employs a structured legal document processing pipeline combined with hybrid retrieval:

- **Article-Aware Legal Chunking (`PyMuPDF` / `fitz`):** Extracts text from the official PDF while repairing end-of-line hyphenation, tracking statutory hierarchy (`TITLE`, `CHAPTER`, and `SECTION`), and segmenting units by article (`Art. X`). It keeps the *caput* attached to its paragraphs (`§`), clauses, and sub-clauses (even across page transitions) while preserving accurate page metadata (`page` and `pages`).
- **Semantic Vector Retrieval (`gemini-embedding-001` / `text-embedding-004`):** Indexes extracted document chunks using normalized embeddings (`RETRIEVAL_DOCUMENT`) with automatic disk-based caching (`cache_embeddings_cdc_*.json`), querying via cosine similarity (`RETRIEVAL_QUERY`).
- **Probabilistic Lexical Retrieval (`BM25Okapi`):** Scores exact terms, article numbers (`Art. 18`, `Art. 42`, `Art. 49`), and legal deadlines.
- **Ranking Fusion (`Reciprocal Rank Fusion - RRF`):** Merges semantic and lexical candidate rankings with score cutoff filters to reject questions that fall outside the scope of consumer law.
- **Contextual Query Reformulation:** Reformulates questions using recent conversation history when relevant, resolves ambiguity, and asks for clarification when critical details are missing. Topic changes cleanly reset context without inheriting irrelevant premises.
- **Expanded Multi-Search and LLM Reranking:** Queries the original question, the reformulated query, and up to three complementary search angles. Retrieves up to 20 candidates per query, unifies and deduplicates up to 30 candidates, and uses the model to select up to six based on legal relevance, including general governing principles.
- **Structured Output with Pydantic (`RespostaJuridicaCDC`):** Uses JSON Schema to enforce formal response categories: grounded legal guidance, clarification requests, insufficient evidence, or out-of-scope notifications. Distinguishes express statutory rules from legal interpretations, citing exact articles, PDF pages, and literal excerpts validated against retrieved chunks.
- **Technical Failure Isolation:** Network or schema parsing errors trigger a dedicated `ErroConsultaCDC` (yielding HTTP 502 at the API layer), preventing infrastructure glitches from being misconstrued as legal refusals.

---

## Project Structure

```text
backend/
   api.py                   FastAPI backend serving endpoints and compiled frontend
   rag_engine.py            Document extraction, retrieval, reranking, and synthesis
   paths.py                 Canonical project paths independent of execution directory
   requirements.txt         Python runtime dependencies
   security.py              Rate limiting, payload guards, and origin validations
   telemetry.py             Local execution trace recording and latency telemetry
frontend/
   index.html               Web application HTML entry point
   src/
      App.tsx                Chat interface, state management, and view components
      main.tsx               React application bootstrap
      styles.css             Tailwind styling, design tokens, and responsive layout
      assets/brand/
         consumiai.png        Optimized logo used in the application
   dist/                    Compiled assets produced by npm run build
data/
   documents/               Official CDC PDF source (PROCON-SP 2025)
   cache/                   Generated vector embedding caches and local metrics
docs/images/                Reference design visual specifications
legacy/streamlit_app.py     Original Streamlit exploratory prototype
notebooks/                  Jupyter and Google Colab experimentation notebooks
tests/                      Test suites for the RAG engine and API endpoints
```

The repository root maintains the README, Vite and TypeScript configs, package manifests, and environment templates (`.env.example`). Build artifacts and temporary caches are managed and excluded from version control.

---

## ConsumiAI Interface (React + Tailwind)

The primary interface is built with React 19, TypeScript, Tailwind CSS, and Lucide icons, connected to the Python RAG engine via FastAPI. Key features include local conversation history, responsive collapsible sidebar, actionable suggestion chips, response clipboard copying, structured legal citations, and PDF/TXT attachment support as case context. Voice dictation is supported via the browser Web Speech API when available.

### Local Setup and Execution

1. Install Python and frontend dependencies:
   ```bash
   python -m pip install -r backend/requirements.txt
   npm install
   ```

2. Configure `GEMINI_API_KEY` in a `.env` file at the project root:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   GEMINI_MODEL=gemini-3.1-flash-lite
   ```
   The API key remains securely on the server and is never exposed to the frontend.

3. Compile the frontend and start the unified server:
   ```bash
   npm run build
   python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
   ```

4. Open your browser at **http://127.0.0.1:8000**.

For development with hot-reload, run the backend on port 8000 and run `npm run dev` in a separate terminal. Vite will proxy all `/api` requests to the FastAPI backend.

---

## Architecture Details

### Dual Response Sections

Every grounded legal answer is generated with two synchronized perspectives within a single inference call:

- **In Plain Words:** An accessible, conversational explanation designed for non-lawyers, using clear language and identifying a concrete, practical next step. Displayed directly in the main message stream.
- **Detailed Legal Analysis:** Comprehensive statutory foundations, specific legal conditions, exceptions, article citations, and literal statutory extracts. Presented in an expandable section directly beneath the plain-language summary.

The model is explicitly instructed to maintain identical legal conclusions and uncertainty margins across both versions, preserving essential caveats. Clarification requests and out-of-scope notices use a concise single-block response.

### Shortcut Actions

The interface features guided action shortcuts:
- **Formal Complaint (`reclamacao`):** Generates a ready-to-use, first-person demand letter (`complaint_text`) complete with placeholders (e.g., `[Insert Invoice Number]`), separated from explanatory advice. Includes a dedicated **Copy Complaint** button.
- **Deadlines (`prazo`):** Identifies statutory time limits (e.g., Art. 26 notice periods, Art. 18 repair windows) and specifies their legal trigger events.
- **PROCON Guidance (`procon`):** Clarifies consumer protection agency workflows, distinguishing standard statutory protocol from administrative specifics.

### Evaluation and Automated Testing

Run the automated test suite locally:

```bash
npm run build
python -m pip install httpx pytest
python -m unittest discover -s tests -v
```

Tests evaluate misspelled legal queries, extraction of Articles 39 and 51 from the official PDF, follow-up conversation turns, clarification triggers, out-of-scope rejections, citation accuracy, and provider fallback behavior.

---

## Deployment Options

### Docker Deployment (Render, Cloud Run, Hugging Face Spaces)

The project includes a multi-stage [Dockerfile](Dockerfile) that builds the frontend assets with Node 20 and packages the backend with Python 3.12-slim:

```bash
# Build the Docker container locally
docker build -t consumiai .

# Run the container
docker run -p 7860:7860 -e GEMINI_API_KEY="your_api_key" consumiai
```

- **Hugging Face Spaces:** Set SDK to `docker` and configure `GEMINI_API_KEY` under Space Secrets. The application runs on port 7860 as an unprivileged user (UID 1000).
- **Render.com:** Deploy as a **Web Service** with the **Docker** runtime. Set the `GEMINI_API_KEY` environment variable in the Render dashboard.
- **Google Cloud Run:** Deploy using `gcloud run deploy consumiai --source . --region southamerica-east1 --memory 2Gi --timeout 300 --allow-unauthenticated`.

---

## Legacy Interfaces and Notebooks

### Streamlit Interface (Prototype)

To run the exploratory Streamlit interface:
```bash
streamlit run legacy/streamlit_app.py
```

### Google Colab Notebook

1. Open [colab.research.google.com](https://colab.research.google.com).
2. Upload `notebooks/chat_com_pdf_rag.ipynb` and `data/documents/codigo_defesa_consumidor.pdf`.
3. Add `GEMINI_API_KEY` to Colab Secrets.
4. Execute cells 1 through 7 sequentially.

---

## Reference Benchmark Cases

1. **Product Defect / 30-Day Cure Period:**
   - Query: Defective television left at authorized service center for more than 30 days.
   - Grounded Response: Art. 18, § 1 (product exchange, full refund, or proportional price abatement).
2. **Right of Regret (Distance Purchases):**
   - Query: Return of an online purchase within the statutory window.
   - Grounded Response: Art. 49 (7-day right of withdrawal with full monetary refund).
3. **Double Restitution for Improper Billing:**
   - Query: Consumer pays an incorrect, unwarranted charge on an invoice.
   - Grounded Response: Art. 42, sole paragraph (repetition of undue payment in double).
4. **Out of Scope Inquiry:**
   - Query: Employment contract termination under labor law (CLT).
   - Expected Response: Clear notification stating the matter is outside the Consumer Defense Code.
