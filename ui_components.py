import os
import threading
import time
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

# ======================================================================
# PALETA "DARK OLED / GAMER DASHBOARD"
# ======================================================================
COLORS = {
    # Superficies
    "bg": "#0F0F12",            # fondo general de la ventana
    "sidebar": "#0B0B0E",       # barra lateral
    "card": "#18181B",          # tarjetas / contenedores
    "card_alt": "#1E1E24",      # tarjetas secundarias / hover
    "console": "#101014",       # consola de logs
    "input": "#101014",         # campos de texto
    "border": "#27272A",
    "border_soft": "#1F1F26",

    # Acento violeta neón
    "accent": "#7C3AED",
    "accent_hover": "#6D28D9",
    "accent_light": "#8B5CF6",
    "accent_text": "#C4B5FD",

    # Estados
    "success": "#22C55E",       # listo / éxito
    "process": "#A855F7",       # proceso activo
    "error": "#EF4444",         # error / detención
    "error_hover": "#DC2626",
    "warning": "#EAB308",

    # Texto
    "text": "#F4F4F5",
    "text_dim": "#A1A1AA",
    "text_mute": "#71717A",
}

FONT = "Segoe UI"


# ======================================================================
# ESTILOS ttk (Combobox y barras de scroll que aún usan otras pestañas)
# ======================================================================
def apply_dark_ttk_styles():
    """Estiliza los widgets ttk que todavía usan las otras pestañas."""
    style = ttk.Style()
    try:
        style.theme_use("default")
    except tk.TclError:
        pass

    c = COLORS
    style.configure(
        "TCombobox",
        fieldbackground=c["card_alt"], background=c["border"], foreground=c["text"],
        bordercolor=c["border"], arrowcolor=c["text_dim"],
        lightcolor=c["border"], darkcolor=c["border"],
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", c["card_alt"])],
        foreground=[("readonly", c["text"])],
        background=[("active", c["accent"])],
    )
    style.configure(
        "Dark.Vertical.TScrollbar",
        background="#2A2A31", troughcolor=c["console"], bordercolor=c["console"],
        arrowcolor=c["text_dim"], lightcolor="#2A2A31", darkcolor="#2A2A31",
        relief="flat", gripcount=0,
    )
    style.map("Dark.Vertical.TScrollbar", background=[("active", c["accent"])])

    # Lista desplegable del Combobox
    try:
        root = style.master
        root.option_add("*TCombobox*Listbox.background", c["card_alt"])
        root.option_add("*TCombobox*Listbox.foreground", c["text"])
        root.option_add("*TCombobox*Listbox.selectBackground", c["accent"])
        root.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")
    except Exception:
        pass


