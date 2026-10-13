import time
import os
import re
import threading
import win32gui
import win32con
from pynput.keyboard import Controller as KeyboardController, Key
from PIL import ImageGrab
import pyautogui

from config import ruta_recurso

keyboard = KeyboardController()

# =========================================================================
# CONFIGURACIÓN GENERAL
# =========================================================================
TIEMPO_RESPAWN_CICLO = 6.0    # Pausa en el seto inicial
VUELTAS_PARA_ALMAS = 6        # Cada cuántas vueltas revisa inventario
CANTIDAD_PULSOS_ALMAS = 50    # Pulsaciones de Z para vaciar el stack
IMG_ICONO_ALMA = ruta_recurso(os.path.join("assets", "bs_icono_alma.png"))
# =========================================================================

# Evento de parada del worker en curso; lo fija worker_black_souls al arrancar.
# Permite que las esperas largas se corten al instante con Shift + Esc.
_STOP = threading.Event()


def _esperar(segundos):
    """Espera interrumpible: devuelve True si se pidió detener."""
    return _STOP.wait(timeout=max(0.0, segundos))


# Tiempos por defecto de cada tile (ms). Son los que usaba la ruta fija original.
PRESS_MS_DEFECTO = 220
WAIT_MS_DEFECTO = 140

# Ruta de farmeo: (tipo, descripción, dirección, veces | segundos)
#   mov     -> pulsa `dirección` `veces` casillas (revisa combate en cada una)
#   espera  -> espera hasta `segundos` a que empiece un combate y lo resuelve
# La pestaña Black Souls construye su lista de calibración a partir de esto.
RUTA_DEFECTO = (
    ("mov", "Subir al callejón", "up", 1),
    ("mov", "Chocar con conejo 1", "right", 1),
    ("espera", "Conejo 1: esperar pelea", None, 3),
    ("mov", "Bajar por carril despejado", "down", 4),
    ("mov", "Quiebre 1: derecha", "right", 1),
    ("mov", "Quiebre 2: abajo bordeando costilla", "down", 1),
    ("mov", "Entrar al esqueleto central", "right", 3),
    ("espera", "Esqueleto (ida): esperar pelea", None, 3),
    ("mov", "Avanzar a zona de agua", "right", 4),
    ("espera", "Patrullero: esperar acercamiento", None, 3),
    ("mov", "Vuelta: cruzar de agua a esqueleto", "left", 4),
    ("espera", "Esqueleto (vuelta): ¿reapareció conejo 2?", None, 3.5),
    ("mov", "Vuelta: salir del esqueleto", "left", 3),
    ("mov", "Vuelta: subir costilla", "up", 1),
    ("mov", "Vuelta: reentrar al carril libre", "left", 1),
    ("mov", "Vuelta: subir por carril", "up", 3),
    ("mov", "Vuelta: encajar en seto inicial", "left", 1),
)


def pasos_por_defecto():
    """RUTA_DEFECTO en el mismo formato que `lista_pasos` (lo usa el worker si llega vacía)."""
    pasos = []
    for tipo, desc, direccion, valor in RUTA_DEFECTO:
        if tipo == "mov":
            pasos.append({"tipo": "mov", "desc": desc, "dir": direccion, "veces": valor,
                          "press_ms": PRESS_MS_DEFECTO, "wait_ms": WAIT_MS_DEFECTO})
        else:
            pasos.append({"tipo": "espera", "desc": desc, "seg": valor})
    return pasos


def _num(valor, defecto):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return defecto


TECLAS_MAP = {
    "z": "z", "enter": Key.enter, "space": Key.space,
    "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
    "x": "x", "shift": Key.shift
}

def enfocar_black_souls():
    """Trae la ventana de Black Souls (RGSS3 Player) al frente."""
    hwnd_target = None
    def enum_cb(hwnd, _):
        nonlocal hwnd_target
        if win32gui.IsWindowVisible(hwnd):
            titulo = win32gui.GetWindowText(hwnd)
            if "black souls" in titulo.lower() or "rgss3" in titulo.lower():
                hwnd_target = hwnd
    win32gui.EnumWindows(enum_cb, None)
    if hwnd_target:
        try:
            win32gui.ShowWindow(hwnd_target, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd_target)
            _esperar(0.12)
            return hwnd_target
        except Exception:
            pass
    return None

