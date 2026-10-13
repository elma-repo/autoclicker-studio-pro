"""Grabador de secuencias.

Recibe los eventos crudos de los listeners globales (teclado y ratón) y los
convierte en pasos para la pestaña Secuencias.

Tipos de paso que puede producir (todos llevan `time_val`/`time_unit` = espera
DESPUÉS de ejecutar el paso):

    mouse         clic simple/doble/derecho/central (opcional `hold_ms` = clic largo)
    mouse_drag    arrastrar de (x, y) a (x2, y2) en `drag_ms`
    mouse_scroll  rueda en (x, y): `dy` (vertical) y `dx` (horizontal)
    mouse_down    mantener un botón (cuando hay otros eventos mientras está pulsado)
    mouse_up      soltar ese botón
    keyboard      pulsar una tecla (opcional `hold_ms` = tecla mantenida)
    key_down      mantener una tecla (combos: Ctrl+C, Shift+click, etc.)
    key_up        soltar esa tecla
"""
import math
import threading
import time

from pynput.keyboard import Key, KeyCode

# ----------------------------------------------------------------------
# Umbrales
# ----------------------------------------------------------------------
TAP_MAX_S = 0.15            # por debajo de esto una tecla es una pulsación normal
LONG_PRESS_MIN_S = 0.40     # clic mantenido sin mover = clic largo
DRAG_MIN_PX = 8             # distancia mínima entre pulsar y soltar para ser arrastre
DOUBLE_CLICK_MAX_S = 0.35   # dos clics izquierdos así de seguidos = doble clic
DOUBLE_CLICK_PX = 6
SCROLL_MERGE_GAP_S = 0.35   # ticks de rueda seguidos se agrupan en un solo paso
MIN_DELAY_MS = 30           # espera mínima entre pasos
LAST_DELAY_MS = 500         # espera tras el último paso

_BUTTON_NAMES = {"left": "Izquierdo", "right": "Derecho", "middle": "Central"}


# ----------------------------------------------------------------------
# Serialización de teclas (compartida con macro_engine y main)
# ----------------------------------------------------------------------
def serialize_key(key):
    """Devuelve (texto_guardable, nombre_para_mostrar).

    Formatos: 'Key.f5' (teclas especiales), 'a' (carácter), 'vk_67' (código virtual).
    Con Ctrl pulsado, Windows entrega caracteres de control (Ctrl+C = '\\x03'):
    en ese caso se guarda el código virtual para que la tecla se reproduzca bien.
    """
    if isinstance(key, Key):
        return f"Key.{key.name}", key.name
    if isinstance(key, KeyCode):
        ch = key.char
        if ch and ch.isprintable():
            return ch, ch
        vk = key.vk
        if vk is not None:
            if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
                return f"vk_{vk}", chr(vk)
            return f"vk_{vk}", f"VK{vk}"
    text = str(key).replace("'", "")
    return text, text


def deserialize_key(text):
    """Inverso de serialize_key. Devuelve algo que pynput acepte, o None."""
    if not text:
        return None
    if text.startswith("Key."):
        return getattr(Key, text[4:], None)
    if text.startswith("vk_"):
        try:
            return KeyCode.from_vk(int(text[3:]))
        except ValueError:
            return None
    if len(text) == 1:
        return text
    return None


