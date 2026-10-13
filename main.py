import ast
import time
import threading
import os
import sys
import tkinter as tk
import customtkinter as ctk
import ctypes
from PIL import Image, ImageDraw, ImageTk
import pystray
from pynput.mouse import Button, Controller as MouseController, Listener as MouseListener
from pynput.keyboard import Listener as KeyboardListener, Key, KeyCode, Controller as KeyboardController

from config import ruta_recurso, cargar_perfiles, guardar_perfil, nombre_valido
from clicker import worker_clicker_main
from macro_engine import worker_macro
from macro_recorder import MacroRecorder, serialize_key
from vision import worker_vision
from black_souls import worker_black_souls
from tab_flujos import TabFlujos

from tab_principal import TabPrincipal
from tab_secuencias import TabSecuencias
from tab_inventario import TabInventario
from tab_blacksouls import TabBlackSouls
from tab_ajustes import TabAjustes
from tab_about import TabAbout
from ui_components import StepCard, StatusLabel, COLORS, FONT, apply_dark_ttk_styles

# ----------------------------------------------------------------------
# Rutas de la carpeta assets/app
#   assets/app/app_icon.png            -> icono de ventana y bandeja
#   assets/app/app_icon.ico            -> icono de ventana / barra de tareas (Windows)
#   assets/app/ui_lightning_white.png  -> rayo blanco del logo en la sidebar
# ----------------------------------------------------------------------
def _key_from_str(texto):
    """Inverso de str(key) para los atajos guardados en perfiles.

    Acepta 'Key.f6', "'a'" (repr de KeyCode), '<65>' (solo código virtual),
    'vk_65' y un carácter suelto. Devuelve None si no se reconoce.
    """
    if not isinstance(texto, str) or not texto:
        return None
    try:
        if texto.startswith("Key."):
            return getattr(Key, texto[4:], None)
        if texto.startswith("<") and texto.endswith(">"):
            return KeyCode.from_vk(int(texto[1:-1]))
        if texto.startswith("vk_"):
            return KeyCode.from_vk(int(texto[3:]))
        if len(texto) >= 2 and texto[0] in "'\"" and texto[-1] == texto[0]:
            texto = ast.literal_eval(texto)
        if isinstance(texto, str) and len(texto) == 1:
            return KeyCode.from_char(texto)
    except Exception:
        pass
    return None


def ruta_asset_app(nombre):
    return ruta_recurso(os.path.join("assets", "app", nombre))


