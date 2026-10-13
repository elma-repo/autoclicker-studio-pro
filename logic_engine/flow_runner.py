"""Intérprete de flujos con cancelación, límites y registro de ejecución."""
from __future__ import annotations
from dataclasses import dataclass, field
from threading import Event
from time import monotonic
from typing import Any, Callable

from .action_registry import ActionRegistry
from .condition_evaluator import ConditionEvaluator
from .flow_model import Flow, FlowNode
from .flow_validator import assert_valid_flow
from .variable_store import VariableStore

class FlowExecutionError(RuntimeError):
    pass

@dataclass
class FlowRunResult:
    status: str
    steps: int
    elapsed_s: float
    last_node: str | None = None
    variables: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

class FlowRunner:
    def __init__(
        self,
        actions: ActionRegistry,
        condition_evaluator_factory: Callable[[VariableStore, dict[str, Any]], ConditionEvaluator],
        *,
        logger: Callable[[str, str], None] | None = None,
        max_steps: int = 10000,
        max_runtime_s: float = 3600.0,
    ):
        self.actions = actions
        self.condition_evaluator_factory = condition_evaluator_factory
        self.logger = logger or (lambda message, level="info": None)
        self.max_steps = max(1, int(max_steps))
        self.max_runtime_s = max(0.1, float(max_runtime_s))

    def run(self, flow: Flow, stop_event: Event | None = None) -> FlowRunResult:
        assert_valid_flow(flow)
        stop_event = stop_event or Event()
        started = monotonic()
        variables = VariableStore(flow.variables)
        context: dict[str, Any] = {
            "started_at": started,
            "elapsed_s": 0.0,
            "last_condition": None,
            "last_action_result": None,
            "last_error": None,
        }
        evaluator = self.condition_evaluator_factory(variables, context)
        nodes = flow.node_map()
        current_id: str | None = flow.start_node
        steps = 0
        loop_counts: dict[str, int] = {}
        status = "completed"
        error = None

        def log(message: str, level: str = "info") -> None:
            try:
                self.logger(message, level)
            except Exception:
                pass

        try:
            while current_id is not None:
                if stop_event.is_set():
                    status = "cancelled"
                    break
                elapsed = monotonic() - started
                context["elapsed_s"] = elapsed
                if elapsed >= self.max_runtime_s:
                    raise FlowExecutionError(f"Se superó el tiempo máximo ({self.max_runtime_s:g} s).")
                steps += 1
                if steps > self.max_steps:
                    raise FlowExecutionError(f"Se superó el máximo de pasos ({self.max_steps}).")
                node = nodes[current_id]
                log(f"Bloque: {node.name or node.id} [{node.type}]", "process")
                current_id = self._execute_node(
                    node, evaluator, variables, context, stop_event, loop_counts
                )
            if status == "completed":
                log("Flujo completado.", "ok")
        except Exception as exc:
            status = "error"
            error = str(exc)
            context["last_error"] = error
            log(f"Error en el flujo: {error}", "err")
        return FlowRunResult(
            status=status,
            steps=steps,
            elapsed_s=monotonic() - started,
            last_node=node.id if "node" in locals() else None,
            variables=variables.snapshot(),
            error=error,
        )

    def _execute_node(
        self,
        node: FlowNode,
        evaluator: ConditionEvaluator,
        variables: VariableStore,
        context: dict[str, Any],
        stop_event: Event,
        loop_counts: dict[str, int],
    ) -> str | None:
        params = node.params
        if node.type == "start":
            return node.next
        if node.type == "end":
            return None
        if node.type == "condition":
            expression = params["condition"]
            result = evaluator.evaluate(expression)
            context["last_condition"] = result.value
            try:
                self.logger(
                    f"{node.name or node.id}: {result.detail}",
                    "ok" if result.value else "warn",
                )
            except Exception:
                pass
            return node.on_true if result.value else node.on_false
        if node.type == "action":
            action_name = str(params["action"])
            action_params = dict(params.get("arguments") or {})
            result = self.actions.execute(action_name, action_params, context)
            context["last_action_result"] = result
            return node.next
        if node.type == "wait":
            seconds = max(0.0, float(params.get("seconds", 0)))
            if stop_event.wait(seconds):
                return None
            return node.next
        if node.type == "set_variable":
            name = str(params.get("name", ""))
            value = params.get("value")
            if isinstance(value, dict) and set(value) == {"variable"}:
                value = variables.get(str(value["variable"]))
            operation = str(params.get("operation", "set"))
            if operation == "set":
                variables.set(name, value)
            elif operation == "increment":
                variables.increment(name, value if value is not None else 1)
            elif operation == "delete":
                variables.delete(name)
            else:
                raise FlowExecutionError(f"Operación de variable no soportada: {operation}")
            return node.next
        if node.type == "loop":
            loop_counts[node.id] = loop_counts.get(node.id, 0) + 1
            maximum = int(params["max_iterations"])
            variable = params.get("counter_variable")
            if variable:
                variables.set(str(variable), loop_counts[node.id])
            if loop_counts[node.id] <= maximum:
                return node.on_true or node.next
            loop_counts[node.id] = 0
            return node.on_false or node.next
        if node.type == "switch":
            value = params.get("value")
            if isinstance(value, dict) and set(value) == {"variable"}:
                value = variables.get(str(value["variable"]))
            return node.branches.get(str(value), node.on_false or node.next)
        raise FlowExecutionError(f"Tipo de bloque no implementado: {node.type}")
