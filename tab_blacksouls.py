import os
import re
import sys
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

from config import ruta_recurso
from black_souls import RUTA_DEFECTO, PRESS_MS_DEFECTO, WAIT_MS_DEFECTO
from ui_components import (
    COLORS, FONT, Card, StatusDot, NativeScrollFrame,
    styled_entry, primary_button, ghost_button,
)

THUMB_W, THUMB_H = 230, 130   # caja de la miniatura de posición inicial
SLOT_W = 118                  # ancho de cada campo de la lista de calibración
ARROWS = {"up": "↑", "down": "↓", "left": "←", "right": "→"}
DEFAULTS = {"press": str(PRESS_MS_DEFECTO), "wait": str(WAIT_MS_DEFECTO), "delay": "100", "seg": "5.0"}


class TabBlackSouls(ctk.CTkFrame):
    """Pestaña limpia: botón de inicio arriba y el resto debajo.

    La calibración de los pasos de la ruta sigue existiendo (main.py usa `bs_pasos_vars`
    y `img_bs_combate` para lanzar el worker y guardar perfiles). Se abre con
    «Calibrar» como una vista a todo el alto de la pestaña, con lista desplazable.
    """

    def __init__(self, master, app_ref):
        super().__init__(master, fg_color="transparent")
        self.app_ref = app_ref

        # ---- Variables (mismos nombres que antes: las usan main.py y los perfiles) ----
        self.img_bs_combate = tk.StringVar(value=ruta_recurso("assets/bs_menu_combate.png"))
        self.img_bs_inicio = tk.StringVar(value=ruta_recurso("assets/bs_initial_position.png"))

        # La lista sale de black_souls.RUTA_DEFECTO: es la ruta que ejecuta el worker,
        # y los tiempos que se editen aquí son los que el worker usa de verdad.
        self.bs_pasos_vars = []
        for n, (tipo, desc, direccion, valor) in enumerate(RUTA_DEFECTO, 1):
            if tipo == "mov":
                self.bs_pasos_vars.append({
                    "desc": f"{n}. {desc}", "tipo": "mov", "dir": direccion, "veces": valor,
                    "press": tk.StringVar(value=DEFAULTS["press"]),
                    "wait": tk.StringVar(value=DEFAULTS["wait"]),
                })
            else:
                # espera = segundos máximos esperando a que empiece un combate
                self.bs_pasos_vars.append({
                    "desc": f"{n}. {desc}", "tipo": "espera",
                    "seg": tk.StringVar(value=f"{valor:g}"), "seg_def": f"{valor:g}",
                })

        # ---- Estado interno de la UI ----
        self._running = False
        self._adv_open = False
        self._assets_ok = False
        self._start_pil = None      # imagen original de posición inicial
        self._thumb_img = None      # referencias para que Tk no las borre
        self._preview_win = None
        self._blank_img = ctk.CTkImage(Image.new("RGBA", (1, 1), (0, 0, 0, 0)), size=(1, 1))

        self._build_ui()

        self.img_bs_combate.trace_add("write", lambda *_: self._refresh_assets())
        self._refresh_assets()

        self.img_bs_inicio.trace_add("write", lambda *_: self._refresh_start_preview())
        self._refresh_start_preview()

        # Escucha los cambios de estado que publica el worker (black_souls.py no se toca)
        lbl = getattr(app_ref, "lbl_status", None)
        if lbl is not None and hasattr(lbl, "add_listener"):
            lbl.add_listener(self._on_status)

    # ==================================================================
    # INTERFAZ
    # ==================================================================
    def _build_ui(self):
        self._build_run_bar()

        # Cuerpo normal y vista de calibración: solo uno visible a la vez
        self.body_view = ctk.CTkFrame(self, fg_color="transparent")
        self.body_view.pack(fill="both", expand=True, pady=(16, 0))
        self.calib_view = ctk.CTkFrame(self, fg_color="transparent")

        self._build_start_card()
        self._build_config_card()
        self._build_calibration_view()

    # ---------------- Barra superior: solo el botón de inicio ----------------
    def _build_run_bar(self):
        self.btn_run = primary_button(
            self, "", height=40,
            command=lambda: self.app_ref.toggle_engine("blacksouls"),
        )
        self.btn_run.pack(fill="x")
        self._update_run_button()

    # ---------------- Tarjeta: posición inicial ----------------
    def _build_start_card(self):
        card = Card(self.body_view, title="Posición inicial")
        card.pack(fill="x")
        row = ctk.CTkFrame(card.body, fg_color="transparent")
        row.pack(fill="x")

        # Miniatura (clic para ampliar)
        self.thumb_box = ctk.CTkFrame(row, width=THUMB_W, height=THUMB_H,
                                      fg_color=COLORS["card_alt"], corner_radius=8)
        self.thumb_box.pack(side="left")
        self.thumb_box.pack_propagate(False)
        self.lbl_thumb = ctk.CTkLabel(self.thumb_box, text="", font=(FONT, 10),
                                      text_color=COLORS["text_mute"], image=self._blank_img)
        self.lbl_thumb.pack(expand=True)
        self.lbl_thumb.bind("<Button-1>", lambda _e: self._open_preview())

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=(18, 0))
        ctk.CTkLabel(info, text="Colócate así antes de iniciar", anchor="w",
                     font=(FONT, 12, "bold"), text_color=COLORS["text"]).pack(fill="x")
        ctk.CTkLabel(info, text="Deja al jugador exactamente en esta posición para que la ruta "
                                "de conejos de Black Souls 1 funcione.",
                     anchor="w", justify="left", wraplength=300, font=(FONT, 10),
                     text_color=COLORS["text_mute"]).pack(fill="x", pady=(2, 10))

        f_state = ctk.CTkFrame(info, fg_color="transparent")
        f_state.pack(fill="x")
        self.start_dot = StatusDot(f_state, size=8, color=COLORS["text_mute"])
        self.start_dot.pack(side="left", padx=(0, 8))
        self.lbl_start = ctk.CTkLabel(f_state, text="", anchor="w", font=(FONT, 11),
                                      text_color=COLORS["text"])
        self.lbl_start.pack(side="left")

        f_btn = ctk.CTkFrame(info, fg_color="transparent")
        f_btn.pack(fill="x", pady=(10, 0))
        ghost_button(f_btn, "Ampliar", command=self._open_preview,
                     width=72, height=24).pack(side="left", padx=(0, 8))
        ghost_button(f_btn, "Cambiar", command=lambda: self._select_image_file(self.img_bs_inicio),
                     width=72, height=24).pack(side="left")

    # ---------------- Tarjeta: configuración compacta ----------------
    def _build_config_card(self):
        card = Card(self.body_view, title="Configuración")
        card.pack(fill="x", pady=(16, 0))
        body = card.body

        # Fila 1: imagen de detección de combate
        f_img = ctk.CTkFrame(body, fg_color="transparent")
        f_img.pack(fill="x", pady=(0, 12))
        self.assets_dot = StatusDot(f_img, size=8, color=COLORS["text_mute"])
        self.assets_dot.pack(side="left", padx=(0, 8))
        self.lbl_assets = ctk.CTkLabel(f_img, text="", anchor="w", font=(FONT, 11),
                                       text_color=COLORS["text"])
        self.lbl_assets.pack(side="left")
        ghost_button(f_img, "Cambiar", command=lambda: self._select_image_file(self.img_bs_combate),
                     width=64, height=24).pack(side="right")

        # Fila 2: resumen de la ruta + botón que abre la calibración
        f_route = ctk.CTkFrame(body, fg_color="transparent")
        f_route.pack(fill="x")
        ctk.CTkLabel(f_route, text=f"Ruta de farmeo · {len(self.bs_pasos_vars)} pasos",
                     anchor="w", font=(FONT, 11), text_color=COLORS["text"]).pack(side="left")
        self.btn_adv = ghost_button(f_route, "Calibrar", command=self._open_calibration,
                                    width=84, height=24)
        self.btn_adv.pack(side="right")

    # ---------------- Vista de calibración (ocupa todo el alto de la pestaña) ----------------
    def _build_calibration_view(self):
        view = self.calib_view

        bar = ctk.CTkFrame(view, fg_color="transparent")
        bar.pack(fill="x")
        ghost_button(bar, "←  Volver", command=self._close_calibration,
                     width=88, height=30).pack(side="left")
        titles = ctk.CTkFrame(bar, fg_color="transparent")
        titles.pack(side="left", padx=(14, 0))
        ctk.CTkLabel(titles, text="Calibración de pasos", anchor="w",
                     font=(FONT, 14, "bold"), text_color=COLORS["text"]).pack(anchor="w")
        ctk.CTkLabel(titles, text=f"{len(self.bs_pasos_vars)} pasos · desplázate con la rueda del ratón",
                     anchor="w", font=(FONT, 10), text_color=COLORS["text_mute"]).pack(anchor="w")
        ghost_button(bar, "Restablecer", command=self._reset_calibration,
                     width=92, height=30).pack(side="right")

        card = Card(view)
        card.pack(fill="both", expand=True, pady=(12, 0))
        self.bs_scroll = NativeScrollFrame(card.body, bg=COLORS["card"])
        self.bs_scroll.pack(fill="both", expand=True)

        for index, paso in enumerate(self.bs_pasos_vars, 1):
            self._build_step_row(self.bs_scroll.interior, index, paso)

    def _build_step_row(self, parent, index, paso):
        row = ctk.CTkFrame(parent, fg_color=COLORS["card_alt"], corner_radius=8, height=42)
        row.pack(fill="x", pady=3, padx=(0, 6))
        row.pack_propagate(False)

        # De derecha a izquierda: campos (columnas alineadas), acción, y luego número + texto
        fields = ctk.CTkFrame(row, fg_color="transparent")
        fields.pack(side="right", padx=(0, 10))

        def slot(label=None, var=None, unit=""):
            box = ctk.CTkFrame(fields, fg_color="transparent", width=SLOT_W, height=30)
            box.pack(side="left")
            box.pack_propagate(False)
            if var is None:
                return
            ctk.CTkLabel(box, text=label, width=38, anchor="w", font=(FONT, 10),
                         text_color=COLORS["text_mute"]).pack(side="left")
            styled_entry(box, textvariable=var, width=48, height=26, justify="center").pack(side="left")
            ctk.CTkLabel(box, text=unit, font=(FONT, 10),
                         text_color=COLORS["text_mute"]).pack(side="left", padx=(4, 0))

        if paso["tipo"] == "mov":
            chip = f"{ARROWS.get(paso['dir'], '?')}  ×{paso['veces']}"
            slot("Pulso", paso["press"], "ms")
            slot("Pausa", paso["wait"], "ms")
        elif paso["tipo"] == "interact":
            chip = f"Z  ×{paso['veces']}"
            slot("Delay", paso["delay"], "ms")
            slot()
        else:
            chip = "⏱"
            slot("Espera", paso["seg"], "s")
            slot()

        ctk.CTkLabel(row, text=chip, width=58, height=26, corner_radius=6,
                     fg_color=COLORS["card"], text_color=COLORS["accent_text"],
                     font=(FONT, 11, "bold")).pack(side="right", padx=(0, 10))

        ctk.CTkLabel(row, text=str(index), width=26, height=26, corner_radius=6,
                     fg_color=COLORS["card"], text_color=COLORS["text_dim"],
                     font=(FONT, 10, "bold")).pack(side="left", padx=10)
        ctk.CTkLabel(row, text=re.sub(r"^\d+\.\s*", "", paso["desc"]), anchor="w",
                     font=(FONT, 11), text_color=COLORS["text"]).pack(side="left", fill="x", expand=True)

    def _reset_calibration(self):
        for paso in self.bs_pasos_vars:
            if paso["tipo"] == "mov":
                paso["press"].set(DEFAULTS["press"])
                paso["wait"].set(DEFAULTS["wait"])
            elif paso["tipo"] == "interact":
                paso["delay"].set(DEFAULTS["delay"])
            elif paso["tipo"] == "espera":
                paso["seg"].set(paso.get("seg_def", DEFAULTS["seg"]))

    def _open_calibration(self):
        self._adv_open = True
        self.body_view.pack_forget()
        self.calib_view.pack(fill="both", expand=True, pady=(16, 0))
        self.after(60, self._refresh_scroll)

    def _close_calibration(self):
        self._adv_open = False
        self.calib_view.pack_forget()
        self.body_view.pack(fill="both", expand=True, pady=(16, 0))

    def _refresh_scroll(self):
        try:
            self.bs_scroll._on_configure()
        except Exception:
            pass

    # ==================================================================
    # API PÚBLICA (la usa main.py)
    # ==================================================================
    def on_show(self):
        """main._switch_tab lo llama al mostrar esta pestaña."""
        if self._adv_open:
            self.after(30, self._refresh_scroll)

    def on_engine_started(self):
        """main.toggle_engine('blacksouls') lo llama justo antes de lanzar el worker."""
        self._running = True
        self._update_run_button()
        if not self._assets_ok:
            # Sin esta imagen el worker no detecta los combates: se avisa en la barra de estado
            self.app_ref.lbl_status.configure(
                text="ATENCIÓN: NO SE ENCUENTRA LA IMAGEN DE COMBATE", text_color="#EAB308")

    def refresh_hotkey_label(self):
        """main.py lo llama cuando el usuario remapea el atajo de Black Souls."""
        self._update_run_button()

    # ==================================================================
    # LÓGICA DE ESTADO (solo UI)
    # ==================================================================
    def _hk(self):
        try:
            return self.app_ref._get_key_name(self.app_ref.key_bs)
        except Exception:
            return "F9"

    def _update_run_button(self):
        if self._running:
            self.btn_run.configure(text=f"■  Detener ({self._hk()})",
                                   fg_color=COLORS["error"], hover_color=COLORS["error_hover"])
        else:
            self.btn_run.configure(text=f"▶  Iniciar ({self._hk()})",
                                   fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])

    def _set_idle(self):
        self._running = False
        self._update_run_button()

    def _on_status(self, text, color):
        """Listener del estado global. Solo sincroniza el botón (el texto lo muestra la barra inferior)."""
        try:
            self.after(0, self._sync_running)
        except Exception:
            pass

    def _sync_running(self):
        active = getattr(self.app_ref, "active_mode", None) == "blacksouls"
        if active and not self._running:
            self._running = True
            self._update_run_button()
        elif not active and self._running:
            self._set_idle()

    # ==================================================================
    # POSICIÓN INICIAL (imagen de referencia)
    # ==================================================================
    @staticmethod
    def _fit(size, max_w, max_h, max_scale=1.0):
        w, h = size
        scale = min(max_w / w, max_h / h, max_scale)
        return max(1, int(w * scale)), max(1, int(h * scale))

    def _refresh_start_preview(self):
        path = self.img_bs_inicio.get()
        self._start_pil = None
        if os.path.isfile(path):
            try:
                img = Image.open(path).convert("RGBA")
                self._start_pil = img
                size = self._fit(img.size, THUMB_W - 8, THUMB_H - 8, max_scale=2.0)
                self._thumb_img = ctk.CTkImage(light_image=img, dark_image=img, size=size)
                self.lbl_thumb.configure(image=self._thumb_img, text="")
                self.start_dot.set_color(COLORS["success"])
                self.lbl_start.configure(text="Imagen de referencia cargada")
                return
            except Exception:
                pass
        self.lbl_thumb.configure(image=self._blank_img, text="Sin imagen")
        self.start_dot.set_color(COLORS["warning"])
        self.lbl_start.configure(text="bs_initial_position.png no encontrada")

    def _open_preview(self):
        """Ventana con la imagen ampliada."""
        if self._start_pil is None:
            return
        if self._preview_win is not None and self._preview_win.winfo_exists():
            self._preview_win.focus()
            return

        win = ctk.CTkToplevel(self)
        win.title("Posición inicial · Black Souls 1")
        win.configure(fg_color=COLORS["bg"])
        win.resizable(False, False)
        win.transient(self.winfo_toplevel())

        max_w = min(900, win.winfo_screenwidth() - 200)
        max_h = min(600, win.winfo_screenheight() - 250)
        size = self._fit(self._start_pil.size, max_w, max_h, max_scale=2.0)
        win._big_img = ctk.CTkImage(light_image=self._start_pil, dark_image=self._start_pil, size=size)
        ctk.CTkLabel(win, text="", image=win._big_img).pack(padx=20, pady=20)
        win.geometry(f"{size[0] + 40}x{size[1] + 40}")

        # CTkToplevel pone su icono por defecto tras ~200 ms: se sobrescribe después
        if sys.platform.startswith("win"):
            ico = ruta_recurso(os.path.join("assets", "app", "app_icon.ico"))
            if os.path.exists(ico):
                win.after(300, lambda: win.winfo_exists() and win.iconbitmap(ico))

        self._preview_win = win
        win.after(200, lambda: win.winfo_exists() and (win.lift(), win.focus_force()))

    # ==================================================================
    # ASSETS
    # ==================================================================
    def _refresh_assets(self):
        ok = os.path.exists(self.img_bs_combate.get())
        self._assets_ok = ok
        if ok:
            self.assets_dot.set_color(COLORS["success"])
            self.lbl_assets.configure(text="Imagen de combate cargada")
        else:
            self.assets_dot.set_color(COLORS["error"])
            self.lbl_assets.configure(text="Imagen de combate no encontrada")

    def _select_image_file(self, target_var):
        file_path = filedialog.askopenfilename(
            filetypes=[("Imágenes PNG", "*.png"), ("Todas las imágenes", "*.png;*.jpg;*.jpeg"), ("Todos", "*.*")],
            title="Seleccionar Recorte",
        )
        if file_path:
            target_var.set(file_path)
