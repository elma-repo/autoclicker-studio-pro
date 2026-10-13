"""Motor de flujos para AutoClicker Studio Pro.

Esta capa no importa CustomTkinter ni PyAutoGUI directamente. La interfaz y los
adaptadores del motor existente se conectan mediante callbacks.
"""
from .flow_model import Flow, FlowNode, load_flow, save_flow
from .flow_validator import validate_flow, FlowValidationError
from .variable_store import VariableStore
from .condition_evaluator import ConditionEvaluator, ConditionResult
from .action_registry import ActionRegistry
from .flow_runner import FlowRunner, FlowExecutionError, FlowRunResult

__all__ = [
    "Flow", "FlowNode", "load_flow", "save_flow",
    "validate_flow", "FlowValidationError",
    "VariableStore", "ConditionEvaluator", "ConditionResult",
    "ActionRegistry", "FlowRunner", "FlowExecutionError", "FlowRunResult",
]