# ----------------------------------------------------------------------
# Grabador
# ----------------------------------------------------------------------
class MacroRecorder:
    def __init__(self, on_change=None):
        self._on_change = on_change          # callback(n_eventos)
        self._lock = threading.Lock()
        self._clock = time.time
        self._events = []
        self._keys_down = set()
        self._buttons_down = set()
        self.active = False

    # -- control --------------------------------------------------------
    def start(self):
        with self._lock:
            self._events = []
            self._keys_down.clear()
            self._buttons_down.clear()
            self.active = True
        self._notify()

    def stop(self, trim_keys=None):
        """Detiene la grabación y devuelve la lista de pasos.

        trim_keys: teclas ('Key.shift', ...) cuyos eventos finales se descartan
        (sirve para no grabar el propio Shift de Shift+Esc).
        """
        with self._lock:
            self.active = False
            events = list(self._events)
            self._events = []
            self._keys_down.clear()
            self._buttons_down.clear()
            t_stop = self._clock()
        return build_steps(events, t_stop, trim_keys)

    # -- entradas -------------------------------------------------------
    def key_down(self, key):
        if not self.active:
            return
        ser, disp = serialize_key(key)
        with self._lock:
            if ser in self._keys_down:       # autorrepetición de Windows: se ignora
                return
            self._keys_down.add(ser)
            self._events.append({"k": "kd", "key": ser, "disp": disp, "t": self._clock()})
        self._notify()

    def key_up(self, key):
        if not self.active:
            return
        ser, disp = serialize_key(key)
        with self._lock:
            if ser not in self._keys_down:   # su pulsación no se grabó (ej. la del atajo)
                return
            self._keys_down.discard(ser)
            self._events.append({"k": "ku", "key": ser, "disp": disp, "t": self._clock()})
        self._notify()

    def mouse_button(self, x, y, button, pressed):
        name = _BUTTON_NAMES.get(getattr(button, "name", ""))
        if name is None or not self.active:
            return
        with self._lock:
            if pressed:
                self._buttons_down.add(name)
                kind = "md"
            else:
                if name not in self._buttons_down:
                    return
                self._buttons_down.discard(name)
                kind = "mu"
            self._events.append({"k": kind, "btn": name, "x": int(x), "y": int(y),
                                 "t": self._clock()})
        self._notify()

    def scroll(self, x, y, dx, dy):
        if not self.active:
            return
        dx, dy = _tick(dx), _tick(dy)
        if dx == 0 and dy == 0:
            return
        with self._lock:
            self._events.append({"k": "sc", "x": int(x), "y": int(y), "dx": dx, "dy": dy,
                                 "t": self._clock()})
        self._notify()

    def _notify(self):
        if self._on_change:
            try:
                self._on_change(len(self._events))
            except Exception:
                pass


def _tick(v):
    """Pasa el delta de la rueda a un entero de al menos 1 notch."""
    if v == 0:
        return 0
    n = int(round(v))
    return n if n != 0 else (1 if v > 0 else -1)


def _sgn(v):
    return (v > 0) - (v < 0)


