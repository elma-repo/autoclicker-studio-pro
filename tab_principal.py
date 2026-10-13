import tkinter as tk

import customtkinter as ctk

from ui_components import (
    COLORS, FONT, Card, LabeledField,
    styled_entry, styled_option_menu, primary_button, ghost_button,
)

def _radio(parent, text, variable, value, **kwargs):
    return ctk.CTkRadioButton(
        parent, text=text, variable=variable, value=value,
        fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
        border_color=COLORS["border"], text_color=COLORS["text"],
        font=(FONT, 11), radiobutton_width=18, radiobutton_height=18, **kwargs,
    )


class TabPrincipal(ctk.CTkFrame):
    """Clicker básico: estado + botón de inicio, intervalo, tipo de clic, repetición y posición.

    Mantiene los nombres que usan main.py, clicker.py y los perfiles:
    entry_h/m/s/ms, combo_btn, combo_type, repeat_mode, entry_repeats,
    pos_mode, entry_x, entry_y, btn_capture, lbl_realtime_pos, get_interval().
    """

    def __init__(self, master, app_ref):
        super().__init__(master, fg_color="transparent")
        self.app_ref = app_ref

        # ---- Variables ----
        self.var_h = tk.StringVar(value="0")
        self.var_m = tk.StringVar(value="0")
        self.var_s = tk.StringVar(value="0")
        self.var_ms = tk.StringVar(value="100")

        self.var_btn = tk.StringVar(value="Izquierdo")
        self.var_type = tk.StringVar(value="Simple")

        self.repeat_mode = tk.StringVar(value="infinite")
        self.var_repeats = tk.StringVar(value="100")

        self.pos_mode = tk.StringVar(value="current")
        self.var_x = tk.StringVar(value="")
        self.var_y = tk.StringVar(value="")

        # ---- Estado interno de la UI ----
        self._running = False

        self._build_ui()

        for var in (self.var_h, self.var_m, self.var_s, self.var_ms):
            var.trace_add("write", lambda *_: self._refresh_summary())
        self._refresh_summary()

        # Escucha los cambios de estado que publica el worker (clicker.py no se toca)
        lbl = getattr(app_ref, "lbl_status", None)
        if lbl is not None and hasattr(lbl, "add_listener"):
            lbl.add_listener(self._on_status)

    # ==================================================================
    # INTERFAZ
    # ==================================================================
    def _build_ui(self):
        self._build_run_bar()

        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", pady=(16, 0))
        row1.grid_columnconfigure(0, weight=1, uniform="cols")
        row1.grid_columnconfigure(1, weight=1, uniform="cols")
        self._build_interval_card(row1).grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._build_click_card(row1).grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x", pady=(16, 0))
        row2.grid_columnconfigure(0, weight=1, uniform="cols")
        row2.grid_columnconfigure(1, weight=1, uniform="cols")
        self._build_repeat_card(row2).grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._build_position_card(row2).grid(row=0, column=1, sticky="nsew", padx=(8, 0))

    # ---------------- Barra superior: solo el botón de inicio ----------------
    def _build_run_bar(self):
        self.btn_run = primary_button(
            self, "", height=40,
            command=lambda: self.app_ref.toggle_engine("principal"),
        )
        self.btn_run.pack(fill="x")
        self._update_run_button()

    # ---------------- Tarjeta: intervalo ----------------
    def _build_interval_card(self, parent):
        card = Card(parent, title="Intervalo entre clics")
        body = card.body

        grid = ctk.CTkFrame(body, fg_color="transparent")
        grid.pack(fill="x")

        fields = (
            ("Horas", self.var_h, "entry_h"),
            ("Min", self.var_m, "entry_m"),
            ("Seg", self.var_s, "entry_s"),
            ("ms", self.var_ms, "entry_ms"),
        )
        for col, (label, var, attr) in enumerate(fields):
            field = LabeledField(grid, label, var, width=56)
            field.grid(row=0, column=col, sticky="w", padx=(0, 10))
            setattr(self, attr, field.entry)   # main.py usa entry_h / entry_m / entry_s / entry_ms

        self.lbl_summary = ctk.CTkLabel(body, text="", anchor="w", font=(FONT, 10),
                                        text_color=COLORS["text_mute"])
        self.lbl_summary.pack(fill="x", pady=(14, 0))
        return card

    # ---------------- Tarjeta: opciones de clic ----------------
    def _build_click_card(self, parent):
        card = Card(parent, title="Opciones de clic")
        body = card.body

        grid = ctk.CTkFrame(body, fg_color="transparent")
        grid.pack(fill="x")

        f_btn = ctk.CTkFrame(grid, fg_color="transparent")
        f_btn.grid(row=0, column=0, sticky="w", padx=(0, 16))
        ctk.CTkLabel(f_btn, text="Botón", font=(FONT, 10), text_color=COLORS["text_dim"],
                     anchor="w").pack(fill="x")
        self.combo_btn = styled_option_menu(
            f_btn, values=["Izquierdo", "Derecho", "Central"],
            variable=self.var_btn, width=118,
            command=lambda _v: self._refresh_summary(),
        )
        self.combo_btn.pack(anchor="w", pady=(2, 0))

        f_type = ctk.CTkFrame(grid, fg_color="transparent")
        f_type.grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(f_type, text="Tipo", font=(FONT, 10), text_color=COLORS["text_dim"],
                     anchor="w").pack(fill="x")
        self.combo_type = styled_option_menu(
            f_type, values=["Simple", "Doble"],
            variable=self.var_type, width=100,
            command=lambda _v: self._refresh_summary(),
        )
        self.combo_type.pack(anchor="w", pady=(2, 0))

        ctk.CTkLabel(body, text="Doble envía dos clics seguidos en cada ciclo.", anchor="w",
                     font=(FONT, 10), text_color=COLORS["text_mute"]).pack(fill="x", pady=(14, 0))
        return card

    # ---------------- Tarjeta: repetición ----------------
    def _build_repeat_card(self, parent):
        card = Card(parent, title="Repetición")
        body = card.body

        self.rb_infinite = _radio(body, "", self.repeat_mode, "infinite")
        self.rb_infinite.pack(anchor="w")

        f_fixed = ctk.CTkFrame(body, fg_color="transparent")
        f_fixed.pack(anchor="w", pady=(12, 0))
        _radio(f_fixed, "Repetir", self.repeat_mode, "fixed").pack(side="left")
        self.entry_repeats = styled_entry(f_fixed, textvariable=self.var_repeats,
                                          width=70, height=26, justify="center")
        self.entry_repeats.pack(side="left", padx=(8, 8))
        ctk.CTkLabel(f_fixed, text="veces", font=(FONT, 10),
                     text_color=COLORS["text_mute"]).pack(side="left")

        self._refresh_infinite_text()
        return card

    # ---------------- Tarjeta: posición ----------------
    def _build_position_card(self, parent):
        card = Card(parent, title="Posición del cursor")
        body = card.body

        _radio(body, "Posición actual del cursor", self.pos_mode, "current").pack(anchor="w")

        f_fixed = ctk.CTkFrame(body, fg_color="transparent")
        f_fixed.pack(anchor="w", pady=(12, 0))
        _radio(f_fixed, "Fija", self.pos_mode, "fixed").pack(side="left")
        ctk.CTkLabel(f_fixed, text="X", font=(FONT, 10),
                     text_color=COLORS["text_mute"]).pack(side="left", padx=(8, 4))
        self.entry_x = styled_entry(f_fixed, textvariable=self.var_x, width=56, height=26,
                                    justify="center")
        self.entry_x.pack(side="left")
        ctk.CTkLabel(f_fixed, text="Y", font=(FONT, 10),
                     text_color=COLORS["text_mute"]).pack(side="left", padx=(8, 4))
        self.entry_y = styled_entry(f_fixed, textvariable=self.var_y, width=56, height=26,
                                    justify="center")
        self.entry_y.pack(side="left")

        # "Capturar" y la lectura en vivo van aparte para que quepan con la ventana al mínimo
        self.btn_capture = ghost_button(body, "Capturar", command=self.app_ref._prepare_capture_pos,
                                        width=76, height=26)
        self.btn_capture.pack(anchor="w", pady=(12, 0))

        self.lbl_realtime_pos = ctk.CTkLabel(
            body, text="Cursor en tiempo real: X: 0, Y: 0", anchor="w",
            font=(FONT, 10), text_color=COLORS["text_mute"])
        self.lbl_realtime_pos.pack(fill="x", pady=(10, 0))
        return card

    # ==================================================================
    # API PÚBLICA (la usan main.py y clicker.py)
    # ==================================================================
    def get_interval(self):
        """Intervalo total en segundos (acepta decimales y coma). Mínimo 1 ms."""
        try:
            h = self._num(self.entry_h.get())
            m = self._num(self.entry_m.get())
            s = self._num(self.entry_s.get())
            ms = self._num(self.entry_ms.get())
        except ValueError:
            return 0.1
        return max(0.001, (h * 3600) + (m * 60) + s + (ms / 1000.0))

    def on_engine_started(self):
        """main.toggle_engine('principal') lo llama justo antes de lanzar el worker."""
        self._running = True
        self._update_run_button()

    def refresh_hotkey_label(self):
        """main.py lo llama cuando el usuario remapea el atajo del clicker."""
        self._update_run_button()
        self._refresh_infinite_text()

    # ==================================================================
    # LÓGICA DE ESTADO (solo UI)
    # ==================================================================
    @staticmethod
    def _num(text):
        text = (text or "").strip().replace(",", ".")
        return float(text) if text else 0.0

    def _hk(self):
        try:
            return self.app_ref._get_key_name(self.app_ref.key_main)
        except Exception:
            return "F6"

    def _refresh_infinite_text(self):
        self.rb_infinite.configure(text=f"Infinito (hasta detener con {self._hk()})")

    def _update_run_button(self):
        if self._running:
            self.btn_run.configure(text=f"■  Detener ({self._hk()})",
                                   fg_color=COLORS["error"], hover_color=COLORS["error_hover"])
        else:
            self.btn_run.configure(text=f"▶  Iniciar ({self._hk()})",
                                   fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])

    @staticmethod
    def _fmt_interval(seconds):
        if seconds < 1:
            return f"{int(round(seconds * 1000))} ms"
        if seconds < 60:
            return f"{seconds:g} s" if abs(seconds - round(seconds)) < 0.05 else f"{seconds:.1f} s"
        total = int(round(seconds))
        h, rest = divmod(total, 3600)
        m, s = divmod(rest, 60)
        parts = []
        if h:
            parts.append(f"{h} h")
        if m:
            parts.append(f"{m} min")
        if s:
            parts.append(f"{s} s")
        return " ".join(parts)

    def _refresh_summary(self):
        if not hasattr(self, "lbl_summary"):
            return
        iv = self.get_interval()
        if iv < 1:
            text = f"≈ {1 / iv:.1f} clics por segundo"
        else:
            text = f"1 clic cada {self._fmt_interval(iv)}"
        self.lbl_summary.configure(text=text)

    def _set_idle(self):
        self._running = False
        self._update_run_button()

    def _on_status(self, text, color):
        """Listener del estado global (se ejecuta en el hilo de Tk).

        Solo sincroniza el botón: el texto de estado ya lo muestra la barra inferior.
        """
        active = getattr(self.app_ref, "active_mode", None) == "principal"
        if active:
            if not self._running:
                self._running = True
                self._update_run_button()
        elif self._running:
            self._set_idle()
