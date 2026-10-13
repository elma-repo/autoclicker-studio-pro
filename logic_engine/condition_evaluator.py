"""Evaluador de condiciones sin eval() ni ejecución de código arbitrario."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
from .variable_store import VariableStore

@dataclass(frozen=True)
class ConditionResult:
    value: bool
    detail: str = ""

class ConditionEvaluator:
    """Evalúa árboles AND/OR/NOT y condiciones simples.

    image_checker(ruta, confidence, timeout_s) debe devolver True/False.
    Si no se registra un checker de imágenes, esa condición devuelve ERROR mediante
    una excepción clara en vez de fingir que la imagen no existe.
    """
    def __init__(
        self,
        variables: VariableStore,
        image_checker: Callable[[str, float, float], bool] | None = None,
        context: dict[str, Any] | None = None,
    ):
        self.variables = variables
        self.image_checker = image_checker
        self.context = context if context is not None else {}

    def evaluate(self, expression: dict[str, Any]) -> ConditionResult:
        if not isinstance(expression, dict):
            raise ValueError("La condición debe ser un objeto.")
        op = str(expression.get("op", "")).lower()
        if op == "and":
            children = self._children(expression)
            for child in children:
                result = self.evaluate(child)
                if not result.value:
                    return ConditionResult(False, f"AND: {result.detail or 'una condición es falsa'}")
            return ConditionResult(True, "Todas las condiciones AND se cumplieron")
        if op == "or":
            children = self._children(expression)
            for child in children:
                result = self.evaluate(child)
                if result.value:
                    return ConditionResult(True, f"OR: {result.detail or 'una condición se cumplió'}")
            return ConditionResult(False, "Ninguna condición OR se cumplió")
        if op == "not":
            result = self.evaluate(expression.get("condition", {}))
            return ConditionResult(not result.value, f"NOT: {result.detail}")
        if op == "image_visible":
            if self.image_checker is None:
                raise RuntimeError("No hay adaptador de visión conectado a image_checker.")
            image = str(expression.get("image", "")).strip()
            if not image:
                raise ValueError("La condición image_visible necesita 'image'.")
            confidence = float(expression.get("confidence", 0.8))
            timeout_s = max(0.0, float(expression.get("timeout_s", 0.0)))
            visible = bool(self.image_checker(image, confidence, timeout_s))
            return ConditionResult(visible, f"Imagen {'encontrada' if visible else 'no encontrada'}: {image}")
        if op == "variable":
            name = str(expression.get("name", ""))
            if not self.variables.exists(name):
                raise ValueError(f"La variable '{name}' no existe.")
            left = self.variables.get(name)
            operator = str(expression.get("operator", "=="))
            right = self._resolve_value(expression.get("value"))
            return ConditionResult(self._compare(left, operator, right), f"{name} {operator} {right!r}")
        if op == "context":
            name = str(expression.get("name", ""))
            if name not in self.context:
                raise ValueError(f"El dato de contexto '{name}' no existe.")
            left = self.context[name]
            operator = str(expression.get("operator", "=="))
            right = self._resolve_value(expression.get("value"))
            return ConditionResult(self._compare(left, operator, right), f"{name} {operator} {right!r}")
        raise ValueError(f"Operación de condición no soportada: '{op}'.")

    @staticmethod
    def _children(expression: dict[str, Any]) -> list[dict[str, Any]]:
        children = expression.get("conditions")
        if not isinstance(children, list) or not children:
            raise ValueError("AND/OR necesitan una lista no vacía en 'conditions'.")
        return children

    def _resolve_value(self, value: Any) -> Any:
        if isinstance(value, dict) and set(value) == {"variable"}:
            name = str(value["variable"])
            if not self.variables.exists(name):
                raise ValueError(f"La variable '{name}' no existe.")
            return self.variables.get(name)
        return value

    @staticmethod
    def _compare(left: Any, operator: str, right: Any) -> bool:
        operations = {
            "==": lambda: left == right,
            "!=": lambda: left != right,
            ">": lambda: left > right,
            ">=": lambda: left >= right,
            "<": lambda: left < right,
            "<=": lambda: left <= right,
            "contains": lambda: right in left,
            "in": lambda: left in right,
        }
        if operator not in operations:
            raise ValueError(f"Operador de comparación no permitido: '{operator}'.")
        try:
            return bool(operations[operator]())
        except TypeError as exc:
            raise ValueError(f"No se pueden comparar {left!r} y {right!r} con '{operator}'.") from exc