class AutoClickerVisionPro(ctk.CTk):
    def __init__(self):
        # En Windows, esto hace que la barra de tareas muestre TU icono
        # y no el de python.exe
        if sys.platform.startswith("win"):
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "AutoClickerStudioPro.App.1"
                )
            except Exception:
                pass

        super().__init__()
        self.title("AutoClicker Studio Pro")
        self.geometry("1020x740")
        self.minsize(940, 700)
        self.resizable(True, True)
        self.configure(fg_color=COLORS["bg"])

        self._set_window_icon()

        apply_dark_ttk_styles()

        self.mouse = MouseController()
        self.keyboard = KeyboardController()
        self.stop_event = threading.Event()
        self.active_mode = None
        self.worker_thread = None
        self._pending_mode = None   # motor esperando a que termine el worker anterior
        self._launch_token = 0      # invalida arranques pendientes (parada / otro motor)

        self.shift_pressed = False

        self.key_main = Key.f6
        self.key_macro = Key.f7
        self.key_vision = Key.f8
        self.key_bs = Key.f9
        self.key_record = Key.f10   # iniciar/detener la grabación de secuencias

        self.capture_target = None
        self.is_capturing_pos = False
        self.is_capturing_macro_pos = False

        self.is_recording = False
        self.recorder = MacroRecorder(on_change=self._on_recorder_change)
        self.profiles = cargar_perfiles()

        self.tray_icon = None
        self._init_tray_icon()
        self._build_ui()
        self._start_global_listeners()
        self._update_real_time_pos()

        self.bind("<Unmap>", self._on_minimize_window)
        self.protocol("WM_DELETE_WINDOW", self._on_close_window)

    def _set_window_icon(self):
        """Icono de la ventana y de la barra de tareas desde assets/app/."""
        png_path = ruta_asset_app("app_icon.png")
        ico_path = ruta_asset_app("app_icon.ico")

        # iconphoto necesita un PhotoImage de Tk (NO un CTkImage).
        # Se guarda la referencia en self para que el recolector no la borre.
        try:
            pil_icon = Image.open(png_path).convert("RGBA")
            self._window_icon = ImageTk.PhotoImage(pil_icon)
            self.iconphoto(True, self._window_icon)
        except Exception as e:
            print(f"No se pudo cargar el icono PNG de la ventana: {e}")

        # En Windows el .ico da mejor resultado en la barra de tareas.
        # CustomTkinter pone su icono por defecto ~200 ms después de abrir
        # la ventana, así que hay que aplicar el nuestro después.
        if sys.platform.startswith("win") and os.path.exists(ico_path):
            self.after(300, lambda: self._apply_ico(ico_path))

    def _apply_ico(self, ico_path):
        try:
            self.iconbitmap(ico_path)
        except Exception as e:
            print(f"No se pudo aplicar el .ico: {e}")

    def _init_tray_icon(self):
        # Icono con círculo morado para la bandeja del sistema (assets/app/)
        tray_icon_path = ruta_asset_app("app_icon.png")
        try:
            img = Image.open(tray_icon_path).resize((64, 64), Image.Resampling.LANCZOS)
        except Exception:
            img = Image.new('RGBA', (64, 64), color=(0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse((4, 4, 60, 60), fill="#7C3AED", outline="#A78BFA", width=2)
            draw.polygon([(34, 12), (20, 36), (32, 36), (30, 52), (44, 28), (32, 28)], fill="#FFFFFF")

        menu = pystray.Menu(
            pystray.MenuItem("Mostrar AutoClicker", self._restore_from_tray, default=True),
            pystray.MenuItem("Salir", self._exit_application)
        )
        self.tray_icon = pystray.Icon("AutoClickerStudio", img, "AutoClicker Studio Pro", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _on_minimize_window(self, event):
        if self.state() == 'iconic' and self.tab_cfg.check_tray.get() == 1:
            self.withdraw()

    def _restore_from_tray(self, icon=None, item=None):
        self.after(0, self._show_window)

    def _show_window(self):
        self.deiconify()
        self.state('normal')
        self.lift()
        self.focus_force()

    # ==================================================================
    # INTERFAZ: SIDEBAR + DASHBOARD
    # ==================================================================
    PAGE_INFO = {
        "main":   ("Principal",   "Clicker básico, intervalo y posición del cursor"),
        "macro":  ("Secuencias",  "Grabador y editor de macros de ratón y teclado"),
        "vision": ("Inventario",  "Detección por imagen · traslado de ítems por pestañas"),
        "bs":     ("Black Souls", "Farmeo automático con detección de combate"),
        "flows":  ("Flujos", "Constructor visual de automatizaciones por bloques"),
        "cfg":    ("Ajustes",     "Comportamiento, atajos y perfiles guardados"),
        "about":  ("Acerca de",   "Información, atajos y datos de la aplicación"),
    }

    def _build_ui(self):
        C = COLORS

        # ==========================================
        # 1. BARRA LATERAL IZQUIERDA (SIDEBAR)
        # ==========================================
        self.sidebar_frame = ctk.CTkFrame(self, width=224, fg_color=C["sidebar"], corner_radius=0)
        self.sidebar_frame.pack(side="left", fill="y")
        self.sidebar_frame.pack_propagate(False)

        ctk.CTkFrame(self, width=1, fg_color=C["border_soft"], corner_radius=0).pack(side="left", fill="y")

        # Logo con imagen personalizada (rayo blanco)
        f_title = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        f_title.pack(fill="x", padx=18, pady=(22, 4))
        badge = ctk.CTkFrame(f_title, width=34, height=34, corner_radius=10, fg_color=C["accent"])
        badge.pack(side="left")
        badge.pack_propagate(False)

        try:
            ui_icon_path = ruta_asset_app("ui_lightning_white.png")
            self.logo_img = ctk.CTkImage(light_image=Image.open(ui_icon_path), dark_image=Image.open(ui_icon_path), size=(18, 18))
            ctk.CTkLabel(badge, text="", image=self.logo_img).pack(expand=True)
        except Exception:
            ctk.CTkLabel(badge, text="⚡", font=(FONT, 16), text_color="#FFFFFF").pack(expand=True)

        f_logo = ctk.CTkFrame(f_title, fg_color="transparent")
        f_logo.pack(side="left", padx=(10, 0))
        f_logo_row = ctk.CTkFrame(f_logo, fg_color="transparent")
        f_logo_row.pack(anchor="w")
        ctk.CTkLabel(f_logo_row, text="Auto", font=(FONT, 16, "bold"), text_color=C["text"]).pack(side="left")
        ctk.CTkLabel(f_logo_row, text="Clicker", font=(FONT, 16, "bold"), text_color=C["accent_light"]).pack(side="left")
        ctk.CTkLabel(f_logo, text="STUDIO PRO", font=(FONT, 8, "bold"), text_color=C["text_mute"]).pack(anchor="w")

        ctk.CTkLabel(self.sidebar_frame, text="MENÚ", font=(FONT, 9, "bold"),
                     text_color=C["text_mute"], anchor="w").pack(fill="x", padx=20, pady=(22, 6))

        # Botones de navegación con indicador vertical violeta pegado al borde izquierdo
        self.nav_buttons = {}
        self.nav_indicators = {}
        tabs = [
            ("main", "📌", "Principal"),
            ("macro", "⚡", "Secuencias"),
            ("vision", "📦", "Inventario"),
            ("bs", "🐰", "Black Souls"),
            ("flows", "🔀", "Flujos"),
            ("cfg", "⚙️", "Ajustes"),
            ("about", "ℹ️", "Acerca de"),
        ]
        for tab_id, icon, label in tabs:
            row = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent", height=42, corner_radius=0)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            indicator = ctk.CTkFrame(row, width=4, fg_color="transparent", corner_radius=2)
            indicator.pack(side="left", fill="y", pady=5)

            btn = ctk.CTkButton(
                row, text=f"{icon}   {label}", font=(FONT, 12, "bold"), anchor="w",
                height=34, corner_radius=8, fg_color="transparent",
                text_color=C["text_dim"], hover_color=C["card_alt"],
                command=lambda t=tab_id: self._switch_tab(t),
            )
            btn.pack(side="left", fill="x", expand=True, padx=(8, 12), pady=4)
            self.nav_buttons[tab_id] = btn
            self.nav_indicators[tab_id] = indicator

        # Pie de la sidebar: recordatorio discreto de la parada de emergencia
        ctk.CTkLabel(self.sidebar_frame, text="Shift + Esc  ·  detener todo", font=(FONT, 10),
                     text_color=C["text_mute"]).pack(side="bottom", pady=20)

        # ==========================================
        # 2. PANEL DERECHO (DASHBOARD)
        # ==========================================
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(side="left", fill="both", expand=True, padx=30, pady=(26, 18))

        # Encabezado de página
        self.page_header = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.page_header.pack(side="top", fill="x", pady=(0, 20))
        self.lbl_page_title = ctk.CTkLabel(self.page_header, text="", anchor="w",
                                           font=(FONT, 22, "bold"), text_color=C["text"])
        self.lbl_page_title.pack(anchor="w")
        self.lbl_page_sub = ctk.CTkLabel(self.page_header, text="", anchor="w",
                                         font=(FONT, 11), text_color=C["text_mute"])
        self.lbl_page_sub.pack(anchor="w")

        # Franja de estado
        self.bottom_bar = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.bottom_bar.pack(side="bottom", fill="x", pady=(16, 0))
        self.status_dot = ctk.CTkLabel(self.bottom_bar, text="●", font=(FONT, 10), text_color=C["error"])
        self.status_dot.pack(side="left", padx=(0, 8))
        self.lbl_status = StatusLabel(self.bottom_bar, text="ESTADO: DETENIDO", font=(FONT, 10, "bold"),
                                      text_color=C["error"], anchor="w")
        self.lbl_status.pack(side="left")
        self.lbl_status.add_listener(lambda text, color: self.status_dot.configure(text_color=color))

        # Área de pestañas
        self.content_area = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.content_area.pack(side="top", fill="both", expand=True)

        self.tab_main = TabPrincipal(self.content_area, self)
        self.tab_macro = TabSecuencias(self.content_area, self)
        self.tab_vision = TabInventario(self.content_area, self)
        self.tab_bs = TabBlackSouls(self.content_area, self)
        self.tab_flows = TabFlujos(self.content_area, self)
        self.tab_cfg = TabAjustes(self.content_area, self)
        self.tab_about = TabAbout(self.content_area, self)

        self._switch_tab("main")

    def _switch_tab(self, target):
        self.tab_main.pack_forget()
        self.tab_macro.pack_forget()
        self.tab_vision.pack_forget()
        self.tab_bs.pack_forget()
        self.tab_flows.pack_forget()
        self.tab_cfg.pack_forget()
        self.tab_about.pack_forget()

        for tab_id, btn in self.nav_buttons.items():
            btn.configure(fg_color="transparent", text_color=COLORS["text_dim"])
            self.nav_indicators[tab_id].configure(fg_color="transparent")

        active_btn = self.nav_buttons.get(target)
        if active_btn:
            active_btn.configure(fg_color=COLORS["card"], text_color=COLORS["accent_text"])
            self.nav_indicators[target].configure(fg_color=COLORS["accent"])

        title, subtitle = self.PAGE_INFO.get(target, ("", ""))
        self.lbl_page_title.configure(text=title)
        self.lbl_page_sub.configure(text=subtitle)

        if target == "main":
            self.tab_main.pack(fill="both", expand=True)
        elif target == "macro":
            self.tab_macro.pack(fill="both", expand=True)
            self.tab_macro.macro_scroll._on_configure()
            self.tab_macro.on_show()
        elif target == "vision":
            self.tab_vision.pack(fill="both", expand=True)
        elif target == "bs":
            self.tab_bs.pack(fill="both", expand=True)
            self.tab_bs.on_show()
        elif target == "flows":
            self.tab_flows.pack(fill="both", expand=True)
            self.tab_flows.on_show()
        elif target == "cfg":
            self.tab_cfg.pack(fill="both", expand=True)
            self.tab_cfg.on_show()
        elif target == "about":
            self.tab_about.pack(fill="both", expand=True)
            self.tab_about.on_show()

    def _get_key_name(self, k):
        return getattr(k, 'name', str(k).replace("'", "")).upper()

    def _toggle_topmost(self):
        self.attributes("-topmost", self.tab_cfg.check_topmost.get() == 1)

    def _update_real_time_pos(self):
        if self.tab_main.winfo_ismapped():
            x, y = self.mouse.position
            self.tab_main.lbl_realtime_pos.configure(text=f"Cursor en tiempo real: X: {int(x)}, Y: {int(y)}")
        self.after(150, self._update_real_time_pos)

    def is_inside_window(self, x, y):
        try:
            if not self.winfo_exists() or not self.winfo_ismapped():
                return False
            wx = self.winfo_rootx()
            wy = self.winfo_rooty()
            ww = self.winfo_width()
            wh = self.winfo_height()
            return (wx <= x <= wx + ww) and (wy <= y <= wy + wh)
        except Exception:
            return False

    def _on_recorder_change(self, n_events):
        """El grabador avisa (desde el hilo del listener) de cuántos eventos lleva."""
        try:
            self.after(0, lambda: self.tab_macro.show_rec_count(n_events))
        except Exception:
            pass

    def _start_global_listeners(self):
        def on_key_press(key):
            if key in (Key.shift, Key.shift_r, Key.shift_l):
                self.shift_pressed = True

            if key == Key.esc and self.shift_pressed:
                self.after(0, self.stop_all)
                return

            # Atajo de grabación: inicia / detiene (o cancela la cuenta regresiva)
            if key == self.key_record and self.capture_target is None:
                self.after(0, self.tab_macro.toggle_recording)
                return

            if self.is_recording:
                if key in (self.key_main, self.key_macro, self.key_vision, self.key_bs):
                    return
                self.recorder.key_down(key)
                return

            if self.capture_target == "key_record":
                self.key_record = key
                k_name = self._get_key_name(key)
                self.after(0, lambda: self.tab_macro.btn_hk_record.configure(text=f"Atajo: {k_name}"))
                self.capture_target = None
                return

            if self.capture_target == "key_main":
                self.key_main = key
                k_name = self._get_key_name(key)
                self.after(0, lambda: self.tab_cfg.btn_hk_main.configure(text=f"Atajo: {k_name}"))
                self.after(0, self.tab_main.refresh_hotkey_label)
                self.capture_target = None
                return

            if self.capture_target == "key_macro":
                self.key_macro = key
                k_name = self._get_key_name(key)
                self.after(0, lambda: self.tab_cfg.btn_hk_macro.configure(text=f"Atajo: {k_name}"))
                self.after(0, self.tab_macro.refresh_hotkey_label)
                self.capture_target = None
                return

            if self.capture_target == "key_vision":
                self.key_vision = key
                k_name = self._get_key_name(key)
                self.after(0, lambda: self.tab_cfg.btn_hk_vision.configure(text=f"Atajo: {k_name}"))
                self.after(0, self.tab_vision.refresh_hotkey_label)
                self.capture_target = None
                return

            if self.capture_target == "key_bs":
                self.key_bs = key
                k_name = self._get_key_name(key)
                self.after(0, lambda: self.tab_cfg.btn_hk_bs.configure(text=f"Atajo: {k_name}"))
                self.after(0, self.tab_bs.refresh_hotkey_label)
                self.capture_target = None
                return

            if self.capture_target == "macro_key":
                k_serial, display_name = serialize_key(key)
                self.tab_macro.temp_macro_key = k_serial
                self.tab_macro.temp_macro_key_display = str(display_name)
                self.after(0, lambda: self.tab_macro.lbl_macro_key.configure(text=f"[{self.tab_macro.temp_macro_key_display.upper()}]"))
                self.after(0, lambda: self.tab_macro.btn_macro_key.configure(text="⌨️ Tecla"))
                self.capture_target = None
                return

            if key == self.key_main and not self.capture_target:
                self.after(0, lambda: self.toggle_engine("principal"))
            elif key == self.key_macro and not self.capture_target:
                self.after(0, lambda: self.toggle_engine("macro"))
            elif key == self.key_vision and not self.capture_target:
                self.after(0, lambda: self.toggle_engine("vision"))
            elif key == self.key_bs and not self.capture_target:
                self.after(0, lambda: self.toggle_engine("blacksouls"))

        def on_key_release(key):
            if key in (Key.shift, Key.shift_r, Key.shift_l):
                self.shift_pressed = False

            if self.is_recording:
                self.recorder.key_up(key)

        def on_mouse_click(x, y, button, pressed):
            if self.is_inside_window(x, y):
                return

            if self.is_recording:
                self.recorder.mouse_button(x, y, button, pressed)
                return

            if not pressed:
                return

            if self.is_capturing_pos:
                self.after(0, lambda: self.tab_main.entry_x.delete(0, "end"))
                self.after(0, lambda: self.tab_main.entry_x.insert(0, str(int(x))))
                self.after(0, lambda: self.tab_main.entry_y.delete(0, "end"))
                self.after(0, lambda: self.tab_main.entry_y.insert(0, str(int(y))))
                self.after(0, lambda: self.tab_main.pos_mode.set("fixed"))
                self.after(0, lambda: self.tab_main.btn_capture.configure(text="Capturar"))
                self.is_capturing_pos = False

            elif self.is_capturing_macro_pos:
                self.tab_macro.temp_macro_x = int(x)
                self.tab_macro.temp_macro_y = int(y)
                self.after(0, lambda: self.tab_macro.lbl_macro_pos.configure(text=f"({int(x)},{int(y)})"))
                self.after(0, lambda: self.tab_macro.btn_macro_pos.configure(text="📍 Coord"))
                self.is_capturing_macro_pos = False

        self.kb_listener = KeyboardListener(on_press=on_key_press, on_release=on_key_release)
        self.kb_listener.daemon = True
        self.kb_listener.start()

        def on_mouse_scroll(x, y, dx, dy):
            if self.is_recording and not self.is_inside_window(x, y):
                self.recorder.scroll(x, y, dx, dy)

        self.mouse_listener = MouseListener(on_click=on_mouse_click, on_scroll=on_mouse_scroll)
        self.mouse_listener.daemon = True
        self.mouse_listener.start()

    def _prepare_hotkey_capture(self, target):
        self.capture_target = target
        if target == "key_main": self.tab_cfg.btn_hk_main.configure(text="Presiona...")
        elif target == "key_macro": self.tab_cfg.btn_hk_macro.configure(text="Presiona...")
        elif target == "key_vision": self.tab_cfg.btn_hk_vision.configure(text="Presiona...")
        elif target == "key_bs": self.tab_cfg.btn_hk_bs.configure(text="Presiona...")
        elif target == "key_record": self.tab_macro.btn_hk_record.configure(text="Presiona...")

    def _prepare_capture_pos(self):
        self.is_capturing_pos = True
        self.tab_main.btn_capture.configure(text="Clic fuera...")

    def _prepare_capture_macro_pos(self):
        self.is_capturing_macro_pos = True
        self.tab_macro.btn_macro_pos.configure(text="Clic fuera...")

    def _prepare_capture_macro_key(self):
        self.capture_target = "macro_key"
        self.tab_macro.btn_macro_key.configure(text="Presiona...")

    def stop_all(self):
        # Shift+Esc también cancela un flujo independiente.
        try:
            if hasattr(self, "tab_flows"):
                self.tab_flows.stop_from_app()
        except Exception:
            pass
        self._launch_token += 1
        self._pending_mode = None
        self.stop_event.set()
        self.active_mode = None
        self.lbl_status.configure(text="ESTADO: DETENIDO", text_color="#EF4444")
        for c in self.tab_macro.step_cards:
            c.set_active(False)
        if self.is_recording or self.tab_macro.is_counting_down():
            self.tab_macro.stop_recording(trim_stop_combo=True)

    def toggle_engine(self, mode):
        if self.active_mode == mode:
            self.stop_all()
            return

        # Segundo toque del atajo mientras el motor espera para arrancar = cancelar
        if self._pending_mode == mode:
            self.stop_all()
            return

        if self.active_mode is not None:
            self.stop_event.set()
            self.active_mode = None

        # No se limpia stop_event hasta que el worker anterior haya muerto de verdad:
        # así nunca quedan dos workers a la vez ni se "resucita" uno que estaba parando.
        self._launch_token += 1
        self._pending_mode = mode
        self._launch_when_free(mode, self._launch_token, 0)

    def _launch_when_free(self, mode, token, intentos):
        if token != self._launch_token:
            return   # llegó una parada u otro arranque: este queda cancelado
        hilo = self.worker_thread
        if hilo is not None and hilo.is_alive():
            self.stop_event.set()
            if intentos >= 50:   # ~5 s
                self._pending_mode = None
                self.lbl_status.configure(text="ERROR: EL MOTOR ANTERIOR NO RESPONDE",
                                          text_color="#EF4444")
                return
            self.after(100, lambda: self._launch_when_free(mode, token, intentos + 1))
            return
        self._pending_mode = None
        self._start_engine(mode)

    def _start_engine(self, mode):
        self.stop_event.clear()
        self.active_mode = mode

        if mode == "principal":
            self.tab_main.on_engine_started()
            self.lbl_status.configure(text="ESTADO: CLICKER ACTIVO", text_color="#22C55E")
            self.worker_thread = threading.Thread(target=worker_clicker_main, args=(self,), daemon=True)
            self.worker_thread.start()

        elif mode == "macro":
            if not self.tab_macro.step_cards:
                self.lbl_status.configure(text="ERROR: SECUENCIA VACÍA", text_color="#EF4444")
                self.active_mode = None
                return
            self.tab_macro.on_engine_started()
            self.lbl_status.configure(text="ESTADO: SECUENCIA ACTIVA", text_color="#22C55E")
            self.worker_thread = threading.Thread(target=worker_macro, args=(self,), daemon=True)
            self.worker_thread.start()

        elif mode == "vision":
            self.tab_vision.on_engine_started()
            self.worker_thread = threading.Thread(target=worker_vision, args=(self,), daemon=True)
            self.worker_thread.start()

        elif mode == "blacksouls":
            self.tab_bs.on_engine_started()
            def _num(var, defecto):
                try:
                    return float(str(var.get()).strip().replace(",", ".") or defecto)
                except ValueError:
                    return defecto

            lista_pasos = []
            for p in self.tab_bs.bs_pasos_vars:
                item = {"desc": p["desc"], "tipo": p["tipo"]}
                if p["tipo"] == "mov":
                    item["dir"] = p["dir"]
                    item["veces"] = p["veces"]
                    item["press_ms"] = _num(p["press"], 220)
                    item["wait_ms"] = _num(p["wait"], 140)
                elif p["tipo"] == "espera":
                    item["seg"] = _num(p["seg"], 5.0)
                lista_pasos.append(item)

            self.worker_thread = threading.Thread(
                target=worker_black_souls,
                args=(
                    self.tab_bs.img_bs_combate.get(),
                    lista_pasos,
                    self.stop_event,
                    lambda txt, col: self.lbl_status.configure(text=txt, text_color=col)
                ),
                daemon=True
            )
            self.worker_thread.start()

    def _save_profile(self):
        escrito = self.tab_cfg.entry_profile_name.get().strip()
        name = nombre_valido(escrito)          # nombre seguro = nombre del archivo en perfiles/
        existia = name in self.profiles
        macro_data = [card.get_current_data() for card in self.tab_macro.step_cards]

        bs_data = []
        for p in self.tab_bs.bs_pasos_vars:
            d = {"tipo": p["tipo"]}
            if p["tipo"] == "mov":
                d["press"] = p["press"].get()
                d["wait"] = p["wait"].get()
            elif p["tipo"] == "interact":
                d["delay"] = p["delay"].get()
            elif p["tipo"] == "espera":
                d["seg"] = p["seg"].get()
            bs_data.append(d)

        self.profiles[name] = {
            "h": self.tab_main.entry_h.get(), "m": self.tab_main.entry_m.get(), "s": self.tab_main.entry_s.get(), "ms": self.tab_main.entry_ms.get(),
            "btn": self.tab_main.combo_btn.get(), "type": self.tab_main.combo_type.get(),
            "rep_mode": self.tab_main.repeat_mode.get(), "rep_count": self.tab_main.entry_repeats.get(),
            "pos_mode": self.tab_main.pos_mode.get(), "x": self.tab_main.entry_x.get(), "y": self.tab_main.entry_y.get(),
            "macro_steps": macro_data,
            "macro_rep_mode": self.tab_macro.macro_repeat_mode.get(),
            "macro_rep_count": self.tab_macro.entry_macro_repeats.get(),
            "macro_speed": self.tab_macro.macro_speed.get(),
            "topmost": self.tab_cfg.check_topmost.get(),
            "minimize_tray": self.tab_cfg.check_tray.get(),
            "countdown": self.tab_cfg.check_countdown.get(),
            "key_main": str(self.key_main),
            "key_macro": str(self.key_macro),
            "key_vision": str(self.key_vision),
            "key_bs": str(self.key_bs),
            "key_record": str(self.key_record),
            "img_open": self.tab_vision.img_open_path.get(),
            "img_check": self.tab_vision.img_check_path.get(),
            "img_move": self.tab_vision.img_move_path.get(),
            "img_bs_combate": self.tab_bs.img_bs_combate.get(),
            "img_bs_inicio": self.tab_bs.img_bs_inicio.get(),
            "bs_steps_data": bs_data,
            "vision_open_delay": self.tab_vision.vision_open_delay.get(),
            "vision_move_delay": self.tab_vision.vision_move_delay.get(),
            "vision_timeout": self.tab_vision.vision_timeout.get(),
            "vision_loop_enabled": self.tab_vision.vision_loop_enabled.get(),
            "vision_loop_h": self.tab_vision.vision_loop_h.get(),
            "vision_loop_m": self.tab_vision.vision_loop_m.get(),
            "vision_loop_s": self.tab_vision.vision_loop_s.get(),
            "vision_num_tabs": self.tab_vision.vision_num_tabs.get(),
            "vision_minimize_on_start": self.tab_vision.vision_minimize_on_start.get(),
            "vision_focus_game": self.tab_vision.vision_focus_game.get()
        }
        try:
            guardar_perfil(name, self.profiles[name])
        except OSError as exc:
            if not existia:
                self.profiles.pop(name, None)
            self.tab_cfg.notify(f"No se pudo guardar el perfil: {exc.strerror or exc}", "error")
            return
        self.tab_cfg.refresh_profiles(select=name)
        self.tab_cfg.entry_profile_name.delete(0, "end")
        accion = "actualizado" if existia else "guardado"
        extra = f" (nombre ajustado desde «{escrito}»)" if escrito and escrito != name else ""
        self.tab_cfg.notify(f"Perfil «{name}» {accion}{extra}")

    def _load_selected_profile(self):
        name = self.tab_cfg.combo_profiles.get()
        if name in self.profiles:
            cfg = self.profiles[name]
            self.tab_main.entry_h.delete(0, "end"); self.tab_main.entry_h.insert(0, cfg.get("h", "0"))
            self.tab_main.entry_m.delete(0, "end"); self.tab_main.entry_m.insert(0, cfg.get("m", "0"))
            self.tab_main.entry_s.delete(0, "end"); self.tab_main.entry_s.insert(0, cfg.get("s", "0"))
            self.tab_main.entry_ms.delete(0, "end"); self.tab_main.entry_ms.insert(0, cfg.get("ms", "100"))
            self.tab_main.combo_btn.set(cfg.get("btn", "Izquierdo"))
            self.tab_main.combo_type.set(cfg.get("type", "Simple"))
            self.tab_main.repeat_mode.set(cfg.get("rep_mode", "infinite"))
            self.tab_main.entry_repeats.delete(0, "end"); self.tab_main.entry_repeats.insert(0, cfg.get("rep_count", "100"))
            self.tab_main.pos_mode.set(cfg.get("pos_mode", "current"))
            self.tab_main.entry_x.delete(0, "end"); self.tab_main.entry_x.insert(0, cfg.get("x", "0"))
            self.tab_main.entry_y.delete(0, "end"); self.tab_main.entry_y.insert(0, cfg.get("y", "0"))

            self.tab_macro.macro_repeat_mode.set(cfg.get("macro_rep_mode", "infinite"))
            self.tab_macro.entry_macro_repeats.delete(0, "end"); self.tab_macro.entry_macro_repeats.insert(0, cfg.get("macro_rep_count", "10"))
            self.tab_macro.macro_speed.set(cfg.get("macro_speed", "1x"))

            self.tab_vision.img_open_path.set(cfg.get("img_open", ruta_recurso("assets/boton_abrir.png")))
            self.tab_vision.img_check_path.set(cfg.get("img_check", ruta_recurso("assets/inventario_abierto.png")))
            self.tab_vision.img_move_path.set(cfg.get("img_move", ruta_recurso("assets/boton_mover.png")))
            self.tab_bs.img_bs_combate.set(cfg.get("img_bs_combate", ruta_recurso("assets/bs_menu_combate.png")))
            self.tab_bs.img_bs_inicio.set(cfg.get("img_bs_inicio", ruta_recurso("assets/bs_initial_position.png")))

            bs_saved = cfg.get("bs_steps_data", [])
            bs_pasos = self.tab_bs.bs_pasos_vars
            if (len(bs_saved) == len(bs_pasos)
                    and all(d.get("tipo") == p["tipo"] for d, p in zip(bs_saved, bs_pasos))):
                for p, d in zip(bs_pasos, bs_saved):
                    if p["tipo"] == "mov":
                        p["press"].set(d.get("press", "220"))
                        p["wait"].set(d.get("wait", "140"))
                    elif p["tipo"] == "espera":
                        p["seg"].set(d.get("seg", p.get("seg_def", "5.0")))
            else:
                self.tab_bs._reset_calibration()

            self.tab_vision.vision_open_delay.set(cfg.get("vision_open_delay", "400"))
            self.tab_vision.vision_move_delay.set(cfg.get("vision_move_delay", "300"))
            self.tab_vision.vision_timeout.set(cfg.get("vision_timeout", "3.0"))

            self.tab_vision.vision_loop_enabled.set(cfg.get("vision_loop_enabled", True))
            self.tab_vision.vision_loop_h.set(cfg.get("vision_loop_h", "4"))
            self.tab_vision.vision_loop_m.set(cfg.get("vision_loop_m", "0"))
            self.tab_vision.vision_loop_s.set(cfg.get("vision_loop_s", "0"))
            self.tab_vision.vision_num_tabs.set(str(cfg.get("vision_num_tabs", "6")))
            self.tab_vision.vision_minimize_on_start.set(cfg.get("vision_minimize_on_start", False))
            self.tab_vision.vision_focus_game.set(cfg.get("vision_focus_game", True))

            self.tab_macro.clear_all_steps()
            self.tab_macro.add_steps(cfg.get("macro_steps", []))

            if cfg.get("topmost"): self.tab_cfg.check_topmost.select()
            else: self.tab_cfg.check_topmost.deselect()
            self._toggle_topmost()

            if cfg.get("minimize_tray"): self.tab_cfg.check_tray.select()
            else: self.tab_cfg.check_tray.deselect()

            if cfg.get("countdown"): self.tab_cfg.check_countdown.select()
            else: self.tab_cfg.check_countdown.deselect()

            self._restore_hotkeys(cfg)
            self.tab_cfg.notify(f"Perfil «{name}» cargado")
        else:
            self.tab_cfg.notify("Ese perfil no existe: guarda uno primero.", "warning")

    def _restore_hotkeys(self, cfg):
        """Aplica los atajos guardados en el perfil (los ausentes o inválidos no se tocan)."""
        for attr in ("key_main", "key_macro", "key_vision", "key_bs", "key_record"):
            key = _key_from_str(cfg.get(attr))
            if key is not None:
                setattr(self, attr, key)

        self.capture_target = None
        for attr, btn in (("key_main", self.tab_cfg.btn_hk_main),
                          ("key_macro", self.tab_cfg.btn_hk_macro),
                          ("key_vision", self.tab_cfg.btn_hk_vision),
                          ("key_bs", self.tab_cfg.btn_hk_bs),
                          ("key_record", self.tab_macro.btn_hk_record)):
            btn.configure(text=f"Atajo: {self._get_key_name(getattr(self, attr))}")

        for tab in (self.tab_main, self.tab_macro, self.tab_vision, self.tab_bs):
            tab.refresh_hotkey_label()
        self.tab_about.refresh()

    def _on_close_window(self):
        if self.tab_cfg.check_tray.get() == 1:
            self.withdraw()
        else:
            self._exit_application()

    def _exit_application(self, icon=None, item=None):
        self.stop_all()
        try:
            self.kb_listener.stop()
            self.mouse_listener.stop()
        except Exception:
            pass
        if self.tray_icon:
            self.tray_icon.stop()
        self.after(0, self.destroy)

if __name__ == "__main__":
    app = AutoClickerVisionPro()
    app.mainloop()