"""Cache TTL em memória para a Central de Conversão (Render single-instance)."""

from __future__ import annotations

import time
from threading import Lock
from typing import Any, TypeVar

T = TypeVar("T")


class TtlCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            value, expires_at = item
            if time.monotonic() >= expires_at:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        with self._lock:
            self._store[key] = (value, time.monotonic() + max(0.1, ttl_seconds))

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def delete_prefix(self, prefix: str) -> None:
        with self._lock:
            for key in [k for k in self._store if k.startswith(prefix)]:
                self._store.pop(key, None)

    def should_run(self, key: str, min_interval_seconds: float) -> bool:
        """Throttle: True se já passou o intervalo desde a última execução marcada."""
        marker = f"throttle:{key}"
        with self._lock:
            item = self._store.get(marker)
            now = time.monotonic()
            if item is not None and now < item[1]:
                return False
            self._store[marker] = (True, now + max(0.1, min_interval_seconds))
            return True


# Respostas HTTP curtas (evita reprocessar sync a cada poll do front).
mensagens_cache = TtlCache()
conversas_cache = TtlCache()
# Controle de sync NSAgent (não precisa a cada request).
sync_throttle = TtlCache()

MENSAGENS_TTL = 6.0
CONVERSAS_TTL = 8.0
SYNC_MSG_INTERVAL = 12.0
SYNC_WORKSPACE_INTERVAL = 20.0


def invalidate_conversa(conversa_id: str, workspace_id: str | None = None) -> None:
    mensagens_cache.delete(f"mensagens:{conversa_id}")
    if workspace_id:
        conversas_cache.delete(f"conversas:{workspace_id}")
    else:
        conversas_cache.delete_prefix("conversas:")
