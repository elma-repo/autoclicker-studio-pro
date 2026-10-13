import os

import customtkinter as ctk
from PIL import Image

from config import ruta_recurso, PROFILES_DIR
from ui_components import COLORS, FONT, Card, ghost_button

APP_NAME = "AutoClicker Studio Pro"
APP_VERSION = "1.0.0"       # ajusta este valor cuando publiques una versión nueva
APP_CODENAME = "Studio"     # nombre en clave de la versión

APP_DESCRIPTION = (
    "Automatiza clics, secuencias de ratón y teclado, y rutinas guiadas por imagen. "
    "Incluye módulos dedicados para War of Genesis, Black Souls y un editor visual de flujos."
)

# (icono, nombre, descripción)
MODULES = (
    ("📌", "Principal",   "Clicker básico con intervalo, repetición y posición."),
    ("⚡", "Secuencias",  "Graba, edita, exporta e importa macros de ratón y teclado."),
    ("📦", "Inventario",  "Detecta imágenes en pantalla y traslada ítems entre pestañas."),
    ("🐰", "Black Souls", "Farmeo automático por ruta con detección de combate."),
    ("🔀", "Flujos",      "Constructor visual de automatizaciones por bloques."),
    ("⚙️", "Ajustes",     "Comportamiento de la ventana, atajos y perfiles guardados."),
)

# (nombre, atributo del app que guarda la tecla)
HOTKEYS = (
    ("Clicker principal", "key_main"),
    ("Secuencias", "key_macro"),
    ("Auto-Inventario", "key_vision"),
    ("Black Souls", "key_bs"),
    ("Grabar secuencia", "key_record"),
)

TECH = "Python · CustomTkinter · pynput · PyAutoGUI · Pillow · pywin32 · pystray"