# ======================================================================
# COMPONENTES CLÁSICOS (misma API que antes: no rompen tab_secuencias / tab_blacksouls)
# ======================================================================
class NativeScrollFrame(tk.Frame):
    def __init__(self, parent, bg="#121214"):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, yscrollincrement=20)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview,
                                       style="Dark.Vertical.TScrollbar")
        self.interior = tk.Frame(self.canvas, bg=bg)

        self.interior_id = self.canvas.create_window((0, 0), window=self.interior, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.interior.bind('<Configure>', self._on_configure)
        self.canvas.bind('<Configure>', self._on_canvas_resize)
        # add="+": no pisa el binding de otras listas (antes solo funcionaba la última creada)
        self.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

    def _on_configure(self, event=None):
        self.interior.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_resize(self, event):
        self.canvas.itemconfig(self.interior_id, width=event.width)

    def _pointer_inside(self, event):
        """True si el cursor está sobre esta lista (o sobre cualquiera de sus hijos)."""
        try:
            w = self.winfo_containing(event.x_root, event.y_root)
        except Exception:
            return False
        while w is not None:
            if w is self:
                return True
            w = getattr(w, "master", None)
        return False

    def _on_mousewheel(self, event):
        try:
            if not (self.winfo_exists() and self.canvas.winfo_exists() and self.winfo_ismapped()):
                return
            if not self._pointer_inside(event):
                return
            first, last = self.canvas.yview()
            if first <= 0.0 and last >= 1.0:
                return      # todo el contenido cabe: no hay nada que desplazar
            steps = int(-1 * (event.delta / 120)) or (-1 if event.delta > 0 else 1)
            self.canvas.yview_scroll(steps * 2, "units")
        except Exception:
            pass


_BTN_SHORT = {"Izquierdo": "Izq", "Derecho": "Der", "Central": "Central", "Doble": "Doble"}


def describe_step(step):
    """Texto corto que muestra cada StepCard según el tipo de paso."""
    t = step.get("type")
    btn = _BTN_SHORT.get(step.get("action", ""), step.get("action", ""))
    pos = f"({step.get('x', 0)},{step.get('y', 0)})"
    key = str(step.get("key_display", "K")).upper()

    if t == "mouse":
        hold = f" · {int(step['hold_ms'])} ms" if step.get("hold_ms") else ""
        return f"🖱️ {btn} {pos}{hold}"
    if t == "mouse_drag":
        return f"🖱️ Arrastrar {btn} {pos} → ({step.get('x2', 0)},{step.get('y2', 0)})"
    if t == "mouse_scroll":
        dy, dx = step.get("dy", 0), step.get("dx", 0)
        if dy:
            arrow, amount = ("↑" if dy > 0 else "↓"), abs(dy)
        else:
            arrow, amount = ("→" if dx > 0 else "←"), abs(dx)
        return f"🖱️ Scroll {arrow} ×{amount} {pos}"
    if t == "mouse_down":
        return f"🖱️ ▼ Mantener {btn} {pos}"
    if t == "mouse_up":
        return f"🖱️ ▲ Soltar {btn} {pos}"
    if t == "keyboard":
        hold = f" · {int(step['hold_ms'])} ms" if step.get("hold_ms") else ""
        return f"⌨️ [{key}]{hold}"
    if t == "key_down":
        return f"⌨️ ▼ Mantener [{key}]"
    if t == "key_up":
        return f"⌨️ ▲ Soltar [{key}]"
    return f"❔ {t}"


class StepCard(tk.Frame):
    def __init__(self, master, step_data, on_delete, on_move, on_duplicate):
        super().__init__(master, bg=COLORS["card"], highlightbackground=COLORS["border"], highlightthickness=1, height=32)
        self.step_data = dict(step_data)
        self.on_delete = on_delete
        self.on_move = on_move
        self.on_duplicate = on_duplicate

        self.pack_propagate(False)
        self.grid_propagate(False)
        self.grid_columnconfigure(1, weight=1)

        self.lbl_index = tk.Label(self, text="#1", width=3, font=(FONT, 8, "bold"), fg=COLORS["text_mute"], bg=COLORS["card"], anchor="w")
        self.lbl_index.grid(row=0, column=0, padx=(6, 1), pady=3, sticky="w")

        desc = describe_step(self.step_data)

        self.lbl_desc = tk.Label(self, text=desc, font=(FONT, 9, "bold"), fg=COLORS["text"], bg=COLORS["card"], anchor="w")
        self.lbl_desc.grid(row=0, column=1, padx=2, pady=3, sticky="ew")

        self.entry_val = tk.Entry(
            self, width=5, bg=COLORS["card_alt"], fg="#FFFFFF", insertbackground="white",
            relief="flat", font=(FONT, 9), justify="center",
            highlightthickness=1, highlightbackground="#3F3F46", highlightcolor=COLORS["accent"]
        )
        self.entry_val.insert(0, str(self.step_data.get('time_val', 500)))
        self.entry_val.grid(row=0, column=2, padx=2, pady=3)

        self.unit_var = tk.StringVar(value=self.step_data.get('time_unit', 'ms'))
        self.unit_combo = ttk.Combobox(
            self, textvariable=self.unit_var, values=["ms", "s", "m"],
            width=3, state="readonly", font=(FONT, 8)
        )
        self.unit_combo.grid(row=0, column=3, padx=1, pady=3)

        self.btn_up = tk.Button(self, text="▲", width=1, font=(FONT, 7), bg=COLORS["card_alt"], fg=COLORS["text_dim"], relief="flat", command=lambda: self.on_move(self, "up"))
        self.btn_up.grid(row=0, column=4, padx=1, pady=3)

        self.btn_down = tk.Button(self, text="▼", width=1, font=(FONT, 7), bg=COLORS["card_alt"], fg=COLORS["text_dim"], relief="flat", command=lambda: self.on_move(self, "down"))
        self.btn_down.grid(row=0, column=5, padx=1, pady=3)

        self.btn_dup = tk.Button(self, text="📋", width=1, font=(FONT, 8), bg=COLORS["accent"], fg="#FFFFFF", relief="flat", command=lambda: self.on_duplicate(self))
        self.btn_dup.grid(row=0, column=6, padx=1, pady=3)

        self.btn_del = tk.Button(self, text="✕", width=1, font=(FONT, 8, "bold"), bg=COLORS["error_hover"], fg="#FFFFFF", relief="flat", command=lambda: self.on_delete(self))
        self.btn_del.grid(row=0, column=7, padx=(1, 5), pady=3)

    def get_current_data(self):
        try:
            val = float(self.entry_val.get().replace(",", "."))
        except ValueError:
            val = 500.0
            self.entry_val.delete(0, "end")
            self.entry_val.insert(0, "500")

        self.step_data['time_val'] = max(0.0, val)
        self.step_data['time_unit'] = self.unit_var.get()
        return dict(self.step_data)

    def set_active(self, active: bool):
        if self.winfo_exists():
            border = COLORS["success"] if active else COLORS["border"]
            self.configure(highlightbackground=border, highlightthickness=2 if active else 1)


# ======================================================================
# COMPONENTES NUEVOS (reutilizables por cualquier tab_*.py)
# ======================================================================
class Card(ctk.CTkFrame):
    """Tarjeta de bordes redondeados (corner_radius=12) con título opcional.

    Los widgets hijos se agregan dentro de `card.body`.
    """

    def __init__(self, master, title=None, accent=None, fg_color=None, **kwargs):
        super().__init__(
            master,
            fg_color=fg_color or COLORS["card"],
            corner_radius=12,
            border_width=1,
            border_color=COLORS["border_soft"],
            **kwargs,
        )
        if title:
            ctk.CTkLabel(
                self, text=title, font=(FONT, 12, "bold"),
                text_color=accent or COLORS["accent_text"], anchor="w",
            ).pack(fill="x", padx=16, pady=(12, 6))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=16, pady=(0 if title else 14, 14))


