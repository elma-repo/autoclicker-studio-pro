import time
from pynput.mouse import Button
from clicker import parse_time_to_seconds, presionar_tecla_segura
from macro_recorder import deserialize_key

BUTTONS = {"Izquierdo": Button.left, "Derecho": Button.right, "Central": Button.middle}
MOVE_SETTLE_S = 0.015   # pausa tras mover el cursor, antes de pulsar


def _get_speed(app_ref):
    try:
        return app_ref.tab_macro.get_speed()
    except Exception:
        return 1.0


def _wait(app_ref, seconds):
    """Espera interrumpible: devuelve True si se pidió detener."""
    return app_ref.stop_event.wait(timeout=max(0.0, seconds))


def _move(app_ref, x, y):
    app_ref.mouse.position = (int(x), int(y))
    time.sleep(MOVE_SETTLE_S)


def _button(step):
    return BUTTONS.get(step.get("action"), Button.left)


def _drag(app_ref, step, speed, held_buttons):
    btn = _button(step)
    x, y, x2, y2 = step["x"], step["y"], step["x2"], step["y2"]
    duration = max(0.05, step.get("drag_ms", 300) / 1000.0 / speed)

    _move(app_ref, x, y)
    app_ref.mouse.press(btn)
    held_buttons.add(btn)
    try:
        n = max(2, min(200, int(duration / 0.012)))
        for i in range(1, n + 1):
            if app_ref.stop_event.is_set():
                break
            app_ref.mouse.position = (int(x + (x2 - x) * i / n), int(y + (y2 - y) * i / n))
            _wait(app_ref, duration / n)
        else:
            app_ref.mouse.position = (int(x2), int(y2))
    finally:
        app_ref.mouse.release(btn)
        held_buttons.discard(btn)


def _tap_key(app_ref, step, speed, held_keys):
    """Pulsar una tecla; con `hold_ms` se mantiene ese tiempo."""
    hold = step.get("hold_ms", 0) / 1000.0 / speed
    key = deserialize_key(step["key"]) if hold > 0 else None
    if key is None:
        presionar_tecla_segura(app_ref.keyboard, step["key"])   # pulsación normal
        return
    app_ref.keyboard.press(key)
    held_keys[step["key"]] = key
    try:
        _wait(app_ref, hold)
    finally:
        app_ref.keyboard.release(key)
        held_keys.pop(step["key"], None)


def _exec_step(app_ref, step, speed, held_keys, held_buttons):
    kind = step.get("type")

    if kind == "mouse":
        _move(app_ref, step["x"], step["y"])
        action = step.get("action", "Izquierdo")
        if action == "Doble":
            app_ref.mouse.click(Button.left, 2)
            return
        btn = BUTTONS.get(action, Button.left)
        hold = step.get("hold_ms", 0) / 1000.0 / speed
        if hold > 0:
            app_ref.mouse.press(btn)
            held_buttons.add(btn)
            try:
                _wait(app_ref, hold)
            finally:
                app_ref.mouse.release(btn)
                held_buttons.discard(btn)
        else:
            app_ref.mouse.click(btn, 1)

    elif kind == "mouse_drag":
        _drag(app_ref, step, speed, held_buttons)

    elif kind == "mouse_scroll":
        _move(app_ref, step["x"], step["y"])
        app_ref.mouse.scroll(step.get("dx", 0), step.get("dy", 0))

    elif kind == "mouse_down":
        _move(app_ref, step["x"], step["y"])
        btn = _button(step)
        app_ref.mouse.press(btn)
        held_buttons.add(btn)

    elif kind == "mouse_up":
        _move(app_ref, step["x"], step["y"])
        btn = _button(step)
        app_ref.mouse.release(btn)
        held_buttons.discard(btn)

    elif kind == "keyboard":
        _tap_key(app_ref, step, speed, held_keys)

    elif kind == "key_down":
        key = deserialize_key(step["key"])
        if key is not None:
            app_ref.keyboard.press(key)
            held_keys[step["key"]] = key

    elif kind == "key_up":
        key = deserialize_key(step["key"])
        if key is not None:
            app_ref.keyboard.release(key)
        held_keys.pop(step["key"], None)


def _release_all(app_ref, held_keys, held_buttons):
    """Suelta todo lo que haya quedado pulsado (al detener, o si la macro olvidó un 'soltar')."""
    for key in list(held_keys.values()):
        try:
            app_ref.keyboard.release(key)
        except Exception:
            pass
    for btn in list(held_buttons):
        try:
            app_ref.mouse.release(btn)
        except Exception:
            pass
    held_keys.clear()
    held_buttons.clear()


def worker_macro(app_ref):
    """Worker para la reproducción de secuencias / macros."""
    target_repeats = None
    if app_ref.tab_macro.macro_repeat_mode.get() == "fixed":
        try:
            target_repeats = int(app_ref.tab_macro.entry_macro_repeats.get())
        except ValueError:
            target_repeats = 10

    if app_ref.tab_cfg.check_countdown.get() == 1:
        for i in range(3, 0, -1):
            if app_ref.stop_event.is_set():
                return
            app_ref.lbl_status.configure(text=f"INICIANDO EN {i}s...", text_color="#EAB308")
            if app_ref.stop_event.wait(timeout=1):
                return
        app_ref.lbl_status.configure(text="ESTADO: SECUENCIA ACTIVA", text_color="#22C55E")

    held_keys = {}      # texto de tecla -> objeto tecla (lo que está pulsado ahora)
    held_buttons = set()
    executed_cycles = 0

    try:
        while not app_ref.stop_event.is_set():
            current_cards = list(app_ref.tab_macro.step_cards)
            if not current_cards:
                app_ref.after(0, app_ref.stop_all)
                break

            speed = _get_speed(app_ref)     # se relee cada ciclo: se puede cambiar en vivo

            for card in current_cards:
                if app_ref.stop_event.is_set():
                    break

                app_ref.after(0, lambda c=card: c.set_active(True))
                step = card.get_current_data()

                try:
                    _exec_step(app_ref, step, speed, held_keys, held_buttons)
                except Exception as exc:
                    print(f"Error en el paso {step.get('type')}: {exc}")

                delay = parse_time_to_seconds(step.get('time_val', 500), step.get('time_unit', 'ms'))
                _wait(app_ref, delay / speed)
                app_ref.after(0, lambda c=card: c.set_active(False))

            executed_cycles += 1
            if target_repeats is not None and executed_cycles >= target_repeats:
                app_ref.after(0, app_ref.stop_all)
                break
    finally:
        _release_all(app_ref, held_keys, held_buttons)