def pulsar_paso(direccion, press_time=0.22, wait_time=0.14):
    """Pulsación unitaria por casilla con las flechas direccionales."""
    tecla = TECLAS_MAP.get(direccion, Key.up)
    keyboard.press(tecla)
    time.sleep(press_time)
    keyboard.release(tecla)
    _esperar(wait_time)

def pulsar_tecla(tecla, delay=0.08):
    """Pulsación para botones de acción o flechas de menú."""
    t = TECLAS_MAP.get(tecla, tecla)
    keyboard.press(t)
    time.sleep(delay)
    keyboard.release(t)
    _esperar(0.04)

def pulsar_z_rapido():
    """Pulsación ultrarrápida para consumir almas y vaciar diálogos."""
    keyboard.press('z')
    time.sleep(0.025)
    keyboard.release('z')
    _esperar(0.035)

def menu_combate_visible(img_menu, conf=0.8):
    """Detecta si el menú de combate está en pantalla."""
    if not os.path.exists(img_menu):
        return False
    try:
        pantalla = ImageGrab.grab(all_screens=True)
        return pyautogui.locate(img_menu, pantalla, confidence=conf) is not None
    except Exception:
        return False

def alma_negra_en_pantalla(img_icono=IMG_ICONO_ALMA, conf=0.80):
    """Comprueba si el icono redondo de Alma negra está presente en el inventario."""
    if not os.path.exists(img_icono):
        return False
    try:
        pantalla = ImageGrab.grab(all_screens=True)
        return pyautogui.locate(img_icono, pantalla, confidence=conf) is not None
    except Exception:
        return False

def consumir_todas_las_almas(stop_event, set_status_fn):
    """
    Rutina calibrada para lista de 22 filas por columna:
    1. Abre menú (X -> Z -> Z)
    2. Sube 25 veces e izquierda 3 veces para asegurar Fila 1 Columna 1
    3. Baja 4 posiciones (Fila 5: Alma negra)
    4. Comprueba icono antes de accionar Z (evita usar Hueso de regreso)
    5. Cierra con X x3
    """
    set_status_fn("ABRIENDO INVENTARIO (X -> Z -> Z)...", "#9333EA")
    _esperar(0.3)

    pulsar_tecla('x', delay=0.10)
    _esperar(0.35)

    pulsar_tecla('z', delay=0.10)
    _esperar(0.35)

    pulsar_tecla('z', delay=0.10)
    _esperar(0.40)

    set_status_fn("RESETEANDO CURSOR A FILA 1 (25 UP + 3 LEFT)...", "#A855F7")
    for _ in range(25):
        if stop_event.is_set():
            return
        pulsar_tecla('up', delay=0.03)

    for _ in range(3):
        if stop_event.is_set():
            return
        pulsar_tecla('left', delay=0.03)

    _esperar(0.25)

    set_status_fn("BAJANDO A CASILLA DE ALMA NEGRA (DOWN x4)...", "#A855F7")
    for _ in range(4):
        if stop_event.is_set():
            return
        pulsar_tecla('down', delay=0.09)
        _esperar(0.12)

    _esperar(0.25)

    if not alma_negra_en_pantalla():
        set_status_fn("0 ALMAS DISPONIBLES (HUESO DETECTADO). CANCELANDO...", "#EAB308")
        _esperar(0.3)
    else:
        set_status_fn("ALMA NEGRA ENCONTRADA: CONSUMIENDO STACK...", "#22C55E")
        for _ in range(CANTIDAD_PULSOS_ALMAS):
            if stop_event.is_set():
                break
            pulsar_z_rapido()
        _esperar(0.3)

    set_status_fn("CERRANDO MENÚ...", "#3B82F6")
    for _ in range(3):
        pulsar_tecla('x', delay=0.08)
        _esperar(0.20)

    _esperar(0.5)

