import os

import customtkinter as ctk

from config import PROFILES_DIR
from ui_components import (
    COLORS, FONT, Card,
    styled_entry, styled_switch, primary_button, ghost_button,
)

# (texto, atributo del botón, atributo del app que guarda la tecla)
FIELD_W = 180        # ancho fijo de combo / campo de perfiles: no se estira al cambiar la ventana
BTN_W = 90           # ancho de los botones Cargar / Guardar
MSG_MS = 4000        # cuánto se muestra el mensaje de «guardado / cargado»

HOTKEYS = (
    ("Clicker principal", "btn_hk_main", "key_main"),
    ("Secuencias", "btn_hk_macro", "key_macro"),
    ("Auto-Inventario", "btn_hk_vision", "key_vision"),
    ("Black Souls", "btn_hk_bs", "key_bs"),
)


class TabAjustes(ctk.CTkFrame):
    """Comportamiento de la ventana, atajos y perfiles guardados."""

    def __init__(self, master, app_ref):
        super().__init__(master, fg_color="transparent")
        self.app_ref = app_ref
        self._msg_job = None
        self._build_ui()

    # ==================================================================
    # INTERFAZ
    # ==================================================================
    def _build_ui(self):
        # Fila superior (Comportamiento y Atajos)
        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 16))
        row1.grid_columnconfigure(0, weight=1, uniform="cols")
        row1.grid_columnconfigure(1, weight=1, uniform="cols")
        row1.grid_rowconfigure(0, weight=1)
        self._build_behavior_card(row1).grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._build_hotkeys_card(row1).grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        # Fila inferior (Perfiles guardados)
        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x")
        row2.grid_columnconfigure(0, weight=1, uniform="cols")
        row2.grid_columnconfigure(1, weight=1, uniform="cols")
        row2.grid_rowconfigure(0, weight=1)
        self._build_profiles_card(row2).grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._build_storage_card(row2).grid(row=0, column=1, sticky="nsew", padx=(8, 0))

    # ---------------- Tarjeta: comportamiento ----------------
    def _build_behavior_card(self, parent):
        card = Card(parent, title="Comportamiento")
        body = card.body

        self.check_topmost = styled_switch(
            body, "Mantener ventana siempre visible", command=self.app_ref._toggle_topmost)
        self.check_topmost.pack(anchor="w")

        self.check_tray = styled_switch(body, "Minimizar a la bandeja del sistema")
        self.check_tray.select()
        self.check_tray.pack(anchor="w", pady=(14, 0))

        self.check_countdown = styled_switch(body, "Cuenta regresiva de 3 s antes de iniciar")
        self.check_countdown.pack(anchor="w", pady=(14, 0))

        ctk.CTkLabel(body, text="Con la bandeja activa, cerrar la ventana la oculta en lugar de salir.",
                     anchor="w", justify="left", wraplength=310, font=(FONT, 10),
                     text_color=COLORS["text_mute"]).pack(fill="x", pady=(16, 0))
        return card

    # ---------------- Tarjeta: atajos ----------------
    def _build_hotkeys_card(self, parent):
        card = Card(parent, title="Atajos de teclado")
        body = card.body

        for text, btn_attr, key_attr in HOTKEYS:
            line = ctk.CTkFrame(body, fg_color="transparent")
            line.pack(fill="x", pady=(0, 8))
            ctk.CTkLabel(line, text=text, anchor="w", font=(FONT, 11),
                         text_color=COLORS["text"]).pack(side="left")
            btn = ghost_button(
                line, f"Atajo: {self._key_name(key_attr)}", width=120, height=26,
                command=lambda k=key_attr: self.app_ref._prepare_hotkey_capture(k))
            btn.pack(side="right")
            setattr(self, btn_attr, btn)

        ctk.CTkFrame(body, height=1, fg_color=COLORS["border_soft"]).pack(fill="x", pady=(4, 10))

        line = ctk.CTkFrame(body, fg_color="transparent")
        line.pack(fill="x")
        ctk.CTkLabel(line, text="Parada de emergencia", anchor="w", font=(FONT, 11),
                     text_color=COLORS["text"]).pack(side="left")
        ctk.CTkLabel(line, text="SHIFT + ESC", font=(FONT, 10, "bold"),
                     text_color=COLORS["accent_text"], fg_color=COLORS["card_alt"],
                     corner_radius=6, height=24, width=120).pack(side="right")

        ctk.CTkLabel(body, text="El atajo de grabar se cambia en la pestaña Secuencias.",
                     anchor="w", justify="left", wraplength=310, font=(FONT, 10),
                     text_color=COLORS["text_mute"]).pack(fill="x", pady=(14, 0))
        return card

    # ---------------- Tarjeta: perfiles ----------------
    def _build_profiles_card(self, parent):
        card = Card(parent, title="Perfiles guardados")
        body = card.body

        # Campos de ancho fijo con su botón pegado a la derecha: al cambiar el tamaño de la
        # ventana la tarjeta crece, pero el contenido no se estira ni se separa.
        f_load = ctk.CTkFrame(body, fg_color="transparent")
        f_load.pack(anchor="w")
        self.combo_profiles = ctk.CTkComboBox(
            f_load, values=self._profile_names(), width=FIELD_W, height=28, corner_radius=8,
            font=(FONT, 11), dropdown_font=(FONT, 11), fg_color=COLORS["input"],
            border_color=COLORS["border"], border_width=1, button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"], dropdown_fg_color=COLORS["card_alt"],
            dropdown_hover_color=COLORS["accent"], dropdown_text_color=COLORS["text"],
            text_color=COLORS["text"])
        self.combo_profiles.pack(side="left")
        ghost_button(f_load, "Cargar", command=self.app_ref._load_selected_profile,
                     width=BTN_W, height=28).pack(side="left", padx=(8, 0))

        ctk.CTkFrame(body, height=1, fg_color=COLORS["border_soft"]).pack(fill="x", pady=14)

        f_save = ctk.CTkFrame(body, fg_color="transparent")
        f_save.pack(anchor="w")
        self.entry_profile_name = styled_entry(
            f_save, width=FIELD_W, height=28, placeholder_text="Nombre del nuevo perfil…")
        self.entry_profile_name.pack(side="left")
        self.entry_profile_name.bind("<Return>", lambda _e: self.app_ref._save_profile())
        primary_button(f_save, "Guardar", command=self.app_ref._save_profile,
                       height=28, width=BTN_W).pack(side="left", padx=(8, 0))

        # Mensaje de resultado (guardado / cargado / error); reserva su altura para que
        # la tarjeta no salte cuando aparece o desaparece.
        self.lbl_profile_msg = ctk.CTkLabel(
            body, text="", anchor="w", justify="left", wraplength=310, height=30,
            font=(FONT, 10), text_color=COLORS["text_mute"])
        self.lbl_profile_msg.pack(fill="x", pady=(12, 0))
        self._show_default_msg()
        return card

    # ---------------- Tarjeta: carpeta de perfiles ----------------
    def _build_storage_card(self, parent):
        card = Card(parent, title="Carpeta de perfiles")
        body = card.body

        self.lbl_profile_count = ctk.CTkLabel(
            body, text="", anchor="w", font=(FONT, 11), text_color=COLORS["text"])
        self.lbl_profile_count.pack(fill="x")

        ctk.CTkLabel(body, text=PROFILES_DIR, anchor="w", justify="left", wraplength=310,
                     font=(FONT, 10), text_color=COLORS["text_mute"]).pack(fill="x", pady=(6, 0))

        ghost_button(body, "Abrir carpeta", command=self._open_profiles_folder,
                     width=BTN_W + 20, height=28).pack(anchor="w", pady=(14, 0))
        self._refresh_count()
        return card

    # ==================================================================
    # API PÚBLICA (la usa main.py)
    # ==================================================================
    def on_show(self):
        """main._switch_tab lo llama al mostrar esta pestaña: sincroniza atajos y perfiles."""
        for _text, btn_attr, key_attr in HOTKEYS:
            getattr(self, btn_attr).configure(text=f"Atajo: {self._key_name(key_attr)}")

        self.refresh_profiles()

    def refresh_profiles(self, select=None):
        """Recarga la lista del combo desde app_ref.profiles; `select` deja ese perfil elegido."""
        names = self._profile_names()
        self.combo_profiles.configure(values=names)
        if select is not None:
            self.combo_profiles.set(select)
        self._refresh_count()

    def notify(self, text, kind="ok"):
        """Muestra un mensaje breve bajo los botones de perfil (kind: ok | error | warning)."""
        color = {"ok": COLORS["success"], "error": COLORS["error"],
                 "warning": COLORS["warning"]}.get(kind, COLORS["text_mute"])
        self.lbl_profile_msg.configure(text=text, text_color=color)
        if self._msg_job is not None:
            try:
                self.after_cancel(self._msg_job)
            except Exception:
                pass
        self._msg_job = self.after(MSG_MS, self._show_default_msg)

    # ==================================================================
    # UTILIDADES
    # ==================================================================
    def _profile_names(self):
        names = sorted(self.app_ref.profiles.keys(), key=str.lower)
        return names or ["Por defecto"]

    def _show_default_msg(self):
        self._msg_job = None
        self.lbl_profile_msg.configure(
            text="Un perfil guarda intervalo, secuencia, tiempos, imágenes, "
                 "opciones de esta pestaña y los atajos.",
            text_color=COLORS["text_mute"])

    def _refresh_count(self):
        n = len(self.app_ref.profiles)
        self.lbl_profile_count.configure(
            text="Sin perfiles guardados" if n == 0
            else f"{n} perfil guardado" if n == 1 else f"{n} perfiles guardados")

    def _open_profiles_folder(self):
        try:
            os.makedirs(PROFILES_DIR, exist_ok=True)
            os.startfile(PROFILES_DIR)   # solo Windows, igual que el resto de la app
        except Exception:
            self.notify("No se pudo abrir la carpeta.", "error")

    def _key_name(self, key_attr):
        try:
            return self.app_ref._get_key_name(getattr(self.app_ref, key_attr))
        except Exception:
            return "—"