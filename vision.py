import time
import os
import win32gui
import win32api
import win32con
from PIL import ImageGrab
import pyautogui

from config import TARGET_GAME_IDENTIFIER, ruta_recurso

def _esperar(stop_event, segundos):
    """Espera interrumpible: devuelve True si se pidió detener."""
    if stop_event is None:
        time.sleep(max(0.0, segundos))
        return False
    return stop_event.wait(timeout=max(0.0, segundos))

def obtener_offset_virtual():
    """Obtiene las coordenadas absolutas (X, Y) del origen del escritorio virtual multimonitor."""
    vx = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
    vy = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
    return vx, vy

def obtener_info_juego(target_identifier=TARGET_GAME_IDENTIFIER):
    """Busca el HWND y el rectángulo de posición de la ventana del juego en Windows."""
    hwnd_target = None
    rect_target = None

    def enum_windows_callback(hwnd, extra):
        nonlocal hwnd_target, rect_target
        if win32gui.IsWindowVisible(hwnd) and not win32gui.IsIconic(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if target_identifier.lower() in title.lower():
                hwnd_target = hwnd
                rect_target = win32gui.GetWindowRect(hwnd)

    win32gui.EnumWindows(enum_windows_callback, None)
    return hwnd_target, rect_target

def capturar_pantalla(region=None, hwnd=None, solo_ventana=False):
    """Captura pantalla, una región o una ventana.

    `solo_ventana` se acepta para compatibilidad con la pestaña Personalizado.
    Si se solicita una ventana y no se proporciona `hwnd`, intenta localizar
    la ventana objetivo del juego.
    """
    if solo_ventana and not hwnd:
        try:
            hwnd, _ = obtener_info_juego(TARGET_GAME_IDENTIFIER)
        except Exception:
            hwnd = None

    if hwnd and win32gui.IsWindow(hwnd) and not win32gui.IsIconic(hwnd):
        try:
            rect = win32gui.GetWindowRect(hwnd)
            x1, y1, x2, y2 = rect
            if (x2 - x1) > 100 and (y2 - y1) > 100:
                return ImageGrab.grab(bbox=(x1, y1, x2, y2))
        except Exception:
            pass

    if region:
        x, y, w, h = region
        return ImageGrab.grab(bbox=(x, y, x + w, y + h))

    try:
        return ImageGrab.grab(all_screens=True)
    except Exception:
        return ImageGrab.grab()

def localizar_en_captura(img_path, screenshot, confidence=0.8):
    """Busca una imagen dentro de una captura existente usando pyautogui.

    Acepta también el orden antiguo (screenshot, img_path), usado por algunas
    versiones de la pestaña Personalizado.
    """
    orden_invertido = not isinstance(img_path, (str, bytes, os.PathLike)) and isinstance(
        screenshot, (str, bytes, os.PathLike)
    )
    if orden_invertido:
        img_path, screenshot = screenshot, img_path

    if not os.path.isfile(img_path) or screenshot is None:
        return None
    try:
        box = pyautogui.locate(img_path, screenshot, confidence=float(confidence))
        if box is not None and orden_invertido:
            # La pestaña Personalizado espera el centro (x, y) en este orden antiguo.
            return (box.left + box.width // 2, box.top + box.height // 2)
        return box
    except Exception:
        return None

def localizar_imagen(img_path, region=None, confidence=0.8, hwnd=None, solo_ventana=False, **kwargs):
    """Busca una imagen y devuelve (x, y, ancho, alto) o None.

    Si el segundo argumento es numérico, se interpreta como `confidence` para
    admitir llamadas posicionales de versiones anteriores.
    """
    if isinstance(region, (int, float)):
        confidence = float(region)
        region = None

    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = 0.8

    target_hwnd = hwnd
    if solo_ventana and not target_hwnd:
        try:
            target_hwnd, _ = obtener_info_juego(TARGET_GAME_IDENTIFIER)
        except Exception:
            pass

    screenshot = capturar_pantalla(region=region, hwnd=target_hwnd)
    box = localizar_en_captura(img_path, screenshot, confidence=confidence)

    if box is not None:
        try:
            return (box.left, box.top, box.width, box.height)
        except AttributeError:
            try:
                if len(box) >= 4:
                    return tuple(box[:4])
            except Exception:
                pass
    return None

def hacer_click_real(x, y, boton="izq", veces=1):
    """Envía clics físicos de Windows, compatibles con botones izquierdo y derecho."""
    boton_norm = str(boton).strip().lower()
    if boton_norm in ("der", "derecho", "right", "secondary"):
        down, up = win32con.MOUSEEVENTF_RIGHTDOWN, win32con.MOUSEEVENTF_RIGHTUP
    else:
        down, up = win32con.MOUSEEVENTF_LEFTDOWN, win32con.MOUSEEVENTF_LEFTUP

    total = max(1, int(veces))
    win32api.SetCursorPos((int(x), int(y)))
    time.sleep(0.05)
    for i in range(total):
        win32api.mouse_event(down, 0, 0, 0, 0)
        time.sleep(0.04)
        win32api.mouse_event(up, 0, 0, 0, 0)
        if i + 1 < total:
            time.sleep(0.08)
    time.sleep(0.03)


def hacer_click_boton(box, x_offset=0, y_offset=0, hwnd=None, region=None,
                      boton="izq", veces=1):
    """Hace clic en el centro de una caja, con offsets y botón/cantidad opcionales."""
    if box is None:
        return False

    base_x, base_y = 0, 0
    if hwnd and win32gui.IsWindow(hwnd) and not win32gui.IsIconic(hwnd):
        try:
            rect = win32gui.GetWindowRect(hwnd)
            base_x, base_y = rect[0], rect[1]
        except Exception:
            pass
    elif region:
        base_x, base_y = region[0], region[1]
    else:
        try:
            base_x, base_y = obtener_offset_virtual()
        except Exception:
            pass

    try:
        bx, by, bw, bh = box[0], box[1], box[2], box[3]
    except (TypeError, IndexError, KeyError):
        try:
            bx, by, bw, bh = box.left, box.top, box.width, box.height
        except Exception:
            return False

    centro_x = base_x + int(bx) + (int(bw) // 2) + int(x_offset)
    centro_y = base_y + int(by) + (int(bh) // 2) + int(y_offset)
    hacer_click_real(centro_x, centro_y, boton=boton, veces=veces)
    return True

def buscar_y_clicar(img_path, confidence=0.8, click=True, hwnd=None, region=None):
    """Busca una imagen en pantalla y realiza un clic protegido dentro del juego."""
    if not os.path.exists(img_path):
        return False

    screenshot = capturar_pantalla(region=region, hwnd=hwnd)
    box = localizar_en_captura(img_path, screenshot, confidence=confidence)

    if box:
        if click:
            hacer_click_boton(box, hwnd=hwnd, region=region)
        return True

    if hwnd or region:
        try:
            pantalla_global = ImageGrab.grab(all_screens=True)
            box_global = localizar_en_captura(img_path, pantalla_global, confidence=confidence)
            if box_global:
                if click:
                    vx, vy = obtener_offset_virtual()
                    cx = vx + box_global.left + (box_global.width // 2)
                    cy = vy + box_global.top + (box_global.height // 2)
                    hacer_click_real(cx, cy)
                return True
        except Exception:
            pass

    return False

def ejecutar_ciclo_inventario(
    img_open, img_check, img_move,
    delay_open=0.4, delay_move=0.3, timeout=3.0,
    stop_event=None, set_status_fn=None,
    num_tabs=6, hwnd=None
):
    """Ejecuta la secuencia completa de apertura de almacén y traslado de ítems por pestañas."""
    def status(txt, color="#C084FC"):
        if set_status_fn:
            set_status_fn(txt, color)

    status("VERIFICANDO ESTADO DEL ALMACÉN...", "#C084FC")
    abierto = buscar_y_clicar(img_check, confidence=0.80, click=False, hwnd=hwnd)

    if not abierto:
        status("ALMACÉN CERRADO. ABRIENDO...", "#C084FC")
        if not buscar_y_clicar(img_open, confidence=0.80, hwnd=hwnd):
            status("NO SE ENCONTRÓ EL BOTÓN ABRIR", "#EF4444")
            return False

        if _esperar(stop_event, delay_open):
            return False

        t0 = time.time()
        while time.time() - t0 < timeout:
            if stop_event and stop_event.is_set():
                return False
            if buscar_y_clicar(img_check, confidence=0.80, click=False, hwnd=hwnd):
                abierto = True
                break
            if _esperar(stop_event, 0.2):
                return False

    if not abierto:
        status("EL ALMACÉN NO SE ABRIÓ A TIEMPO", "#EF4444")
        return False

    status("ALMACÉN ABIERTO. INICIANDO TRASLADO POR PESTAÑAS...", "#22C55E")

    for tab_num in range(1, num_tabs + 1):
        if stop_event and stop_event.is_set():
            return False

        img_tab = ruta_recurso(os.path.join("assets", f"tab_{tab_num}.png"))
        status(f"SELECCIONANDO PESTAÑA {tab_num}...", "#3B82F6")

        if os.path.exists(img_tab):
            encontrado = buscar_y_clicar(img_tab, confidence=0.90, hwnd=hwnd)
            if not encontrado:
                buscar_y_clicar(img_tab, confidence=0.87, hwnd=hwnd)
            if _esperar(stop_event, 0.3):
                return False

        status(f"MOVIENDO ÍTEMS A PESTAÑA {tab_num}...", "#A855F7")
        buscar_y_clicar(img_move, confidence=0.88, hwnd=hwnd)
        if _esperar(stop_event, delay_move):
            return False

    status("TRASLADO COMPLETO EN TODAS LAS PESTAÑAS", "#22C55E")
    return True

def worker_vision(app_ref):
    """Worker ejecutado en hilo separado para gestionar el bucle del motor de visión."""
    tab = app_ref.tab_vision
    try:
        delay_open = max(0.05, float(tab.vision_open_delay.get()) / 1000.0)
    except ValueError:
        delay_open = 0.4

    try:
        delay_move = max(0.05, float(tab.vision_move_delay.get()) / 1000.0)
    except ValueError:
        delay_move = 0.3

    try:
        timeout_search = max(1.0, float(tab.vision_timeout.get()))
    except ValueError:
        timeout_search = 3.0

    try:
        lh = int(tab.vision_loop_h.get() or 0)
        lm = int(tab.vision_loop_m.get() or 0)
        ls = int(tab.vision_loop_s.get() or 0)
        loop_interval = max(1.0, (lh * 3600) + (lm * 60) + ls)
    except ValueError:
        loop_interval = 14400.0

    try:
        num_tabs = max(1, min(6, int(tab.vision_num_tabs.get())))
    except (ValueError, AttributeError):
        num_tabs = 6

    def set_status(texto, color):
        if hasattr(app_ref, "lbl_status") and app_ref.lbl_status:
            app_ref.lbl_status.configure(text=texto, text_color=color)

    while not app_ref.stop_event.is_set():
        focus_fn = getattr(tab, "focus_game_window", None)
        if focus_fn is not None:
            try:
                if tab.vision_focus_game.get():
                    focus_fn()
            except Exception:
                pass

        hwnd_game, reg = obtener_info_juego(TARGET_GAME_IDENTIFIER)
        if reg:
            set_status("VENTANA DETECTADA", "#C084FC")
        else:
            set_status("BUSCANDO VENTANA DEL JUEGO...", "#EAB308")

        ejecutar_ciclo_inventario(
            img_open=tab.img_open_path.get(),
            img_check=tab.img_check_path.get(),
            img_move=tab.img_move_path.get(),
            delay_open=delay_open,
            delay_move=delay_move,
            timeout=timeout_search,
            stop_event=app_ref.stop_event,
            set_status_fn=set_status,
            num_tabs=num_tabs,
            hwnd=hwnd_game
        )

        if not tab.vision_loop_enabled.get():
            app_ref.stop_event.wait(timeout=1.0)
            app_ref.after(0, app_ref.stop_all)
            break

        prox_t = time.time() + loop_interval
        while time.time() < prox_t:
            if app_ref.stop_event.is_set():
                return
            restante = int(prox_t - time.time())
            mins, secs = divmod(restante, 60)
            hrs, mins = divmod(mins, 60)
            set_status(f"PRÓXIMO TRASLADO EN: {hrs:02d}:{mins:02d}:{secs:02d}", "#22C55E")
            if app_ref.stop_event.wait(timeout=1):
                return


# =====================================================================
# UTILIDADES DE VENTANAS (usadas por la pestaña Flujos)
# =====================================================================
def listar_ventanas_visibles():
    """Devuelve [(hwnd, titulo), ...] con las ventanas visibles con título no vacío.

    Excluye diálogos/popups flotantes (con GW_OWNER) y duplicados por título.
    """
    vistos = set()
    ventanas = []

    def cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            titulo = win32gui.GetWindowText(hwnd)
            if not titulo or not titulo.strip():
                return
            if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
                return
            if titulo in vistos:
                return
            vistos.add(titulo)
            ventanas.append((hwnd, titulo))
        except Exception:
            pass

    win32gui.EnumWindows(cb, None)
    return ventanas


def enfocar_ventana(hwnd):
    """Trae una ventana al primer plano (misma técnica que la pestaña Inventario)."""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return False
    try:
        if win32gui.GetForegroundWindow() == hwnd and not win32gui.IsIconic(hwnd):
            return True
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        return True
    except Exception:
        return False


def hwnd_por_titulo(titulo):
    """Busca el hwnd de la primera ventana visible cuyo título contenga `titulo`."""
    if not titulo:
        return None
    titulo_low = titulo.lower()
    for hwnd, t in listar_ventanas_visibles():
        if titulo_low in t.lower():
            return hwnd
    return None