def resolver_pelea_en_curso(img_menu, stop_event, set_status_fn):
    """Ejecuta la maestría y barre los textos de victoria con Turbo-Spam."""
    set_status_fn("COMBATE DETECTADO: SELECCIONANDO MAESTRÍA...", "#C084FC")
    _esperar(0.3)

    pulsar_tecla('x', delay=0.08)
    _esperar(0.15)

    pulsar_tecla('down', delay=0.10)
    _esperar(0.15)

    pulsar_tecla('z', delay=0.08)
    _esperar(0.22)
    pulsar_tecla('z', delay=0.08)
    _esperar(0.22)
    pulsar_tecla('z', delay=0.08)

    set_status_fn("COMBATE: ANIMACIÓN DE HABILIDAD...", "#EAB308")
    _esperar(5.0)

    set_status_fn("COMBATE: BARRIENDO DROPS Y RESULTADOS...", "#22C55E")
    t_fin = time.time()
    while time.time() - t_fin < 5.0:
        if stop_event.is_set():
            return
        pulsar_z_rapido()

    _esperar(0.8)
    set_status_fn("COMBATE FINALIZADO. RETOMANDO MAPA...", "#22C55E")

def iniciar_y_resolver_combate(img_menu, timeout_espera, stop_event, set_status_fn, mensaje="INICIANDO COMBATE..."):
    """Espera activamente a que cargue la batalla."""
    set_status_fn(mensaje, "#EF4444")
    t_inicio = time.time()

    while time.time() - t_inicio < timeout_espera:
        if stop_event.is_set():
            return False

        if menu_combate_visible(img_menu):
            resolver_pelea_en_curso(img_menu, stop_event, set_status_fn)
            return True

        pulsar_tecla('z', delay=0.06)
        _esperar(0.30)

    return False

def worker_black_souls(img_menu, lista_pasos, stop_event, set_status_fn):
    """Bucle principal de farmeo de conejos."""
    global _STOP
    _STOP = stop_event
    enfocar_black_souls()
    _esperar(0.4)

    pasos = lista_pasos or pasos_por_defecto()
    contador_vueltas = 0

    def dar_pasos(direccion, cantidad, descripcion, t_press, t_wait):
        set_status_fn(f"{descripcion} ({direccion.upper()} x{cantidad})", "#3B82F6")
        for _ in range(cantidad):
            if stop_event.is_set():
                break

            pulsar_z_rapido()
            if menu_combate_visible(img_menu):
                resolver_pelea_en_curso(img_menu, stop_event, set_status_fn)

            pulsar_paso(direccion, press_time=t_press, wait_time=t_wait)

            pulsar_z_rapido()
            if menu_combate_visible(img_menu):
                resolver_pelea_en_curso(img_menu, stop_event, set_status_fn)

    while not stop_event.is_set():
        enfocar_black_souls()

        # 1. RECORRIDO COMPLETO (los tiempos salen de la calibración de la pestaña)
        for paso in pasos:
            if stop_event.is_set():
                break
            desc = re.sub(r"^\d+\.\s*", "", str(paso.get("desc", "")))

            if paso.get("tipo") == "mov":
                dar_pasos(
                    paso.get("dir", "up"),
                    max(1, int(_num(paso.get("veces"), 1))),
                    desc,
                    max(0.01, _num(paso.get("press_ms"), PRESS_MS_DEFECTO) / 1000.0),
                    max(0.0, _num(paso.get("wait_ms"), WAIT_MS_DEFECTO) / 1000.0),
                )
            elif paso.get("tipo") == "espera":
                iniciar_y_resolver_combate(
                    img_menu,
                    timeout_espera=max(0.5, _num(paso.get("seg"), 5.0)),
                    stop_event=stop_event,
                    set_status_fn=set_status_fn,
                    mensaje=f"{desc.upper()}...",
                )

        if stop_event.is_set():
            break

        # 3. CONTROL DE CICLOS Y VACIADO SEGURO
        contador_vueltas += 1
        set_status_fn(f"RECORRIDO {contador_vueltas}/{VUELTAS_PARA_ALMAS} COMPLETADO", "#22C55E")

        if contador_vueltas >= VUELTAS_PARA_ALMAS:
            consumir_todas_las_almas(stop_event, set_status_fn)
            contador_vueltas = 0

        # Pausa de respawn antes de reiniciar
        t_fin_respawn = time.time() + TIEMPO_RESPAWN_CICLO
        while time.time() < t_fin_respawn:
            if stop_event.is_set():
                break
            restante = int(t_fin_respawn - time.time()) + 1
            set_status_fn(f"ESPERANDO RESPAWN EN SETO ({restante}s)...", "#EAB308")
            if _esperar(1):
                break
