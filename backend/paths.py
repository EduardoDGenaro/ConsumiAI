"""Caminhos compartilhados, independentes do diretorio de execucao."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CDC_PDF_PATH = PROJECT_ROOT / "data" / "documents" / "codigo_defesa_consumidor.pdf"
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"