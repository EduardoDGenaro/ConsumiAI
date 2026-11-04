"""Preparacao e retomada explicita do indice: python -m backend.index_documents."""

import json

from .api import get_engine


def main():
    _, index = get_engine()
    print(json.dumps({"indexed": index.indexed_chunks, "total": len(index.chunks),
                      "ready": index.embeddings is not None, "error": index.index_error}, indent=2))
    return 0 if index.embeddings is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())