class StatusDot(ctk.CTkFrame):
    """Punto de estado circular, con pulso opcional para 'proceso activo'."""

    def __init__(self, master, size=14, color=None):
        self._dot_color = color or COLORS["success"]
        super().__init__(master, width=size, height=size, corner_radius=size // 2,
                         fg_color=self._dot_color, border_width=0)
        self._pulse_job = None
        self._pulse_on = False

    def set_color(self, color):
        self._dot_color = color
        if self._pulse_job is None:
            self.configure(fg_color=color)

    def start_pulse(self):
        if self._pulse_job is None:
            self._pulse_tick()

    def stop_pulse(self):
        if self._pulse_job is not None:
            try:
                self.after_cancel(self._pulse_job)
            except Exception:
                pass
            self._pulse_job = None
        if self.winfo_exists():
            self.configure(fg_color=self._dot_color)

    def _pulse_tick(self):
        if not self.winfo_exists():
            return
        self._pulse_on = not self._pulse_on
        self.configure(fg_color=self._dot_color if self._pulse_on else COLORS["border"])
        self._pulse_job = self.after(550, self._pulse_tick)


class StatusLabel(ctk.CTkLabel):
    """CTkLabel de estado global con listeners.

    Se usa igual que antes (`lbl_status.configure(text=..., text_color=...)`),
    por lo que los workers existentes (clicker, macro, vision, black_souls) no cambian.
    Además:
      * si se llama desde un hilo secundario, la actualización se delega al hilo
        principal de Tk (más seguro que tocar widgets desde threads);
      * notifica a los listeners registrados con `add_listener(fn(text, color))`.
    """

    def __init__(self, master, **kwargs):
        self._listeners = []
        super().__init__(master, **kwargs)

    def add_listener(self, fn):
        self._listeners.append(fn)

    def configure(self, require_redraw=False, **kwargs):
        if threading.current_thread() is not threading.main_thread():
            try:
                self.after(0, lambda kw=dict(kwargs): self._apply(kw))
            except Exception:
                pass
            return
        self._apply(kwargs)

    def _apply(self, kwargs):
        try:
            super().configure(**kwargs)
        except Exception:
            return
        if ("text" in kwargs or "text_color" in kwargs) and self._listeners:
            text = self.cget("text")
            color = self.cget("text_color")
            for fn in list(self._listeners):
                try:
                    fn(text, color)
                except Exception:
                    pass