# ----------------------------------------------------------------------
# Eventos crudos -> pasos
# ----------------------------------------------------------------------
def build_steps(events, t_stop, trim_keys=None):
    ev = [dict(e) for e in events]

    trim = set(trim_keys or ())
    while ev and ev[-1]["k"] in ("kd", "ku") and ev[-1]["key"] in trim:
        ev.pop()
    if not ev:
        return []

    # 1) Emparejar pulsar/soltar. Lo que quedó pulsado al terminar se suelta
    #    automáticamente (así nunca queda una tecla "atascada" al reproducir).
    pairs = {}
    open_k, open_m = {}, {}
    for i, e in enumerate(ev):
        k = e["k"]
        if k == "kd":
            open_k[e["key"]] = i
        elif k == "ku":
            j = open_k.pop(e["key"], None)
            if j is not None:
                pairs[j] = i
        elif k == "md":
            open_m[e["btn"]] = i
        elif k == "mu":
            j = open_m.pop(e["btn"], None)
            if j is not None:
                pairs[j] = i
    for key, j in open_k.items():
        ev.append({"k": "ku", "key": key, "disp": ev[j]["disp"], "t": t_stop})
        pairs[j] = len(ev) - 1
    for btn, j in open_m.items():
        ev.append({"k": "mu", "btn": btn, "x": ev[j]["x"], "y": ev[j]["y"], "t": t_stop})
        pairs[j] = len(ev) - 1
    up_idx = set(pairs.values())

    # 2) Recorrer en orden. Un pulsar/soltar "simple" (sin ningún otro evento
    #    entre medias) se funde en un solo paso; si hay eventos en medio
    #    (combos, tecla mantenida mientras se hace clic...) se guardan como
    #    pasos separados de pulsar y soltar para conservar el orden real.
    steps = []              # [paso, t_inicio, t_fin]
    consumed = set()
    n = len(ev)
    for i in range(n):
        if i in consumed:
            continue
        e = ev[i]
        k = e["k"]

        if k == "kd":
            j = pairs[i]
            up = ev[j]
            base = {"key": e["key"], "key_display": e["disp"]}
            if j == i + 1:
                step = {"type": "keyboard", **base}
                hold = up["t"] - e["t"]
                if hold >= TAP_MAX_S:
                    step["hold_ms"] = int(hold * 1000)
                consumed.add(j)
                steps.append([step, e["t"], up["t"]])
            else:
                steps.append([{"type": "key_down", **base}, e["t"], e["t"]])

        elif k == "ku":
            if i in up_idx:
                steps.append([{"type": "key_up", "key": e["key"], "key_display": e["disp"]},
                              e["t"], e["t"]])

        elif k == "md":
            j = pairs[i]
            up = ev[j]
            if j == i + 1:
                hold = up["t"] - e["t"]
                dist = math.hypot(up["x"] - e["x"], up["y"] - e["y"])
                if dist > DRAG_MIN_PX:
                    step = {"type": "mouse_drag", "x": e["x"], "y": e["y"],
                            "x2": up["x"], "y2": up["y"], "action": e["btn"],
                            "drag_ms": max(50, int(hold * 1000))}
                else:
                    step = {"type": "mouse", "x": e["x"], "y": e["y"], "action": e["btn"]}
                    if hold >= LONG_PRESS_MIN_S:
                        step["hold_ms"] = int(hold * 1000)
                consumed.add(j)
                steps.append([step, e["t"], up["t"]])
            else:
                steps.append([{"type": "mouse_down", "x": e["x"], "y": e["y"],
                               "action": e["btn"]}, e["t"], e["t"]])

        elif k == "mu":
            if i in up_idx:
                steps.append([{"type": "mouse_up", "x": e["x"], "y": e["y"],
                               "action": e["btn"]}, e["t"], e["t"]])

        elif k == "sc":
            dx, dy, last_t = e["dx"], e["dy"], e["t"]
            m = i + 1
            while m < n and ev[m]["k"] == "sc":
                nxt = ev[m]
                if (nxt["t"] - last_t <= SCROLL_MERGE_GAP_S
                        and _sgn(nxt["dy"]) == _sgn(e["dy"])
                        and _sgn(nxt["dx"]) == _sgn(e["dx"])):
                    dx += nxt["dx"]
                    dy += nxt["dy"]
                    last_t = nxt["t"]
                    consumed.add(m)
                    m += 1
                else:
                    break
            steps.append([{"type": "mouse_scroll", "x": e["x"], "y": e["y"],
                           "dx": dx, "dy": dy}, e["t"], last_t])

    # 3) Dos clics izquierdos seguidos en el mismo sitio = doble clic
    merged = []
    for st in steps:
        if merged:
            prev = merged[-1]
            a, b = prev[0], st[0]
            if (a["type"] == "mouse" and b["type"] == "mouse"
                    and a["action"] == "Izquierdo" and b["action"] == "Izquierdo"
                    and "hold_ms" not in a and "hold_ms" not in b
                    and st[1] - prev[1] <= DOUBLE_CLICK_MAX_S
                    and math.hypot(a["x"] - b["x"], a["y"] - b["y"]) <= DOUBLE_CLICK_PX):
                a["action"] = "Doble"
                prev[2] = st[2]
                continue
        merged.append(st)

    # 4) Espera de cada paso = tiempo hasta que empieza el siguiente
    out = []
    for idx, (step, _ts, te) in enumerate(merged):
        if idx + 1 < len(merged):
            gap_ms = int(round((merged[idx + 1][1] - te) * 1000))
            step["time_val"] = max(MIN_DELAY_MS, gap_ms)
        else:
            step["time_val"] = LAST_DELAY_MS
        step["time_unit"] = "ms"
        out.append(step)
    return out
