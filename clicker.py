import time
from pynput.mouse import Button
from pynput.keyboard import Key, KeyCode

def parse_time_to_seconds(val, unit):
    try:
        v = float(val)
    except ValueError:
        return 0.1
    if unit == "ms":
        return max(0.001, v / 1000.0)
    elif unit == "s":
        return max(0.001, v)
    elif unit == "m":
        return max(0.001, v * 60.0)
    return 0.1

def presionar_tecla_segura(keyboard_ctrl, k_str):
    try:
        if k_str.startswith("Key."):
            attr = k_str.split(".")[1]
            k = getattr(Key, attr, None)
            if k:
                keyboard_ctrl.press(k)
                keyboard_ctrl.release(k)
        elif k_str.startswith("vk_"):
            vk_code = int(k_str.split("_")[1])
            k = KeyCode.from_vk(vk_code)
            keyboard_ctrl.press(k)
            keyboard_ctrl.release(k)
        else:
            keyboard_ctrl.press(k_str)
            keyboard_ctrl.release(k_str)
    except Exception:
        pass

def worker_clicker_main(app_ref):
    """Worker para la pestaña del Clicker Principal."""
    target_repeats = None
    if app_ref.tab_main.repeat_mode.get() == "fixed":
        try:
            target_repeats = int(app_ref.tab_main.entry_repeats.get())
        except ValueError:
            target_repeats = 100

    btn_map = {
        "Izquierdo": Button.left,
        "Derecho": Button.right,
        "Central": Button.middle
    }
    button = btn_map.get(app_ref.tab_main.combo_btn.get(), Button.left)
    is_double = app_ref.tab_main.combo_type.get() == "Doble"

    if app_ref.tab_cfg.check_countdown.get() == 1:
        for i in range(3, 0, -1):
            if app_ref.stop_event.is_set():
                return
            app_ref.lbl_status.configure(text=f"INICIANDO EN {i}s...", text_color="#EAB308")
            if app_ref.stop_event.wait(timeout=1):
                return
        app_ref.lbl_status.configure(text="ESTADO: CLICKER ACTIVO", text_color="#22C55E")

    executed = 0
    while not app_ref.stop_event.is_set():
        if app_ref.tab_main.pos_mode.get() == "fixed":
            try:
                x = int(app_ref.tab_main.entry_x.get())
                y = int(app_ref.tab_main.entry_y.get())
                app_ref.mouse.position = (x, y)
            except ValueError:
                pass

        app_ref.mouse.click(button, 2 if is_double else 1)

        executed += 1
        if target_repeats is not None and executed >= target_repeats:
            app_ref.after(0, app_ref.stop_all)
            break

        interval = app_ref.tab_main.get_interval()
        app_ref.stop_event.wait(timeout=interval)