class LogConsole(ctk.CTkFrame):
    """Consola de logs de solo lectura con marcas de tiempo [HH:MM:SS]."""

    LEVEL_COLORS = {
        "info": COLORS["text_dim"],
        "ok": COLORS["success"],
        "proc": COLORS["process"],
        "warn": COLORS["warning"],
        "err": COLORS["error"],
    }

    def __init__(self, master, title="Consola de registros", max_lines=500, height=120):
        super().__init__(master, fg_color=COLORS["card"], corner_radius=12,
                         border_width=1, border_color=COLORS["border_soft"])
        self._max_lines = max_lines

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(10, 4))
        ctk.CTkLabel(head, text=title, font=(FONT, 12, "bold"),
                     text_color=COLORS["accent_text"]).pack(side="left")
        ctk.CTkButton(
            head, text="Limpiar", width=60, height=22, corner_radius=6,
            font=(FONT, 10), fg_color=COLORS["card_alt"], hover_color=COLORS["border"],
            text_color=COLORS["text_dim"], command=self.clear,
        ).pack(side="right")

        self.textbox = ctk.CTkTextbox(
            self, height=height, fg_color=COLORS["console"], text_color=COLORS["text_dim"],
            border_width=1, border_color=COLORS["border_soft"], corner_radius=8,
            font=("Consolas", 11), wrap="word", state="disabled",
        )
        self.textbox.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.textbox.tag_config("ts", foreground=COLORS["text_mute"])
        for level, color in self.LEVEL_COLORS.items():
            self.textbox.tag_config(level, foreground=color)

    def log(self, message, level="info"):
        if level not in self.LEVEL_COLORS:
            level = "info"
        stamp = time.strftime("[%H:%M:%S]")
        self.textbox.configure(state="normal")
        self.textbox.insert("end", stamp + " ", "ts")
        self.textbox.insert("end", message + "\n", level)
        try:
            lines = int(self.textbox.index("end-1c").split(".")[0])
            if lines > self._max_lines:
                self.textbox.delete("1.0", f"{lines - self._max_lines + 1}.0")
        except Exception:
            pass
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def clear(self):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")


# ----------------------------------------------------------------------
# Fábricas de widgets con el estilo del tema
# ----------------------------------------------------------------------
def styled_entry(master, textvariable=None, width=60, height=28, justify="left", **kwargs):
    return ctk.CTkEntry(
        master, textvariable=textvariable, width=width, height=height, justify=justify,
        fg_color=COLORS["input"], border_color=COLORS["border"], border_width=1,
        text_color=COLORS["text"], corner_radius=8, font=(FONT, 11), **kwargs,
    )


