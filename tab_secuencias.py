import json
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

from ui_components import (
    COLORS, FONT, Card, NativeScrollFrame, StepCard,
    styled_entry, styled_option_menu, styled_radio, primary_button, ghost_button,
)

REC_COUNTDOWN_S = 3
SPEED_VALUES = ["0.5x", "0.75x", "1x", "1.5x", "2x", "3x"]
KEY_MODES = ["Pulsar", "Mantener ▼", "Soltar ▲"]
KNOWN_STEP_TYPES = {
    "mouse", "mouse_drag", "mouse_scroll", "mouse_down", "mouse_up",
    "keyboard", "key_down", "key_up",
}
# Teclas que forman parte de la combinación Shift+Esc (no se graban al detener con ella)
STOP_COMBO_KEYS = ("Key.shift", "Key.shift_l", "Key.shift_r", "Key.esc")


class TabSecuencias(ctk.CTkFrame):
    """Editor de secuencias: botón de inicio, reproducción, grabación, añadir pasos y lista.

    Mantiene los nombres que usan main.py, macro_engine.py y los perfiles:
    step_cards, macro_scroll, macro_repeat_mode, entry_macro_repeats, macro_speed,
    btn_hk_record, btn_macro_pos, lbl_macro_pos, btn_macro_key, lbl_macro_key,
    temp_macro_x/y/key/key_display, get_speed(), add_steps(), clear_all_steps(),
    toggle_recording(), stop_recording(), show_rec_count(), is_counting_down().
    """

    def __init__(self, master, app_ref):
        super().__init__(master, fg_color="transparent")
        self.app_ref = app_ref
        self.step_cards = []

        self.temp_macro_x = 0
        self.temp_macro_y = 0
        self.temp_macro_key = None
        self.temp_macro_key_display = ""

        self._countdown_job = None
        self._running = False

        self._build_ui()

        # Escucha los cambios de estado que publica el worker (macro_engine.py no se toca)
        lbl = getattr(app_ref, "lbl_status", None)
        if lbl is not None and hasattr(lbl, "add_listener"):
            lbl.add_listener(self._on_status)

    # ==================================================================
    # INTERFAZ
    # ==================================================================
    def _build_ui(self):
        self._build_run_bar()

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=(12, 0))
        row.grid_columnconfigure(0, weight=1, uniform="cols")
        row.grid_columnconfigure(1, weight=1, uniform="cols")
        row.grid_rowconfigure(0, weight=1)
        self._build_playback_card(row).grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._build_record_card(row).grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self._build_add_card().pack(fill="x", pady=(12, 0))
        self._build_steps_card().pack(fill="both", expand=True, pady=(12, 0))

    # ---------------- Barra superior: botón de inicio ----------------
    def _build_run_bar(self):
        self.btn_run = primary_button(self, "", height=40, command=self._on_run_clicked)
        self.btn_run.pack(fill="x")
        self._update_run_button()

    # ---------------- Tarjeta: reproducción ----------------
    def _build_playback_card(self, parent):
        card = Card(parent, title="Reproducción")
        body = card.body

        self.macro_repeat_mode = ctk.StringVar(value="infinite")
        self.rb_infinite = styled_radio(body, "", self.macro_repeat_mode, "infinite")
        self.rb_infinite.pack(anchor="w")

        f_fixed = ctk.CTkFrame(body, fg_color="transparent")
        f_fixed.pack(anchor="w", pady=(8, 0))
        styled_radio(f_fixed, "Repetir", self.macro_repeat_mode, "fixed").pack(side="left")
        self.entry_macro_repeats = styled_entry(f_fixed, width=60, height=26, justify="center")
        self.entry_macro_repeats.insert(0, "10")
        self.entry_macro_repeats.pack(side="left", padx=(8, 8))
        ctk.CTkLabel(f_fixed, text="ciclos", font=(FONT, 10),
                     text_color=COLORS["text_mute"]).pack(side="left")

        # Velocidad de reproducción (afecta esperas, teclas/clics mantenidos y arrastres)
        f_speed = ctk.CTkFrame(body, fg_color="transparent")
        f_speed.pack(anchor="w", pady=(10, 0))
        ctk.CTkLabel(f_speed, text="Velocidad", font=(FONT, 10),
                     text_color=COLORS["text_dim"]).pack(side="left", padx=(0, 8))
        self.macro_speed = ctk.StringVar(value="1x")
        styled_option_menu(f_speed, SPEED_VALUES, variable=self.macro_speed,
                           width=84).pack(side="left")

        self._refresh_infinite_text()
        return card

    # ---------------- Tarjeta: grabación y archivo ----------------
    def _build_record_card(self, parent):
        card = Card(parent, title="Grabación y archivo")
        body = card.body

        f_rec = ctk.CTkFrame(body, fg_color="transparent")
        f_rec.pack(anchor="w")
        self.btn_record = primary_button(f_rec, "", height=30, width=124,
                                         command=self.toggle_recording)
        self.btn_record.pack(side="left")
        self._set_record_button(False)

        hk_name = self.app_ref._get_key_name(self.app_ref.key_record)
        self.btn_hk_record = ghost_button(
            f_rec, f"Atajo: {hk_name}", width=104, height=30,
            command=lambda: self.app_ref._prepare_hotkey_capture("key_record"))
        self.btn_hk_record.pack(side="left", padx=(8, 0))

        f_file = ctk.CTkFrame(body, fg_color="transparent")
        f_file.pack(anchor="w", pady=(10, 0))
        ghost_button(f_file, "📂 Importar", command=self.import_macro_file,
                     width=96, height=28).pack(side="left")
        ghost_button(f_file, "💾 Exportar", command=self.export_macro_file,
                     width=96, height=28).pack(side="left", padx=(8, 0))
        return card

    # ---------------- Tarjeta: añadir paso ----------------
    def _build_add_card(self):
        card = Card(self, title="Añadir paso")
        body = card.body

        # Acciones de ratón
        f_mouse = ctk.CTkFrame(body, fg_color="transparent")
        f_mouse.pack(fill="x")

        self.btn_macro_pos = ghost_button(f_mouse, "📍 Coord", width=78, height=28,
                                          command=self.app_ref._prepare_capture_macro_pos)
        self.btn_macro_pos.pack(side="left")
        self.lbl_macro_pos = ctk.CTkLabel(f_mouse, text="(0, 0)", width=66, font=(FONT, 10),
                                          text_color=COLORS["text_dim"])
        self.lbl_macro_pos.pack(side="left", padx=(4, 4))
        self.combo_macro_btn = styled_option_menu(
            f_mouse, ["Izquierdo", "Derecho", "Central", "Doble"], width=104)
        self.combo_macro_btn.pack(side="left")
        ctk.CTkLabel(f_mouse, text="Espera", font=(FONT, 10),
                     text_color=COLORS["text_dim"]).pack(side="left", padx=(10, 4))
        self.entry_mouse_val = styled_entry(f_mouse, width=56, height=28, justify="center")
        self.entry_mouse_val.insert(0, "500")
        self.entry_mouse_val.pack(side="left")
        self.combo_mouse_unit = styled_option_menu(f_mouse, ["ms", "s", "m"], width=64)
        self.combo_mouse_unit.pack(side="left", padx=(4, 0))
        primary_button(f_mouse, "＋ Ratón", command=self.add_mouse_step,
                       height=28, width=84).pack(side="right")

        # Acciones de teclado
        f_key = ctk.CTkFrame(body, fg_color="transparent")
        f_key.pack(fill="x", pady=(10, 0))

        self.btn_macro_key = ghost_button(f_key, "⌨️ Tecla", width=78, height=28,
                                          command=self.app_ref._prepare_capture_macro_key)
        self.btn_macro_key.pack(side="left")
        self.lbl_macro_key = ctk.CTkLabel(f_key, text="[ Ninguna ]", width=66, font=(FONT, 10),
                                          text_color=COLORS["text_dim"])
        self.lbl_macro_key.pack(side="left", padx=(4, 4))
        # Pulsar / Mantener (key_down) / Soltar (key_up): sirve para armar combos a mano
        self.combo_key_mode = styled_option_menu(f_key, KEY_MODES, width=104)
        self.combo_key_mode.pack(side="left")
        ctk.CTkLabel(f_key, text="Espera", font=(FONT, 10),
                     text_color=COLORS["text_dim"]).pack(side="left", padx=(10, 4))
        self.entry_key_val = styled_entry(f_key, width=56, height=28, justify="center")
        self.entry_key_val.insert(0, "500")
        self.entry_key_val.pack(side="left")
        self.combo_key_unit = styled_option_menu(f_key, ["ms", "s", "m"], width=64)
        self.combo_key_unit.pack(side="left", padx=(4, 0))
        primary_button(f_key, "＋ Tecla", command=self.add_keyboard_step,
                       height=28, width=84).pack(side="right")
        return card

    # ---------------- Tarjeta: lista de pasos ----------------
    def _build_steps_card(self):
        card = Card(self)
        body = card.body

        f_head = ctk.CTkFrame(body, fg_color="transparent")
        f_head.pack(fill="x", pady=(0, 8))
        self.lbl_count = ctk.CTkLabel(f_head, text="Pasos", anchor="w", font=(FONT, 12, "bold"),
                                      text_color=COLORS["accent_text"])
        self.lbl_count.pack(side="left")
        btn_clear = ghost_button(f_head, "🗑️ Vaciar todo", command=self.clear_all_steps,
                                 width=108, height=26)
        btn_clear.configure(text_color=COLORS["error"])
        btn_clear.pack(side="right")

        self.macro_scroll = NativeScrollFrame(body, bg=COLORS["console"])
        self.macro_scroll.pack(fill="both", expand=True)

        self.empty_label = tk.Label(self.macro_scroll.interior, text="No hay pasos en la secuencia.",
                                    font=(FONT, 10), fg=COLORS["text_mute"], bg=COLORS["console"])
        self.empty_label.pack(pady=30)
        return card

    # ==================================================================
    # ESTADO DEL BOTÓN DE INICIO (solo UI)
    # ==================================================================
    def _hk(self):
        try:
            return self.app_ref._get_key_name(self.app_ref.key_macro)
        except Exception:
            return "F7"

    def _refresh_infinite_text(self):
        self.rb_infinite.configure(text=f"Infinito (hasta detener con {self._hk()})")

    def _update_run_button(self):
        if self._running:
            self.btn_run.configure(text=f"■  Detener ({self._hk()})",
                                   fg_color=COLORS["error"], hover_color=COLORS["error_hover"])
        else:
            self.btn_run.configure(text=f"▶  Iniciar ({self._hk()})",
                                   fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"])

    def _on_run_clicked(self):
        app = self.app_ref
        if app.is_recording or self.is_counting_down():
            app.lbl_status.configure(text="DETÉN LA GRABACIÓN ANTES DE REPRODUCIR",
                                     text_color="#EAB308")
            return
        app.toggle_engine("macro")

    def _set_idle(self):
        self._running = False
        self._update_run_button()

    def _on_status(self, text, color):
        """Listener del estado global (se ejecuta en el hilo de Tk).

        Solo sincroniza el botón: el texto de estado ya lo muestra la barra inferior.
        """
        active = getattr(self.app_ref, "active_mode", None) == "macro"
        if active:
            if not self._running:
                self._running = True
                self._update_run_button()
        elif self._running:
            self._set_idle()

    # ==================================================================
    # API PÚBLICA (la usa main.py)
    # ==================================================================
    def on_engine_started(self):
        """main._start_engine('macro') lo llama justo antes de lanzar el worker."""
        self._running = True
        self._update_run_button()

    def refresh_hotkey_label(self):
        """main.py lo llama cuando el usuario remapea el atajo de secuencias."""
        self._update_run_button()
        self._refresh_infinite_text()

    def on_show(self):
        """main._switch_tab lo llama al mostrar esta pestaña (los atajos pueden haber cambiado)."""
        self.refresh_hotkey_label()
        try:
            self.btn_hk_record.configure(
                text=f"Atajo: {self.app_ref._get_key_name(self.app_ref.key_record)}")
        except Exception:
            pass

    # ==================================================================
    # GRABACIÓN
    # ==================================================================
    def is_counting_down(self):
        return self._countdown_job is not None

    def toggle_recording(self):
        """Botón Grabar y atajo de grabación."""
        if self.app_ref.is_recording or self.is_counting_down():
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        app = self.app_ref
        if app.active_mode:
            app.stop_all()
        self._set_record_button(True)
        if app.tab_cfg.check_countdown.get() == 1:
            self._countdown_tick(REC_COUNTDOWN_S)
        else:
            self._begin_recording()

    def _countdown_tick(self, n):
        if n <= 0:
            self._begin_recording()
            return
        hk = self.app_ref._get_key_name(self.app_ref.key_record)
        self.app_ref.lbl_status.configure(
            text=f"GRABANDO EN {n}s... ({hk} PARA CANCELAR)", text_color="#EAB308")
        self._countdown_job = self.after(1000, lambda: self._countdown_tick(n - 1))

    def _begin_recording(self):
        self._countdown_job = None
        self.app_ref.recorder.start()
        self.app_ref.is_recording = True
        self.show_rec_count(0)

    def show_rec_count(self, n):
        app = self.app_ref
        if app.is_recording:
            hk = app._get_key_name(app.key_record)
            app.lbl_status.configure(
                text=f"GRABANDO... {n} EVENTOS · {hk} PARA DETENER", text_color="#EAB308")

    def stop_recording(self, trim_stop_combo=False):
        """Detiene la grabación (o cancela la cuenta regresiva) y añade lo grabado.

        trim_stop_combo=True: se detuvo con Shift+Esc, así que no se graba ese Shift.
        """
        app = self.app_ref
        was_recording = app.is_recording

        if self._countdown_job is not None:
            try:
                self.after_cancel(self._countdown_job)
            except Exception:
                pass
            self._countdown_job = None

        app.is_recording = False
        self._set_record_button(False)

        steps = []
        if was_recording:
            steps = app.recorder.stop(trim_keys=STOP_COMBO_KEYS if trim_stop_combo else None)
            if steps:
                self.add_steps(steps)

        if was_recording and steps:
            app.lbl_status.configure(text=f"ESTADO: DETENIDO · {len(steps)} PASOS GRABADOS", text_color="#EF4444")
        else:
            app.lbl_status.configure(text="ESTADO: DETENIDO", text_color="#EF4444")

    def _set_record_button(self, recording):
        if recording:
            self.btn_record.configure(text="⏹  Detener", fg_color=COLORS["accent"],
                                      hover_color=COLORS["accent_hover"])
        else:
            self.btn_record.configure(text="🔴  Grabar", fg_color=COLORS["error"],
                                      hover_color=COLORS["error_hover"])

    # ==================================================================
    # PASOS
    # ==================================================================
    def get_speed(self):
        try:
            v = float(self.macro_speed.get().lower().replace("x", "").replace(",", "."))
        except ValueError:
            return 1.0
        return min(5.0, max(0.25, v))

    def add_step(self, step_data, index=None, refresh=True):
        """Único punto donde se crea una StepCard. `index=None` = al final."""
        card = StepCard(
            self.macro_scroll.interior,
            step_data=step_data,
            on_delete=self._card_delete,
            on_move=self._card_move,
            on_duplicate=self._card_duplicate,
        )
        if index is None or index >= len(self.step_cards):
            self.step_cards.append(card)
            card.pack(fill="x", pady=1, padx=2, expand=False)
        else:
            before = self.step_cards[index]
            self.step_cards.insert(index, card)
            card.pack(before=before, fill="x", pady=1, padx=2, expand=False)

        if refresh:
            self.reindex_labels()
            self.macro_scroll._on_configure()
        return card

    def add_steps(self, steps):
        for step in steps:
            self.add_step(step, refresh=False)
        self.reindex_labels()
        self.macro_scroll._on_configure()

    def add_mouse_step(self):
        try:
            val = float(self.entry_mouse_val.get().replace(",", "."))
        except ValueError:
            val = 500.0

        self.add_step({
            "type": "mouse",
            "x": self.temp_macro_x,
            "y": self.temp_macro_y,
            "action": self.combo_macro_btn.get(),
            "time_val": max(0.0, val),
            "time_unit": self.combo_mouse_unit.get(),
        })

    def add_keyboard_step(self):
        if not self.temp_macro_key:
            return
        try:
            val = float(self.entry_key_val.get().replace(",", "."))
        except ValueError:
            val = 500.0

        mode = self.combo_key_mode.get()
        step_type = {"Mantener ▼": "key_down", "Soltar ▲": "key_up"}.get(mode, "keyboard")

        self.add_step({
            "type": step_type,
            "key": self.temp_macro_key,
            "key_display": self.temp_macro_key_display,
            "time_val": max(0.0, val),
            "time_unit": self.combo_key_unit.get(),
        })

        # Tras "Mantener" se conserva la tecla para poder añadir su "Soltar" enseguida
        if step_type != "key_down":
            self.temp_macro_key = None
            self.lbl_macro_key.configure(text="[ Ninguna ]")

    def reindex_labels(self):
        n = len(self.step_cards)
        self.lbl_count.configure(text="Pasos" if n == 0 else f"{n} paso" if n == 1 else f"{n} pasos")

        if not self.step_cards:
            self.empty_label.pack(pady=30)
            return

        self.empty_label.pack_forget()
        for idx, card in enumerate(self.step_cards):
            card.lbl_index.config(text=f"#{idx+1}")

    def _card_move(self, card, direction):
        if card not in self.step_cards:
            return
        idx = self.step_cards.index(card)

        if direction == "up" and idx > 0:
            target = self.step_cards[idx - 1]
            self.step_cards[idx], self.step_cards[idx - 1] = self.step_cards[idx - 1], self.step_cards[idx]
            card.pack(before=target, fill="x", pady=1, padx=2, expand=False)
            self.reindex_labels()

        elif direction == "down" and idx < len(self.step_cards) - 1:
            target = self.step_cards[idx + 1]
            self.step_cards[idx], self.step_cards[idx + 1] = self.step_cards[idx + 1], self.step_cards[idx]
            target.pack(before=card, fill="x", pady=1, padx=2, expand=False)
            self.reindex_labels()

    def _card_duplicate(self, card):
        if card not in self.step_cards:
            return
        idx = self.step_cards.index(card)
        self.add_step(card.get_current_data(), index=idx + 1)

    def _card_delete(self, card):
        if card in self.step_cards:
            self.step_cards.remove(card)
            card.destroy()
            self.reindex_labels()
            self.macro_scroll._on_configure()

    def clear_all_steps(self):
        for card in list(self.step_cards):
            card.destroy()
        self.step_cards.clear()
        self.reindex_labels()
        self.macro_scroll._on_configure()

    # ==================================================================
    # EXPORTAR / IMPORTAR
    # ==================================================================
    def export_macro_file(self):
        if not self.step_cards:
            messagebox.showwarning("Atención", "No hay pasos en la secuencia para exportar.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("Archivo Macro JSON", "*.json"), ("Todos los archivos", "*.*")],
            title="Guardar Macro Como"
        )
        if file_path:
            macro_data = {
                "format": "AutoClickerStudio_Macro",
                "repeat_mode": self.macro_repeat_mode.get(),
                "repeat_count": self.entry_macro_repeats.get(),
                "speed": self.macro_speed.get(),
                "steps": [card.get_current_data() for card in self.step_cards]
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(macro_data, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Exportación Exitosa", "Macro guardada correctamente.")

    @staticmethod
    def _validate_steps(steps):
        if not isinstance(steps, list):
            raise ValueError("Formato no reconocido")
        for idx, step in enumerate(steps, 1):
            if not isinstance(step, dict) or step.get("type") not in KNOWN_STEP_TYPES:
                raise ValueError(f"El paso #{idx} no es válido")

    def import_macro_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Archivo Macro JSON", "*.json"), ("Todos los archivos", "*.*")],
            title="Seleccionar Macro para Importar"
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                steps = data.get("steps", []) if isinstance(data, dict) and "steps" in data else data
                self._validate_steps(steps)     # se valida ANTES de borrar la secuencia actual

                self.clear_all_steps()
                self.add_steps(steps)

                if isinstance(data, dict):
                    self.macro_repeat_mode.set(data.get("repeat_mode", "infinite"))
                    self.entry_macro_repeats.delete(0, "end")
                    self.entry_macro_repeats.insert(0, data.get("repeat_count", "10"))
                    speed = data.get("speed", "1x")
                    self.macro_speed.set(speed if speed in SPEED_VALUES else "1x")

                messagebox.showinfo("Importación Exitosa", f"Se cargaron {len(steps)} pasos.")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo leer el archivo: {e}")