class TabAbout(ctk.CTkFrame):
    def __init__(self, master, app_ref):
        super().__init__(master, fg_color="transparent")
        self.app_ref = app_ref
        self._hotkey_labels = {}
        self._logo_img = None

        self.scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
        )
        self.scroll.pack(fill="both", expand=True)

        self._build_hero_card()

        row = ctk.CTkFrame(self.scroll, fg_color="transparent")
        row.pack(fill="x", pady=(16, 0))
        row.grid_columnconfigure(0, weight=1, uniform="cols")
        row.grid_columnconfigure(1, weight=1, uniform="cols")
        self._build_modules_card(row).grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._build_hotkeys_card(row).grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self._build_data_card()
        self.refresh()

    # ==================================================================
    # INTERFAZ
    # ==================================================================
    def _build_hero_card(self):
        card = Card(self.scroll)
        card.pack(fill="x")
        row = ctk.CTkFrame(card.body, fg_color="transparent")
        row.pack(fill="x")

        badge = ctk.CTkFrame(row, width=52, height=52, corner_radius=14, fg_color=COLORS["accent"])
        badge.pack(side="left")
        badge.pack_propagate(False)
        try:
            path = ruta_recurso(os.path.join("assets", "app", "ui_lightning_white.png"))
            img = Image.open(path)
            self._logo_img = ctk.CTkImage(light_image=img, dark_image=img, size=(26, 26))
            ctk.CTkLabel(badge, text="", image=self._logo_img).pack(expand=True)
        except Exception:
            ctk.CTkLabel(badge, text="⚡", font=(FONT, 24), text_color="#FFFFFF").pack(expand=True)

        texts = ctk.CTkFrame(row, fg_color="transparent")
        texts.pack(side="left", fill="x", expand=True, padx=(16, 0))

        title_row = ctk.CTkFrame(texts, fg_color="transparent")
        title_row.pack(fill="x")
        ctk.CTkLabel(title_row, text=APP_NAME, anchor="w",
                     font=(FONT, 20, "bold"), text_color=COLORS["text"]).pack(side="left")
        ctk.CTkLabel(title_row, text=f"v{APP_VERSION} · {APP_CODENAME}",
                     font=(FONT, 10, "bold"),
                     text_color=COLORS["accent_text"], fg_color=COLORS["card_alt"],
                     corner_radius=6, width=110, height=20).pack(side="left", padx=(10, 0))

        ctk.CTkLabel(texts, text=APP_DESCRIPTION, anchor="w", justify="left", wraplength=520,
                     font=(FONT, 11), text_color=COLORS["text_dim"]).pack(fill="x", pady=(4, 0))

    def _build_modules_card(self, parent):
        card = Card(parent, title="Módulos")
        for icon, name, desc in MODULES:
            item = ctk.CTkFrame(card.body, fg_color="transparent")
            item.pack(fill="x", pady=(0, 10))
            ctk.CTkLabel(item, text=icon, width=30, font=(FONT, 16)).pack(side="left", anchor="n")
            txt = ctk.CTkFrame(item, fg_color="transparent")
            txt.pack(side="left", fill="x", expand=True, padx=(6, 0))
            ctk.CTkLabel(txt, text=name, anchor="w", font=(FONT, 11, "bold"),
                         text_color=COLORS["text"]).pack(fill="x")
            ctk.CTkLabel(txt, text=desc, anchor="w", justify="left", wraplength=250,
                         font=(FONT, 10), text_color=COLORS["text_mute"]).pack(fill="x")
        return card

    def _build_hotkeys_card(self, parent):
        card = Card(parent, title="Atajos de teclado")
        body = card.body

        for name, attr in HOTKEYS:
            self._hotkey_labels[attr] = self._hotkey_row(body, name)

        ctk.CTkFrame(body, height=1, fg_color=COLORS["border_soft"]).pack(fill="x", pady=(6, 10))
        self._hotkey_row(body, "Parada de emergencia", fixed="SHIFT + ESC")

        ctk.CTkLabel(body, text="Puedes cambiarlos en Ajustes (y el de grabar en Secuencias).",
                     anchor="w", justify="left", wraplength=250, font=(FONT, 10),
                     text_color=COLORS["text_mute"]).pack(fill="x", pady=(12, 0))
        return card

    def _hotkey_row(self, parent, name, fixed=None):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(row, text=name, anchor="w", font=(FONT, 11),
                     text_color=COLORS["text"]).pack(side="left")
        chip = ctk.CTkLabel(row, text=fixed or "—", font=(FONT, 10, "bold"),
                            text_color=COLORS["accent_text"], fg_color=COLORS["card_alt"],
                            corner_radius=6, height=22, width=92)
        chip.pack(side="right")
        return chip

    def _build_data_card(self):
        card = Card(self.scroll, title="Datos y tecnologías")
        card.pack(fill="x", pady=(16, 0))
        body = card.body

        self._path_row(body, "Perfiles", PROFILES_DIR, PROFILES_DIR, first=True)
        assets_dir = ruta_recurso("assets")
        self._path_row(body, "Assets", assets_dir, assets_dir)

        ctk.CTkLabel(body, text=TECH, anchor="w", font=(FONT, 10),
                     text_color=COLORS["text_mute"]).pack(fill="x", pady=(12, 0))

    def _path_row(self, parent, label, path_text, folder, first=False):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(0 if first else 8, 0))
        ctk.CTkLabel(row, text=label, width=64, anchor="w", font=(FONT, 11),
                     text_color=COLORS["text_dim"]).pack(side="left")
        ghost_button(row, "Abrir carpeta", command=lambda f=folder: self._open_folder(f),
                     width=100, height=24).pack(side="right")
        ctk.CTkLabel(row, text=path_text, anchor="w", justify="left", wraplength=360,
                     font=(FONT, 10), text_color=COLORS["text_mute"]).pack(
            side="left", fill="x", expand=True, padx=(0, 10))

    # ==================================================================
    # API PÚBLICA (la usa main.py)
    # ==================================================================
    def on_show(self):
        """main._switch_tab lo llama al mostrar esta pestaña (los atajos pueden haber cambiado)."""
        self.refresh()

    def refresh(self):
        for attr, chip in self._hotkey_labels.items():
            try:
                chip.configure(text=self.app_ref._get_key_name(getattr(self.app_ref, attr)))
            except Exception:
                chip.configure(text="—")

    # ==================================================================
    # UTILIDADES
    # ==================================================================
    @staticmethod
    def _open_folder(folder):
        try:
            os.makedirs(folder, exist_ok=True)   # perfiles/ no existe hasta guardar el primero
            os.startfile(folder)   # solo Windows, igual que el resto de la app
        except Exception:
            pass