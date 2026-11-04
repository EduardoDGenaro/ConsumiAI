"""Limites locais por processo; nao substituem autenticacao e gateway em producao."""

import threading
import time
from collections import deque


class RequestLimiter:
    def __init__(self, limit: int = 12, window: int = 60):
        self.limit = limit
        self.window = window
        self.hits: dict[str, deque] = {}
        self.lock = threading.Lock()

    def allow(self, client: str) -> bool:
        now = time.monotonic()
        with self.lock:
            for key in list(self.hits):
                queue = self.hits[key]
                while queue and queue[0] <= now - self.window:
                    queue.popleft()
                if not queue:
                    del self.hits[key]
            if client not in self.hits and len(self.hits) >= 4096:
                return False
            queue = self.hits.setdefault(client, deque())
            if len(queue) >= self.limit:
                return False
            queue.append(now)
            return True