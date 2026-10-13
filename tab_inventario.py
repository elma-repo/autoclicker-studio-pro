import os
import re
import time
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from config import ruta_recurso, TARGET_GAME_IDENTIFIER
from ui_components import (
    COLORS, FONT, Card, StatusDot, LogConsole, LabeledField, ImagePathRow,
    styled_entry, styled_option_menu, styled_switch, primary_button, ghost_button,
)

MAX_TABS = 6  # assets/tab_1.png ... tab_6.png

# Colores que usan los workers → nivel de log
_LEVEL_BY_COLOR = {
    "#22C55E": "ok",
    "#A855F7": "proc", "#9333EA": "proc", "#C084FC": "proc", "#3B82F6": "proc",
    "#EF4444": "err",
    "#EAB308": "warn",
}


class TabInventario(ctk.CTkFrame):
    def __init__(self, master, app_ref):
        super().__init__(master, fg_color="transparent")
        self.app_ref = app_ref

        # ---- Variables (mismos nombres que antes: las usan vision.py y los perfiles) ----
        self.img_open_path = tk.StringVar(value=ruta_recurso("assets/boton_abrir.png"))
        self.img_check_path = tk.StringVar(value=ruta_recurso("assets/inventario_abierto.png"))
        self.img_move_path = tk.StringVar(value=ruta_recurso("assets/boton_mover.png"))

        self.vision_open_delay = tk.StringVar(value="400")
        self.vision_move_delay = tk.StringVar(value="300")
        self.vision_timeout = tk.StringVar(value="3.0")

        self.vision_loop_enabled = tk.BooleanVar(value=True)
        self.vision_loop_h = tk.StringVar(value="4")
        self.vision_loop_m = tk.StringVar(value="0")
        self.vision_loop_s = tk.StringVar(value="0")

        # ---- Variables nuevas ----
        self.vision_num_tabs = tk.StringVar(value=str(MAX_TABS))
        self.vision_minimize_on_start = tk.BooleanVar(value=False)
        self.vision_focus_game = tk.BooleanVar(value=True)

        # ---- Estado interno de la UI ----
        self._running = False
        self._last_text = None
        self._waiting_logged = False
        self._assets_win = None

        self._build_ui()

        # Indicador compacto de assets: se actualiza si cambia cualquier ruta
        for var in (self.img_open_path, self.img_check_path, self.img_move_path):
            var.trace_add("write", lambda *_: self._refresh_assets())
        self._refresh_assets()

        # Escucha los cambios de estado que publican los workers (vision.py no se toca).
        lbl = getattr(app_ref, "lbl_status", None)
        if lbl is not None and hasattr(lbl, "add_listener"):
            lbl.add_listener(self._on_status)

        self.log("Sistema listo. Esperando inicio de rutina.", "ok")

    # ==================================================================
    # CONSTRUCCIÓN DE LA INTERFAZ
    # ==================================================================
    def _build_ui(self):
        self._build_run_bar()

        # Una sola fila con dos tarjetas compactas: Configuración | Opciones
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=(16, 0))
        row.grid_columnconfigure(0, weight=1, uniform="cols")
        row.grid_columnconfigure(1, weight=1, uniform="cols")
        self._build_config_card(row).grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._build_options_card(row).grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self.console = LogConsole(self, title="Registro", height=110)
        self.console.pack(fill="both", expand=True, pady=(16, 0))

    # ---------------- Barra superior: solo el botón de inicio ----------------
    def _build_run_bar(self):
        self.btn_run = primary_button(
            self, "", height=40,
            command=lambda: self.app_ref.toggle_engine("vision"),
        )
        self.btn_run.pack(fill="x")
        self._update_run_button()

    # ---------------- Tarjeta: configuración ----------------
    def _build_config_card(self, parent):
        card = Card(parent, title="Configuración")
        body = card.body

        # Indicador compacto de assets (en lugar de las rutas completas)
        f_assets = ctk.CTkFrame(body, fg_color="transparent")
        f_assets.pack(fill="x", pady=(0, 16))
        self.assets_dot = StatusDot(f_assets, size=8, color=COLORS["text_mute"])
        self.assets_dot.pack(side="left", padx=(0, 8))
        self.lbl_assets = ctk.CTkLabel(f_assets, text="", anchor="w", font=(FONT, 11),
                                       text_color=COLORS["text"])
        self.lbl_assets.pack(side="left")
        ghost_button(f_assets, "Cambiar", command=self._open_assets_dialog,
                     width=64, height=24).pack(side="right")

        grid = ctk.CTkFrame(body, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)

        f_tabs = ctk.CTkFrame(grid, fg_color="transparent")
        f_tabs.grid(row=0, column=0, sticky="w", pady=(0, 14))
        ctk.CTkLabel(f_tabs, text="Pestañas", font=(FONT, 10), text_color=COLORS["text_dim"],
                     anchor="w").pack(fill="x")
        self.opt_tabs = styled_option_menu(
            f_tabs, values=[str(i) for i in range(1, MAX_TABS + 1)],
            variable=self.vision_num_tabs, width=84,
        )
        self.opt_tabs.pack(anchor="w", pady=(2, 0))

        LabeledField(grid, "Timeout", self.vision_timeout, "s", width=56).grid(
            row=0, column=1, sticky="w", pady=(0, 14))
        LabeledField(grid, "Tras abrir", self.vision_open_delay, "ms", width=56).grid(
            row=1, column=0, sticky="w")
        LabeledField(grid, "Tras mover", self.vision_move_delay, "ms", width=56).grid(
            row=1, column=1, sticky="w")
        return card

    # ---------------- Tarjeta: opciones (interruptores) ----------------
    def _build_options_card(self, parent):
        card = Card(parent, title="Opciones")
        body = card.body

        styled_switch(body, "Repetir cada", variable=self.vision_loop_enabled).pack(anchor="w")
        f_loop = ctk.CTkFrame(body, fg_color="transparent")
        f_loop.pack(anchor="w", padx=(46, 0), pady=(8, 16))
        for lbl, var in (("H", self.vision_loop_h), ("M", self.vision_loop_m), ("S", self.vision_loop_s)):
            ctk.CTkLabel(f_loop, text=lbl, font=(FONT, 10),
                         text_color=COLORS["text_mute"]).pack(side="left", padx=(0, 4))
            styled_entry(f_loop, textvariable=var, width=40, height=26, justify="center").pack(
                side="left", padx=(0, 10))

        styled_switch(body, "Minimizar al iniciar", variable=self.vision_minimize_on_start).pack(
            anchor="w", pady=(0, 16))
        styled_switch(body, "Enfocar ventana del juego", variable=self.vision_focus_game).pack(anchor="w")
        return card

    # ---------------- Assets: indicador compacto + diálogo ----------------
    def _refresh_assets(self):
        paths = (self.img_open_path, self.img_check_path, self.img_move_path)
        ok = sum(1 for v in paths if os.path.exists(v.get()))
        self._assets_ok = ok
        if ok == len(paths):
            color, text = COLORS["success"], f"Assets cargados ({ok}/3)"
        elif ok == 0:
            color, text = COLORS["error"], f"Assets no encontrados ({ok}/3)"
        else:
            color, text = COLORS["warning"], f"Assets incompletos ({ok}/3)"
        self.assets_dot.set_color(color)
        self.lbl_assets.configure(text=text)

    def _open_assets_dialog(self):
        """Ventana pequeña para cambiar las 3 imágenes (las rutas largas ya no ocupan la pestaña)."""
        if self._assets_win is not None and self._assets_win.winfo_exists():
            self._assets_win.focus()
            return

        win = ctk.CTkToplevel(self)
        win.title("Assets de detección")
        win.configure(fg_color=COLORS["bg"])
        win.geometry("660x250")
        win.resizable(False, False)
        win.transient(self.winfo_toplevel())

        card = ctk.CTkFrame(win, fg_color=COLORS["card"], corner_radius=12, border_width=0)
        card.pack(fill="both", expand=True, padx=24, pady=24)
        rows = (
            ("Botón Abrir", self.img_open_path),
            ("Check Abierto", self.img_check_path),
            ("Botón Mover", self.img_move_path),
        )
        for label, var in rows:
            ImagePathRow(card, label, var, on_browse=lambda v=var: self._select_image_file(v)).pack(
                fill="x", padx=22, pady=(14, 0))
        primary_button(card, "Listo", command=win.destroy, width=90, height=32).pack(
            anchor="e", padx=22, pady=(18, 18))

        self._assets_win = win
        win.after(200, lambda: win.winfo_exists() and (win.lift(), win.focus_force()))

    # ==================================================================
    # API PÚBLICA (la usa main.py)
    # ==================================================================
    def log(self, message, level="info"):
        self.console.log(message, level)

    def on_engine_started(self):
        """Llamado por main.toggle_engine('vision') justo antes de lanzar el worker."""
        self._running = True
        self._last_text = None
        self._waiting_logged = False
        self._set_header("proc", "Iniciando rutina…", f"{self._total_tabs()} pestañas configuradas")
        self.log(f"Rutina de inventario iniciada ({self._total_tabs()} pestañas).", "ok")
        if getattr(self, "_assets_ok", 3) < 3:
            self.log("Faltan imágenes de referencia: revisa 'Cambiar' en Configuración.", "warn")

        if self.vision_minimize_on_start.get():
            self.log("Minimizando aplicación…", "info")
            self.app_ref.iconify()

    # ==================================================================
    # LÓGICA DE ESTADO (solo UI)
    # ==================================================================
    def _total_tabs(self):
        try:
            return max(1, min(MAX_TABS, int(self.vision_num_tabs.get())))
        except ValueError:
            return MAX_TABS

    def _set_header(self, kind, title="", sub=""):
        """Ya no hay tarjeta de estado: solo se sincroniza el botón.

        El detalle de cada paso sigue en el Registro y en la barra de estado inferior.
        """
        self._update_run_button()

    def _hk(self):
        try:
            return self.app_ref._get_key_name(self.app_ref.key_vision)
        except Exception:
            return "F8"

    def _update_run_button(self):
        if self._running:
            self.btn_run.configure(text=f"■  Detener ({self._hk()})",
                                   fg_color=COLORS["error"], hover_color=COLORS["error_hover"])
        else:
            self.btn_run.configure(text=f"▶  Iniciar ({self._hk()})",
                                   fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])

    def refresh_hotkey_label(self):
        """main.py lo llama cuando el usuario remapea el atajo del inventario."""
        self._update_run_button()

    def _set_idle(self, reason="Rutina detenida"):
        was_running = self._running
        self._running = False
        self._last_text = None
        self._waiting_logged = False
        self._set_header("ok", "Sistema Listo", "Rutina de inventario detenida")
        if was_running:
            self.log(reason, "warn")

    @staticmethod
    def _nice(text):
        """'ALMACÉN CERRADO. ABRIENDO...' -> 'Almacén cerrado. Abriendo...'"""
        t = text.lower()
        t = t[:1].upper() + t[1:]
        return re.sub(r"(\. )(\w)", lambda m: m.group(1) + m.group(2).upper(), t)

    def _on_status(self, text, color):
        """Listener del estado global: traduce los mensajes de vision.py a UI + logs."""
        text = str(text)
        color = str(color).upper()
        active = getattr(self.app_ref, "active_mode", None) == "vision"

        if not active:
            # El motor cambió/se detuvo: si estábamos corriendo, volvemos a 'listo'.
            if self._running:
                self._set_idle("Rutina detenida")
            return

        if text == self._last_text:
            return
        self._last_text = text
        upper = text.upper()

        # Cuenta regresiva del bucle: se muestra en el header pero se loguea una sola vez
        if upper.startswith("PRÓXIMO TRASLADO EN"):
            countdown = text.split(":", 1)[1].strip() if ":" in text else ""
            self._set_header("ok", "En espera", f"Próximo traslado en {countdown}")
            self._last_text = None  # permite que el contador siga refrescando
            if not self._waiting_logged:
                self._waiting_logged = True
                self.log(f"Ciclo completado. Próximo traslado en {countdown}.", "ok")
            return
        self._waiting_logged = False

        level = _LEVEL_BY_COLOR.get(color, "info")
        nice = self._nice(text)

        m = re.search(r"PESTAÑA\s+(\d+)", upper)
        if m:
            n = int(m.group(1))
            total = self._total_tabs()
            self._set_header("proc", f"Procesando Pestaña {n}", f"Pestaña {n} de {total} · {nice}")
            self.log(nice, "proc")
            return

        if level == "err":
            self._set_header("err", "Error en la rutina", nice)
        elif level == "warn":
            self._set_header("warn", "Atención", nice)
        elif upper.startswith("TRASLADO COMPLETO"):
            self._set_header("ok", "Traslado completo", nice)
        else:
            self._set_header("proc", "Procesando…", nice)
        self.log(nice, level)

    # ==================================================================
    # UTILIDADES
    # ==================================================================
    @staticmethod
    def _find_game_hwnd():
        """Busca la ventana del juego, incluso si está minimizada."""
        import win32gui
        found = []

        def cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                if TARGET_GAME_IDENTIFIER.lower() in win32gui.GetWindowText(hwnd).lower():
                    found.append(hwnd)

        win32gui.EnumWindows(cb, None)
        return found[0] if found else None

    def focus_game_window(self):
        """Trae la ventana del juego al primer plano y verifica que realmente lo logró.

        Seguro para llamarse desde el hilo del worker (los logs se delegan al hilo de Tk).
        Devuelve True si el juego quedó en primer plano.
        """
        def say(msg, level="info"):
            try:
                self.after(0, lambda: self.log(msg, level))
            except Exception:
                pass

        try:
            import win32api
            import win32con
            import win32gui
            import win32process
        except ImportError:
            say("pywin32 no disponible: no se puede enfocar el juego.", "warn")
            return False

        try:
            hwnd = self._find_game_hwnd()
            if not hwnd:
                say("No se encontró la ventana del juego para enfocarla.", "warn")
                return False

            if win32gui.GetForegroundWindow() == hwnd and not win32gui.IsIconic(hwnd):
                return True

            # 1) Restaurar si está minimizada
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

            # 2) Pulsar/soltar ALT: desbloquea la restricción de Windows para cambiar el foco
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)

            # 3) Acoplar la entrada con la ventana que tiene el foco ahora mismo
            attached = False
            cur_tid = win32api.GetCurrentThreadId()
            fg = win32gui.GetForegroundWindow()
            fg_tid = win32process.GetWindowThreadProcessId(fg)[0] if fg else 0
            if fg_tid and fg_tid != cur_tid:
                try:
                    win32process.AttachThreadInput(cur_tid, fg_tid, True)
                    attached = True
                except Exception:
                    pass
            try:
                win32gui.BringWindowToTop(hwnd)
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            finally:
                if attached:
                    try:
                        win32process.AttachThreadInput(cur_tid, fg_tid, False)
                    except Exception:
                        pass

            # 4) Respaldo: forzar al frente del orden Z (topmost y volver a normal)
            flags = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, flags)
            win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, flags)

            time.sleep(0.4)  # deja que el juego se redibuje antes de buscar imágenes

            if win32gui.GetForegroundWindow() == hwnd:
                say("Ventana del juego en primer plano.", "ok")
                return True
            say("Windows no permitió traer el juego al frente. Haz clic en él una vez e inténtalo de nuevo.", "warn")
            return False
        except Exception as exc:
            say(f"No se pudo enfocar el juego ({exc.__class__.__name__}: {exc}).", "warn")
            return False

    def _select_image_file(self, target_var):
        file_path = filedialog.askopenfilename(
            filetypes=[("Imágenes PNG", "*.png"), ("Todas las imágenes", "*.png;*.jpg;*.jpeg"), ("Todos", "*.*")],
            title="Seleccionar Recorte"
        )
        if file_path:
            target_var.set(file_path)
            self.log(f"Imagen seleccionada: {file_path}", "info")
