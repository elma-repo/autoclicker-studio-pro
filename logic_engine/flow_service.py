"""Servicio pequeño para cargar, validar, guardar y ejecutar flujos."""
from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Any, Callable

from .flow_model import Flow, load_flow, save_flow
from .flow_validator import validate_flow
from .flow_runner import FlowRunResult
from .vision_adapter import build_app_runner, make_ui_logger


class FlowService:
    """Capa que puede usar una futura pestaña UI sin acoplarse al widget."""

    def __init__(self, app_ref: Any, logger: Callable[[str, str], None] | None = None):
        self.app_ref = app_ref
        self.logger = logger or make_ui_logger(app_ref)

    def load(self, path: str | Path) -> Flow:
        flow = load_flow(path)
        errors = validate_flow(flow)
        if errors:
            raise ValueError("El flujo contiene errores:\n- " + "\n- ".join(errors))
        return flow

    def save(self, flow: Flow, path: str | Path) -> None:
        errors = validate_flow(flow)
        if errors:
            raise ValueError("No se puede guardar un flujo inválido:\n- " + "\n- ".join(errors))
        save_flow(flow, path)

    def run(
        self,
        flow: Flow,
        stop_event: Event | None = None,
        *,
        max_steps: int = 10000,
        max_runtime_s: float = 3600.0,
        target_hwnd: int | None = None,
    ) -> FlowRunResult:
        runner = build_app_runner(
            self.app_ref,
            logger=self.logger,
            max_steps=max_steps,
            max_runtime_s=max_runtime_s,
            stop_event=stop_event,
            target_hwnd=target_hwnd,
        )
        return runner.run(flow, stop_event=stop_event)