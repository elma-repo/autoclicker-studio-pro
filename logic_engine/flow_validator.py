"""Validación estática de flujos antes de permitir su ejecución."""
from __future__ import annotations
from dataclasses import dataclass
from .flow_model import Flow

KNOWN_NODE_TYPES = {
    "start", "end", "condition", "action", "wait",
    "set_variable", "loop", "switch",
}

@dataclass
class ValidationIssue:
    message: str
    node_id: str | None = None
    severity: str = "error"

class FlowValidationError(ValueError):
    def __init__(self, issues: list[ValidationIssue]):
        self.issues = issues
        super().__init__("\n".join(
            f"{issue.node_id + ': ' if issue.node_id else ''}{issue.message}"
            for issue in issues if issue.severity == "error"
        ))

def validate_flow(flow: Flow, *, max_nodes: int = 1000) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not flow.name.strip():
        issues.append(ValidationIssue("El flujo necesita un nombre."))
    if not flow.nodes:
        issues.append(ValidationIssue("El flujo no contiene bloques."))
        return issues
    if len(flow.nodes) > max_nodes:
        issues.append(ValidationIssue(f"El flujo supera el máximo de {max_nodes} bloques."))
    ids = [node.id for node in flow.nodes]
    if any(not node_id for node_id in ids):
        issues.append(ValidationIssue("Todos los bloques deben tener un identificador."))
    if len(ids) != len(set(ids)):
        issues.append(ValidationIssue("Hay identificadores de bloque duplicados."))
    node_map = flow.node_map()
    if flow.start_node not in node_map:
        issues.append(ValidationIssue(f"El bloque inicial '{flow.start_node}' no existe."))

    for node in flow.nodes:
        if node.type not in KNOWN_NODE_TYPES:
            issues.append(ValidationIssue(f"Tipo de bloque desconocido: '{node.type}'.", node.id))
        if node.type == "start" and node.id != flow.start_node:
            issues.append(ValidationIssue("Solo el bloque indicado por start_node puede ser el inicio.", node.id))
        if node.type == "condition" and not isinstance(node.params.get("condition"), dict):
            issues.append(ValidationIssue("El bloque condition necesita params.condition.", node.id))
        if node.type == "action" and not str(node.params.get("action", "")).strip():
            issues.append(ValidationIssue("El bloque action necesita params.action.", node.id))
        if node.type == "wait":
            try:
                seconds = float(node.params.get("seconds", 0))
                if seconds < 0:
                    raise ValueError
            except (TypeError, ValueError):
                issues.append(ValidationIssue("params.seconds debe ser un número >= 0.", node.id))
        if node.type == "loop":
            try:
                maximum = int(node.params.get("max_iterations", 0))
                if maximum < 1:
                    raise ValueError
            except (TypeError, ValueError):
                issues.append(ValidationIssue("El bloque loop necesita max_iterations >= 1.", node.id))

        refs = [node.next, node.on_true, node.on_false, node.on_timeout, node.on_error]
        refs.extend(node.branches.values())
        for ref in refs:
            if ref is not None and ref not in node_map:
                issues.append(ValidationIssue(f"La conexión apunta al bloque inexistente '{ref}'.", node.id))

    if flow.start_node in node_map and node_map[flow.start_node].type != "start":
        issues.append(ValidationIssue("El bloque inicial debe ser de tipo 'start'.", flow.start_node))
    return issues

def assert_valid_flow(flow: Flow) -> None:
    errors = [issue for issue in validate_flow(flow) if issue.severity == "error"]
    if errors:
        raise FlowValidationError(errors)