def styled_option_menu(master, values, variable=None, width=90, command=None, **kwargs):
    return ctk.CTkOptionMenu(
        master, values=values, variable=variable, width=width, height=28, command=command,
        fg_color=COLORS["input"], button_color=COLORS["accent"], button_hover_color=COLORS["accent_hover"],
        dropdown_fg_color=COLORS["card_alt"], dropdown_hover_color=COLORS["accent"],
        dropdown_text_color=COLORS["text"], text_color=COLORS["text"],
        corner_radius=8, font=(FONT, 11), dropdown_font=(FONT, 11), **kwargs,
    )


def styled_switch(master, text, variable=None, command=None, **kwargs):
    return ctk.CTkSwitch(
        master, text=text, variable=variable, command=command,
        progress_color=COLORS["accent"], button_color="#FFFFFF", button_hover_color=COLORS["accent_text"],
        fg_color=COLORS["border"], text_color=COLORS["text"], font=(FONT, 11),
        switch_width=38, switch_height=18, **kwargs,
    )


def styled_radio(master, text, variable, value, **kwargs):
    return ctk.CTkRadioButton(
        master, text=text, variable=variable, value=value,
        fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
        border_color=COLORS["border"], text_color=COLORS["text"],
        font=(FONT, 11), radiobutton_width=18, radiobutton_height=18, **kwargs,
    )


def primary_button(master, text, command=None, height=32, **kwargs):
    return ctk.CTkButton(
        master, text=text, command=command, height=height, corner_radius=8,
        fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
        text_color="#FFFFFF", font=(FONT, 11, "bold"), **kwargs,
    )


def ghost_button(master, text, command=None, width=30, height=28, **kwargs):
    return ctk.CTkButton(
        master, text=text, command=command, width=width, height=height, corner_radius=8,
        fg_color=COLORS["card_alt"], hover_color=COLORS["border"],
        text_color=COLORS["text_dim"], font=(FONT, 11), **kwargs,
    )


class LabeledField(ctk.CTkFrame):
    """Etiqueta superior + campo numérico + unidad (ej. 'Tras abrir:  [400] ms')."""

    def __init__(self, master, label, variable, unit="", width=64):
        super().__init__(master, fg_color="transparent")
        ctk.CTkLabel(self, text=label, font=(FONT, 10), text_color=COLORS["text_dim"],
                     anchor="w").pack(fill="x")
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=(2, 0))
        self.entry = styled_entry(row, textvariable=variable, width=width, justify="center")
        self.entry.pack(side="left")
        if unit:
            ctk.CTkLabel(row, text=unit, font=(FONT, 10),
                         text_color=COLORS["text_mute"]).pack(side="left", padx=(6, 0))


class ImagePathRow(ctk.CTkFrame):
    """Fila 'etiqueta + ruta + [...]' con un punto verde/rojo según exista el archivo."""

    def __init__(self, master, label, variable, on_browse, label_width=104):
        super().__init__(master, fg_color="transparent")
        self._var = variable
        ctk.CTkLabel(self, text=label, width=label_width, anchor="w", font=(FONT, 10),
                     text_color=COLORS["text_dim"]).pack(side="left")
        self.dot = StatusDot(self, size=8, color=COLORS["text_mute"])
        self.dot.pack(side="left", padx=(0, 6))
        styled_entry(self, textvariable=variable, height=26).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ghost_button(self, "…", command=on_browse, width=30, height=26).pack(side="right")
        variable.trace_add("write", lambda *_: self.refresh())
        self.refresh()

    def refresh(self):
        try:
            ok = os.path.exists(self._var.get())
        except Exception:
            ok = False
        if self.winfo_exists():
            self.dot.set_color(COLORS["success"] if ok else COLORS["error"])
