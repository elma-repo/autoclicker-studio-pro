"""Almacén de variables aislado por ejecución del flujo."""
from __future__ import annotations
from threading import RLock
from typing import Any
import re

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

class VariableStore:
    def __init__(self, initial: dict[str, Any] | None = None):
        self._values: dict[str, Any] = {}
        self._lock = RLock()
        for name, value in (initial or {}).items():
            self.set(name, value)

    def set(self, name: str, value: Any) -> None:
        name = str(name)
        if not _NAME.fullmatch(name):
            raise ValueError(f"Nombre de variable no válido: {name!r}")
        with self._lock:
            self._values[name] = value

    def get(self, name: str, default: Any = None) -> Any:
        with self._lock:
            return self._values.get(name, default)

    def exists(self, name: str) -> bool:
        with self._lock:
            return name in self._values

    def delete(self, name: str) -> None:
        with self._lock:
            self._values.pop(name, None)

    def increment(self, name: str, amount: int | float = 1) -> int | float:
        with self._lock:
            current = self._values.get(name, 0)
            if not isinstance(current, (int, float)) or isinstance(current, bool):
                raise TypeError(f"La variable '{name}' no es numérica.")
            value = current + amount
            self.set(name, value)
            return value

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._values)
