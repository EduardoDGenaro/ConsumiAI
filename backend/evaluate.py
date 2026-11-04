"""Avaliacao explicita: python -m backend.evaluate --mode lexical (offline) ou --mode live."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from .paths import CDC_PDF_PATH, PROJECT_ROOT
from .rag_engine import IndiceHibridoCDC, PlanoConsultaCDC, _recuperar_candidatos, consultar_cdc, extrair_chunks_cdc

DATASET = PROJECT_ROOT / "data" / "evaluation" / "cases.json"


def load_cases(path: Path = DATASET) -> list[dict]:
    cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
    identifiers = set()
    for case in cases:
        if case["id"] in identifiers or not case["question"].strip():
            raise ValueError("Casos duplicados ou sem pergunta")
        identifiers.add(case["id"])
        review = case["review"]
        if review["status"] not in {"pending", "approved", "rejected"}:
            raise ValueError("Estado de revisao invalido")
        if review["status"] == "approved":
            if not all(review.get(key) for key in ["reviewer", "credential", "reviewed_at", "notes"]):
                raise ValueError("Aprovacao exige responsavel, qualificacao, data e justificativa")
            date.fromisoformat(review["reviewed_at"])
    return cases


def readability(text: str) -> dict:
    sentences = [sentence for sentence in re.split(r"[.!?\n]+", text) if sentence.strip()]
    words = re.findall(r"\w+", text)
    jargon = [term for term in ["iniquas", "iníquas", "indebito", "indébito", "onerosidade", "nulidade"] if term in text.lower()]
    return {"words": len(words), "average_words_per_sentence": round(len(words) / max(1, len(sentences)), 1),
            "jargon_flags": jargon, "note": "Indicadores mecanicos; nao comprovam clareza nem precisao juridica."}


def run_evaluation(cases: list[dict], mode: str = "lexical") -> dict:
    if mode == "live":
        from .api import get_engine
        client, index = get_engine()
    else:
        client = None
        index = IndiceHibridoCDC(extrair_chunks_cdc(str(CDC_PDF_PATH)), None)
        index.embeddings = None
    rows = []
    for case in cases:
        row = {"id": case["id"], "category": case["category"], "review_status": case["review"]["status"]}
        if mode == "lexical":
            original = index.buscar(case["question"], top_k=20)
            plan = PlanoConsultaCDC(acao="consultar", pergunta_interpretada=case["question"], consultas_busca=case["search_queries"])
            expanded = _recuperar_candidatos(case["question"], plan, index)
            expected = set(case["candidate_articles"])
            row.update({"original_candidate_hit": bool(expected & {item.get("artigo") for item in original}) if expected else None,
                        "curated_expansion_hit": bool(expected & {item.get("artigo") for item in expanded}) if expected else None,
                        "note": "Expansao usa consultas de desenvolvimento, NAO reformulacao real pelo LLM."})
        else:
            try:
                answer, sources = consultar_cdc(case["question"], index, client, historico_conversa=case["history"])
                row.update({"expected_status_match": answer.status == case["expected_status"],
                            "answer": answer.model_dump(), "retrieved_articles": [source.get("artigo") for source in sources],
                            "simple_readability": readability(answer.resposta_didatica),
                            "requires_human_review": True})
            except Exception as error:
                row["technical_error"] = type(error).__name__
        rows.append(row)
    hits = [row for row in rows if row.get("original_candidate_hit") is not None]
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "mode": mode, "cases": rows,
            "summary": {"total": len(rows), "approved": sum(row["review_status"] == "approved" for row in rows),
                        "original_candidate_hit_rate": sum(row["original_candidate_hit"] for row in hits) / len(hits) if hits else None,
                        "curated_expansion_hit_rate": sum(row["curated_expansion_hit"] for row in hits) / len(hits) if hits else None},
            "warning": "Resultados experimentais. Citacao valida nao garante interpretacao correta. Sem aprovacao humana nao ha referencia juridica validada."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["lexical", "live"], default="lexical")
    parser.add_argument("--approved-only", action="store_true")
    parser.add_argument("--require-reviewed", action="store_true")
    args = parser.parse_args()
    cases = load_cases()
    if args.require_reviewed and any(case["review"]["status"] != "approved" for case in cases):
        print("Avaliacao bloqueada: ha casos sem aprovacao juridica registrada.")
        return 2
    if args.approved_only:
        cases = [case for case in cases if case["review"]["status"] == "approved"]
    if not cases:
        print("Nao ha casos aprovados para avaliar.")
        return 2
    report = run_evaluation(cases, args.mode)
    directory = DATASET.parent / "reports"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}_{args.mode}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Relatorio: {path.relative_to(PROJECT_ROOT)}")
    print(report["warning"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())