"""Registro de acciones conectable al código actual de AutoClicker Studio."""
from __future__ import annotations
from typing import Any, Callable

ActionHandler = Callable[[dict[str, Any], Any], Any]

class ActionRegistry:
    def __init__(self):
        self._handlers: dict[str, ActionHandler] = {}

    def register(self, name: str, handler: ActionHandler) -> None:
        name = str(name).strip()
        if not name:
            raise ValueError("El nombre de la acción no puede estar vacío.")
        if not callable(handler):
            raise TypeError("El manejador de la acción debe ser invocable.")
        self._handlers[name] = handler

    def unregister(self, name: str) -> None:
        self._handlers.pop(name, None)

    def has(self, name: str) -> bool:
        return name in self._handlers

    def execute(self, name: str, params: dict[str, Any], context: Any = None) -> Any:
        handler = self._handlers.get(name)
        if handler is None:
            raise KeyError(f"No hay una acción registrada con el nombre '{name}'.")
        return handler(params, context)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))
