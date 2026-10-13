"""Adaptadores entre el motor de flujos y las funciones existentes de AutoClicker Studio.

Este módulo importa `vision` y `clicker` de forma diferida para que el motor pueda
probarse en equipos donde las dependencias de Windows no estén instaladas.
"""
from __future__ import annotations

from threading import Event
from time import monotonic
from typing import Any, Callable

from .action_registry import ActionRegistry
from .condition_evaluator import ConditionEvaluator
from .flow_runner import FlowRunner
from .variable_store import VariableStore


class FlowCancelled(RuntimeError):
    """Señala que la ejecución se canceló mientras esperaba una condición."""


def _safe_log(logger: Callable[[str, str], None] | None, message: str, level: str = "info") -> None:
    if logger is None:
        return
    try:
        logger(message, level)
    except Exception:
        pass


def build_app_runner(
    app_ref: Any,
    *,
    logger: Callable[[str, str], None] | None = None,
    max_steps: int = 10000,
    max_runtime_s: float = 3600.0,
    stop_event: Event | None = None,
    target_hwnd: int | None = None,
) -> FlowRunner:
    """Construye un FlowRunner conectado con `vision.py` y los controladores de la app.

    Si `target_hwnd` no es None, las acciones y condiciones basadas en imagen se
    restringen a esa ventana (búsqueda + origen de coordenadas para los clics).
    """
    import vision
    import clicker

    stop_event = stop_event or getattr(app_ref, "stop_event", None)
    if stop_event is None:
        stop_event = Event()

    registry = ActionRegistry()

    def check_cancelled() -> None:
        if stop_event.is_set():
            raise FlowCancelled("Ejecución cancelada por el usuario.")

    def image_checker(image: str, confidence: float, timeout_s: float) -> bool:
        deadline = monotonic() + max(0.0, float(timeout_s))
        while True:
            check_cancelled()
            box = vision.localizar_imagen(
                image,
                confidence=confidence,
                hwnd=target_hwnd,
                solo_ventana=bool(target_hwnd),
            )
            if box is not None:
                return True
            if monotonic() >= deadline:
                return False
            if stop_event.wait(min(0.15, max(0.0, deadline - monotonic()))):
                raise FlowCancelled("Ejecución cancelada mientras se buscaba una imagen.")

    def action_click_image(params: dict[str, Any], context: Any) -> bool:
        image = str(params.get("image", "")).strip()
        if not image:
            raise ValueError("La acción click_image necesita el parámetro 'image'.")
        confidence = float(params.get("confidence", 0.8))
        timeout_s = max(0.0, float(params.get("timeout_s", 0.0)))
        deadline = monotonic() + timeout_s
        while True:
            check_cancelled()
            box = vision.localizar_imagen(
                image,
                confidence=confidence,
                hwnd=target_hwnd,
                solo_ventana=bool(target_hwnd),
            )
            if box is not None:
                offset_x = int(params.get("offset_x", 0))
                offset_y = int(params.get("offset_y", 0))
                boton = str(params.get("button", "izq"))
                veces = max(1, int(params.get("clicks", 1)))
                clicked = vision.hacer_click_boton(
                    box,
                    x_offset=offset_x,
                    y_offset=offset_y,
                    boton=boton,
                    veces=veces,
                    hwnd=target_hwnd,
                )
                return bool(clicked)
            if monotonic() >= deadline:
                return False
            if stop_event.wait(min(0.15, max(0.0, deadline - monotonic()))):
                raise FlowCancelled("Ejecución cancelada mientras se buscaba una imagen.")

    def action_click_at(params: dict[str, Any], context: Any) -> bool:
        check_cancelled()
        if "x" not in params or "y" not in params:
            raise ValueError("La acción click_at necesita 'x' e 'y'.")
        vision.hacer_click_real(
            int(params["x"]),
            int(params["y"]),
            boton=str(params.get("button", "izq")),
            veces=max(1, int(params.get("clicks", 1))),
        )
        return True

    def action_press_key(params: dict[str, Any], context: Any) -> bool:
        check_cancelled()
        key = str(params.get("key", "")).strip()
        if not key:
            raise ValueError("La acción press_key necesita el parámetro 'key'.")
        keyboard = getattr(app_ref, "keyboard", None)
        if keyboard is None:
            raise RuntimeError("La aplicación no tiene un controlador de teclado disponible.")
        clicker.presionar_tecla_segura(keyboard, key)
        return True

    def action_wait(params: dict[str, Any], context: Any) -> bool:
        seconds = max(0.0, float(params.get("seconds", 0)))
        if stop_event.wait(seconds):
            raise FlowCancelled("Ejecución cancelada durante la espera.")
        return True

    def action_log(params: dict[str, Any], context: Any) -> str:
        message = str(params.get("message", ""))
        level = str(params.get("level", "info"))
        _safe_log(logger, message, level)
        return message

    registry.register("click_image", action_click_image)
    registry.register("click_at", action_click_at)
    registry.register("press_key", action_press_key)
    registry.register("wait", action_wait)
    registry.register("log", action_log)

    def evaluator_factory(variables: VariableStore, context: dict[str, Any]) -> ConditionEvaluator:
        return ConditionEvaluator(
            variables=variables,
            image_checker=image_checker,
            context=context,
        )

    return FlowRunner(
        actions=registry,
        condition_evaluator_factory=evaluator_factory,
        logger=logger,
        max_steps=max_steps,
        max_runtime_s=max_runtime_s,
    )


def make_ui_logger(app_ref: Any) -> Callable[[str, str], None]:
    """Devuelve un logger seguro para CustomTkinter; usa `after` si está disponible."""
    def logger(message: str, level: str = "info") -> None:
        callback = getattr(app_ref, "log_flow_message", None)
        if callable(callback):
            try:
                app_ref.after(0, callback, message, level)
                return
            except Exception:
                pass
        status = getattr(app_ref, "lbl_status", None)
        if status is not None and level in ("err", "error"):
            try:
                app_ref.after(
                    0,
                    lambda: status.configure(text=f"FLUJO: {message}", text_color="#EF4444"),
                )
            except Exception:
                pass
    return logger