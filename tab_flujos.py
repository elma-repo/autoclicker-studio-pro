"""Editor visual de flujos con ventana flotante dedicada.

Estructura:
  • TabFlujos         → pestaña compacta en la ventana principal (barra, resumen, log).
  • FlowEditorWindow  → ventana flotante con paleta arrastrable, lienzo, inspector
                        y selector de ventana objetivo.

Importar/Exportar vs. Guardar/Abrir:
  • Guardar/Abrir     → usa la carpeta `flujos/` del proyecto (tus flujos habituales).
  • Exportar/Importar → usa un diálogo libre (para compartir un .json con otra persona).

Contrato con main.py (sin cambios):
    TabFlujos(master, app_ref)
    on_show()
    stop_from_app()
"""
from __future__ import annotations

import os
import threading
import uuid
from tkinter import filedialog, messagebox

import customtkinter as ctk
import tkinter as tk

from logic_engine.flow_model import Flow, FlowNode
from logic_engine.flow_service import FlowService
from logic_engine.flow_validator import validate_flow
from config import ruta_recurso
from ui_components import COLORS, FONT, Card, styled_entry, styled_option_menu, ghost_button

from flow_canvas import FlowCanvas, NODE_W, NODE_H


FLOWS_DIR = ruta_recurso("flujos")
PANTALLA_COMPLETA = "(toda la pantalla)"

# (etiqueta, tipo, params por defecto, nombre sugerido, preferencia de posición)
PALETA = (
    ("🖼  Clic en imagen",     "action",       {"action": "click_image", "arguments": {"image": "", "confidence": 0.8, "timeout_s": 5.0}}, "Clic en imagen", "down"),
    ("⌖  Clic en coordenadas", "action",       {"action": "click_at", "arguments": {"x": 0, "y": 0}}, "Clic en coordenadas", "down"),
    ("⌨  Pulsar tecla",        "action",       {"action": "press_key", "arguments": {"key": "Key.enter"}}, "Pulsar tecla", "down"),
    ("📝  Registro (log)",     "action",       {"action": "log", "arguments": {"message": "Paso completado", "level": "info"}}, "Registro", "down"),
    ("⏱  Espera",             "wait",         {"seconds": 1.0}, "Esperar", "down"),
    ("❓  Si (imagen visible)", "condition",    {"condition": {"op": "image_visible", "image": "", "confidence": 0.8, "timeout_s": 3.0}}, "¿Imagen visible?", "right"),
    ("❓  Si (variable)",      "condition",    {"condition": {"op": "variable", "name": "contador", "operator": ">=", "value": 1}}, "¿Variable?", "right"),
    ("🔁  Bucle",             "loop",         {"max_iterations": 5, "counter_variable": ""}, "Bucle", "right"),
    ("🔢  Variable",           "set_variable", {"name": "contador", "operation": "set", "value": 0}, "Variable", "down"),
)


# =====================================================================
# PESTAÑA (ventana principal)
# =====================================================================
class TabFlujos(ctk.CTkFrame):
    def __init__(self, master, app_ref):
        super().__init__(master, fg_color="transparent")
        self.app_ref = app_ref
        self.service = FlowService(app_ref, logger=self._log_from_worker)

        self.stop_event = threading.Event()
        self.worker_thread: threading.Thread | None = None
        self.flow_name = ctk.StringVar(value="Mi primer flujo")
        self._id_seq = 0
        self._current_path: str | None = None     # ruta del .json guardado/abierto actual

        # Ventana objetivo del flujo
        self.target_window = ctk.StringVar(value=PANTALLA_COMPLETA)
        self.target_focus = ctk.BooleanVar(value=False)

        # Referencias al editor flotante y sus componentes
        self.editor: "FlowEditorWindow | None" = None
        self.canvas: FlowCanvas | None = None
        self.inspector_body: ctk.CTkScrollableFrame | None = None

        self._build_ui()
        self.after(80, self._ensure_editor)

    # ------------------------------------------------------------------
    # UI DE LA PESTAÑA
    # ------------------------------------------------------------------
    def _build_ui(self):
        self._build_toolbar()
        self._build_center_card()
        self._build_log()

    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=12,
                           border_width=1, border_color=COLORS["border_soft"])
        bar.pack(fill="x")

        # Fila 1: nombre + ejecutar/detener
        row1 = ctk.CTkFrame(bar, fg_color="transparent")
        row1.pack(fill="x", padx=14, pady=(10, 4))

        ctk.CTkLabel(row1, text="Nombre:", font=(FONT, 11, "bold"),
                     text_color=COLORS["text_dim"]).pack(side="left", padx=(0, 8))
        self.entry_name = styled_entry(row1, textvariable=self.flow_name, width=260, height=30)
        self.entry_name.pack(side="left")

        self.btn_stop = ghost_button(row1, "■  Detener", command=self.stop_execution,
                                     width=100, height=30)
        self.btn_stop.configure(state="disabled", text_color=COLORS["error"])
        self.btn_stop.pack(side="right")

        self.btn_run = ctk.CTkButton(
            row1, text="▶  Ejecutar", command=self.run_flow,
            width=110, height=30, corner_radius=8,
            fg_color=COLORS["success"], hover_color="#16A34A",
            text_color="#FFFFFF", font=(FONT, 11, "bold"))
        self.btn_run.pack(side="right", padx=(0, 6))

        # Fila 2: gestión de archivos
        row2 = ctk.CTkFrame(bar, fg_color="transparent")
        row2.pack(fill="x", padx=14, pady=(0, 10))

        ghost_button(row2, "🗑️ Nuevo", command=self._confirm_new,
                     width=90, height=28).pack(side="left", padx=(0, 6))
        ghost_button(row2, "📂 Abrir", command=self._load_dialog,
                     width=90, height=28).pack(side="left", padx=(0, 6))
        ghost_button(row2, "💾 Guardar", command=self._save_dialog,
                     width=90, height=28).pack(side="left", padx=(0, 6))
        ghost_button(row2, "📥 Importar", command=self._import_dialog,
                     width=96, height=28).pack(side="left", padx=(0, 6))
        ghost_button(row2, "📤 Exportar", command=self._export_dialog,
                     width=96, height=28).pack(side="left")

        self.lbl_saved = ctk.CTkLabel(row2, text="(sin guardar)", anchor="e",
                                      font=(FONT, 10), text_color=COLORS["text_mute"])
        self.lbl_saved.pack(side="right")

    def _build_center_card(self):
        card = Card(self, title="Editor de flujo")
        card.pack(fill="x", pady=(12, 0))
        body = card.body

        self.lbl_summary = ctk.CTkLabel(
            body, text="Sin bloques todavía.",
            anchor="w", font=(FONT, 11), text_color=COLORS["text"])
        self.lbl_summary.pack(fill="x")

        self.lbl_target = ctk.CTkLabel(
            body, text="", anchor="w", font=(FONT, 10), text_color=COLORS["text_mute"])
        self.lbl_target.pack(fill="x", pady=(4, 0))
        self._refresh_target_label()

        ctk.CTkLabel(
            body,
            text="El diagrama se edita en una ventana flotante: puedes moverla libremente, "
                 "incluso a un segundo monitor. Arrastra los bloques desde la paleta al lienzo.",
            anchor="w", justify="left", wraplength=520,
            font=(FONT, 10), text_color=COLORS["text_mute"],
        ).pack(fill="x", pady=(8, 14))

        ctk.CTkButton(
            body, text="🧩   Abrir editor de flujo", height=38, corner_radius=8,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            text_color="#FFFFFF", font=(FONT, 12, "bold"),
            command=self._open_editor,
        ).pack(fill="x")

    def _build_log(self):
        wrap = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=12,
                            border_width=1, border_color=COLORS["border_soft"])
        wrap.pack(fill="both", expand=True, pady=(12, 0))

        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(8, 4))
        ctk.CTkLabel(head, text="Registro", font=(FONT, 11, "bold"),
                     text_color=COLORS["accent_text"]).pack(side="left")
        ghost_button(head, "Limpiar", command=self._clear_log,
                     width=70, height=22).pack(side="right")

        self.log_box = ctk.CTkTextbox(
            wrap, height=140, fg_color=COLORS["console"], text_color=COLORS["text_dim"],
            border_width=0, corner_radius=8, font=("Consolas", 10), wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------
    # EDITOR FLOTANTE
    # ------------------------------------------------------------------
    def _ensure_editor(self) -> "FlowEditorWindow":
        if self.editor is not None and self.editor.winfo_exists():
            return self.editor
        self.editor = FlowEditorWindow(self.winfo_toplevel(), self)
        self.canvas = self.editor.canvas
        self.inspector_body = self.editor.inspector_body
        self._new_flow()
        return self.editor

    def _open_editor(self):
        editor = self._ensure_editor()
        editor.show()

    def _update_summary(self):
        if self.canvas is None:
            self.lbl_summary.configure(text="Sin bloques todavía.")
            return
        n_nodes = len(self.canvas.all_nodes())
        n_edges = len(self.canvas.edges())
        if n_nodes == 0:
            self.lbl_summary.configure(text="Sin bloques todavía.")
        else:
            plural_n = "" if n_nodes == 1 else "s"
            plural_e = "" if n_edges == 1 else "es"
            self.lbl_summary.configure(
                text=f"{n_nodes} bloque{plural_n} · {n_edges} conexión{plural_e}")

    def _refresh_target_label(self):
        t = self.target_window.get().strip()
        if t and t != PANTALLA_COMPLETA:
            self.lbl_target.configure(text=f"Ventana objetivo: {t}")
        else:
            self.lbl_target.configure(text="Ventana objetivo: toda la pantalla")

    def _update_saved_label(self):
        if self._current_path:
            self.lbl_saved.configure(text=os.path.basename(self._current_path))
        else:
            self.lbl_saved.configure(text="(sin guardar)")

    # ------------------------------------------------------------------
    # FLUJO: NUEVO / AÑADIR / BORRAR
    # ------------------------------------------------------------------
    def _new_id(self, prefix="n"):
        self._id_seq += 1
        return f"{prefix}_{uuid.uuid4().hex[:6]}"

    def _confirm_new(self):
        self._ensure_editor()
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("Flujos", "Detén la ejecución antes de crear un flujo nuevo.",
                                   parent=self)
            return
        if not messagebox.askyesno("Flujos", "¿Descartar el flujo actual y empezar uno nuevo?",
                                   parent=self):
            return
        self._new_flow()

    def _new_flow(self):
        if self.canvas is None:
            return
        self.flow_name.set("Mi primer flujo")
        self.target_window.set(PANTALLA_COMPLETA)
        self.target_focus.set(False)
        self._current_path = None
        self.canvas.clear()

        start_id = self._new_id("inicio")
        end_id = self._new_id("fin")
        self.canvas.add_node(FlowNode(id=start_id, type="start", name="Inicio"), 60, 40)
        self.canvas.add_node(FlowNode(id=end_id, type="end", name="Fin"), 60, 320)
        self.canvas.connect(start_id, "next", end_id)
        self.canvas.set_selected(start_id)
        self._update_summary()
        self._refresh_target_label()
        self._update_saved_label()

    def _add_node(self, node_type: str, params: dict, name: str,
                  x_root: int | None = None, y_root: int | None = None):
        """Crea un nodo. Con coordenadas de pantalla cae ahí (drop);
        sin ellas se coloca junto al seleccionado y se auto-conecta (clic)."""
        if self.canvas is None:
            return
        node = FlowNode(id=self._new_id(), type=node_type, name=name, params=dict(params))

        if x_root is not None and y_root is not None:
            cx, cy = self.canvas.screen_to_logical(x_root, y_root)
            x = max(0, cx - NODE_W // 2)
            y = max(0, cy - NODE_H // 2)
            self.canvas.add_node(node, x, y)
            self.canvas.set_selected(node.id)
            return

        sel = self.canvas.selected_id()
        prefer = "down"
        for _lbl, t, _p, _n, p in PALETA:
            if t == node_type and _n == name:
                prefer = p
                break
        pos = self.canvas.free_spot(sel, prefer=prefer)
        self.canvas.add_node(node, *pos)
        if sel:
            port = self.canvas.free_port(sel)
            if port:
                self.canvas.connect(sel, port, node.id)
        self.canvas.set_selected(node.id)

    # ------------------------------------------------------------------
    # CALLBACKS DEL CANVAS
    # ------------------------------------------------------------------
    def _on_canvas_select(self, node_id: str | None):
        self._refresh_inspector(node_id)

    def _on_canvas_change(self):
        self._update_summary()

    # ------------------------------------------------------------------
    # INSPECTOR
    # ------------------------------------------------------------------
    def _refresh_inspector(self, node_id: str | None):
        if self.inspector_body is None:
            return
        for w in self.inspector_body.winfo_children():
            w.destroy()

        if node_id is None:
            ctk.CTkLabel(self.inspector_body,
                         text="Selecciona un bloque del lienzo\npara editarlo aquí.",
                         font=(FONT, 11), text_color=COLORS["text_mute"],
                         justify="center").pack(pady=30)
            return

        node = self.canvas.get_node(node_id) if self.canvas else None
        if node is None:
            return

        self._field_entry(self.inspector_body, "Nombre del bloque", node.name or "",
                          lambda v: self._set_name(node, v))

        ctk.CTkFrame(self.inspector_body, height=1, fg_color=COLORS["border_soft"]).pack(
            fill="x", pady=10)

        if node.type == "start":
            self._hint("Punto de entrada del flujo. Conecta su puerto de salida al primer bloque.")
        elif node.type == "end":
            self._hint("Punto final. Cuando el flujo llega aquí, se detiene.")
        elif node.type == "action":
            self._inspector_action(node)
        elif node.type == "wait":
            self._inspector_wait(node)
        elif node.type == "condition":
            self._inspector_condition(node)
        elif node.type == "loop":
            self._inspector_loop(node)
        elif node.type == "set_variable":
            self._inspector_variable(node)

        if node.type not in ("start", "end"):
            ctk.CTkFrame(self.inspector_body, height=1, fg_color=COLORS["border_soft"]).pack(
                fill="x", pady=10)
            ghost_button(self.inspector_body, "🗑️ Eliminar bloque",
                         command=lambda: self.canvas.remove_node(node.id),
                         width=200, height=28).pack(fill="x")

    def _inspector_action(self, node: FlowNode):
        p = node.params
        a = p.get("action", "click_image")
        args = p.setdefault("arguments", {})

        self._field_option(
            self.inspector_body, "Tipo de acción",
            ["Clic en imagen", "Clic en coordenadas", "Pulsar tecla", "Registrar mensaje"],
            self._label_para_accion(a),
            lambda label: self._change_action(node, label),
        )

        if a == "click_image":
            self._field_entry(self.inspector_body, "Imagen", args.get("image", ""),
                              lambda v: self._set_arg(node, "image", v),
                              browse_images=True)
            self._field_entry(self.inspector_body, "Confianza (0.1 – 1.0)",
                              str(args.get("confidence", 0.8)),
                              lambda v: self._set_arg(node, "confidence", self._to_float(v, 0.8)))
            self._field_entry(self.inspector_body, "Esperar hasta (s)",
                              str(args.get("timeout_s", 5.0)),
                              lambda v: self._set_arg(node, "timeout_s", self._to_float(v, 5.0)))
            self._hint("Sin timeout (0) = una sola búsqueda. Con timeout > 0 = espera hasta que aparezca.")
        elif a == "click_at":
            self._field_entry(self.inspector_body, "X", str(args.get("x", 0)),
                              lambda v: self._set_arg(node, "x", self._to_int(v, 0)))
            self._field_entry(self.inspector_body, "Y", str(args.get("y", 0)),
                              lambda v: self._set_arg(node, "y", self._to_int(v, 0)))
            self._field_option(self.inspector_body, "Botón", ["izq", "der"],
                               args.get("button", "izq"),
                               lambda v: self._set_arg(node, "button", v))
        elif a == "press_key":
            self._field_entry(self.inspector_body, "Tecla",
                              args.get("key", "Key.enter"),
                              lambda v: self._set_arg(node, "key", v))
            self._hint("Acepta 'a', 'Key.enter', 'Key.f5', 'vk_65'…")
        elif a == "log":
            self._field_entry(self.inspector_body, "Mensaje",
                              args.get("message", ""),
                              lambda v: self._set_arg(node, "message", v))
            self._field_option(self.inspector_body, "Nivel",
                               ["info", "ok", "warn", "err"],
                               args.get("level", "info"),
                               lambda v: self._set_arg(node, "level", v))

    def _inspector_wait(self, node: FlowNode):
        p = node.params
        self._field_entry(self.inspector_body, "Segundos", str(p.get("seconds", 1.0)),
                          lambda v: self._set_param(node, "seconds", self._to_float(v, 1.0)))

    def _inspector_condition(self, node: FlowNode):
        p = node.params
        cond = p.setdefault("condition", {})
        op = cond.get("op", "image_visible")

        self._field_option(
            self.inspector_body, "Tipo de comprobación",
            ["Imagen visible", "Variable"],
            "Imagen visible" if op == "image_visible" else "Variable",
            lambda label: self._change_condition(node, label),
        )

        if op == "image_visible":
            self._field_entry(self.inspector_body, "Imagen",
                              cond.get("image", ""),
                              lambda v: self._set_cond(node, "image", v),
                              browse_images=True)
            self._field_entry(self.inspector_body, "Confianza (0.1 – 1.0)",
                              str(cond.get("confidence", 0.8)),
                              lambda v: self._set_cond(node, "confidence", self._to_float(v, 0.8)))
            self._field_entry(self.inspector_body, "Esperar hasta (s)",
                              str(cond.get("timeout_s", 3.0)),
                              lambda v: self._set_cond(node, "timeout_s", self._to_float(v, 3.0)))
        elif op == "variable":
            self._field_entry(self.inspector_body, "Variable",
                              cond.get("name", ""),
                              lambda v: self._set_cond(node, "name", v))
            self._field_option(self.inspector_body, "Operador",
                               ["==", "!=", ">", ">=", "<", "<="],
                               cond.get("operator", "=="),
                               lambda v: self._set_cond(node, "operator", v))
            self._field_entry(self.inspector_body, "Valor",
                              str(cond.get("value", 0)),
                              lambda v: self._set_cond(node, "value", self._to_scalar(v)))

        self._hint("Conecta el puerto «Sí» y el puerto «No» a los bloques que deben "
                   "ejecutarse en cada caso.")

    def _inspector_loop(self, node: FlowNode):
        p = node.params
        self._field_entry(self.inspector_body, "Máximo de iteraciones",
                          str(p.get("max_iterations", 5)),
                          lambda v: self._set_param(node, "max_iterations",
                                                    max(1, self._to_int(v, 5))))
        self._field_entry(self.inspector_body, "Variable contador (opcional)",
                          str(p.get("counter_variable", "")),
                          lambda v: self._set_param(node, "counter_variable", v.strip()))
        self._hint("Conecta «Repetir» a los bloques que se repiten y «Salir» al bloque "
                   "que sigue cuando se alcanza el máximo.")

    def _inspector_variable(self, node: FlowNode):
        p = node.params
        self._field_entry(self.inspector_body, "Nombre",
                          p.get("name", ""),
                          lambda v: self._set_param(node, "name", v.strip()))
        self._field_option(self.inspector_body, "Operación",
                           ["set", "increment", "delete"],
                           p.get("operation", "set"),
                           lambda v: self._set_param(node, "operation", v))
        self._field_entry(self.inspector_body, "Valor",
                          str(p.get("value", 0)),
                          lambda v: self._set_param(node, "value", self._to_scalar(v)))

    # ---- Helpers del inspector ----
    def _field_entry(self, parent, label, value, on_change, browse_images: bool = False):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(box, text=label, anchor="w", font=(FONT, 10),
                     text_color=COLORS["text_dim"]).pack(fill="x")

        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", pady=(2, 0))

        var = tk.StringVar(value=str(value))
        styled_entry(row, textvariable=var, height=28).pack(side="left", fill="x", expand=True)

        if browse_images:
            ghost_button(row, "📁", width=34, height=28,
                         command=lambda: self._browse_image(var)).pack(side="left", padx=(6, 0))

        state = {"editing": False}

        def _apply(*_):
            if state["editing"]:
                return
            state["editing"] = True
            try:
                on_change(var.get())
            finally:
                state["editing"] = False

        var.trace_add("write", _apply)
        return var

    def _browse_image(self, var: tk.StringVar):
        assets_dir = ruta_recurso("assets")
        initial = assets_dir if os.path.isdir(assets_dir) else None
        ruta = filedialog.askopenfilename(
            parent=self.editor if self.editor else self,
            title="Seleccionar imagen de referencia",
            initialdir=initial,
            filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.bmp *.gif"),
                       ("PNG", "*.png"), ("Todos los archivos", "*.*")],
        )
        if ruta:
            var.set(os.path.normpath(ruta))

    def _field_option(self, parent, label, values, value, on_change):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(box, text=label, anchor="w", font=(FONT, 10),
                     text_color=COLORS["text_dim"]).pack(fill="x")
        var = tk.StringVar(value=str(value))
        styled_option_menu(box, values=values, variable=var, width=200,
                           command=lambda _v: on_change(var.get())).pack(fill="x", pady=(2, 0))
        return var

    def _hint(self, text):
        ctk.CTkLabel(self.inspector_body, text=text, anchor="w", justify="left",
                     wraplength=240, font=(FONT, 9),
                     text_color=COLORS["text_mute"]).pack(fill="x", pady=(4, 0))

    @staticmethod
    def _to_float(text, default):
        try:
            return float(str(text).replace(",", "."))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_int(text, default):
        try:
            return int(float(str(text).replace(",", ".")))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_scalar(text):
        text = str(text).strip()
        try:
            if "." in text or "e" in text.lower():
                return float(text)
            return int(text)
        except ValueError:
            return text

    # ---- Setters ----
    def _set_name(self, node: FlowNode, value: str):
        node.name = value[:60]
        self.canvas.redraw()

    def _set_param(self, node: FlowNode, key: str, value):
        node.params[key] = value
        self.canvas.redraw()

    def _set_arg(self, node: FlowNode, key: str, value):
        node.params.setdefault("arguments", {})[key] = value
        self.canvas.redraw()

    def _set_cond(self, node: FlowNode, key: str, value):
        node.params.setdefault("condition", {})[key] = value
        self.canvas.redraw()

    @staticmethod
    def _label_para_accion(op):
        return {
            "click_image": "Clic en imagen",
            "click_at": "Clic en coordenadas",
            "press_key": "Pulsar tecla",
            "log": "Registrar mensaje",
        }.get(op, "Clic en imagen")

    def _change_action(self, node: FlowNode, label: str):
        op = {
            "Clic en imagen": "click_image",
            "Clic en coordenadas": "click_at",
            "Pulsar tecla": "press_key",
            "Registrar mensaje": "log",
        }.get(label, "click_image")
        defaults = {
            "click_image": {"image": "", "confidence": 0.8, "timeout_s": 5.0},
            "click_at": {"x": 0, "y": 0, "button": "izq", "clicks": 1},
            "press_key": {"key": "Key.enter"},
            "log": {"message": "Paso completado", "level": "info"},
        }
        node.params["action"] = op
        node.params["arguments"] = dict(defaults[op])
        self.canvas.redraw()
        self._refresh_inspector(node.id)

    def _change_condition(self, node: FlowNode, label: str):
        op = "image_visible" if label == "Imagen visible" else "variable"
        defaults = {
            "image_visible": {"op": "image_visible", "image": "", "confidence": 0.8, "timeout_s": 3.0},
            "variable": {"op": "variable", "name": "contador", "operator": ">=", "value": 1},
        }
        node.params["condition"] = dict(defaults[op])
        self.canvas.redraw()
        self._refresh_inspector(node.id)

    # ------------------------------------------------------------------
    # CONSTRUIR / CARGAR EL FLUJO
    # ------------------------------------------------------------------
    def _build_flow(self) -> Flow:
        nodes = self.canvas.all_nodes()
        if not nodes:
            raise ValueError("El flujo está vacío.")

        for n in nodes.values():
            n.next = None
            n.on_true = None
            n.on_false = None
            n.on_timeout = None
            n.on_error = None
            if n.type != "switch":
                n.branches = {}

        start_id = None
        for n in nodes.values():
            if n.type == "start":
                start_id = n.id
                break
        if start_id is None:
            raise ValueError("Falta un bloque de Inicio.")

        for e in self.canvas.edges():
            f = nodes.get(e["from"])
            if not f or e["to"] not in nodes:
                continue
            port, target = e["port"], e["to"]
            if port == "next":
                f.next = target
            elif port in ("true", "body"):
                f.on_true = target
            elif port in ("false", "exit"):
                f.on_false = target
            elif port.startswith("branch_"):
                f.branches[port] = target
            elif port == "error":
                f.on_error = target
            elif port == "timeout":
                f.on_timeout = target

        target_title = self.target_window.get().strip()
        if target_title == PANTALLA_COMPLETA:
            target_title = ""

        meta = {"positions": self.canvas.node_positions()}
        if target_title:
            meta["target_window"] = target_title
        if self.target_focus.get():
            meta["target_focus"] = True

        flow = Flow(
            name=self.flow_name.get().strip() or "Flujo sin nombre",
            start_node=start_id,
            nodes=list(nodes.values()),
        )
        flow.metadata.update(meta)
        return flow

    def _load_flow_into_canvas(self, flow: Flow):
        self.canvas.clear()
        positions = (flow.metadata or {}).get("positions") or {}
        start_id = flow.start_node

        x, y = 60, 40
        for node in flow.nodes:
            pos = positions.get(node.id)
            if isinstance(pos, (list, tuple)) and len(pos) == 2:
                px, py = int(pos[0]), int(pos[1])
            else:
                px, py = x, y
                y += 90
            self.canvas.add_node(node, px, py)

        for node in flow.nodes:
            if node.next:
                self.canvas.connect(node.id, "next", node.next)
            if node.on_true:
                port = "true" if node.type == "condition" else "body" if node.type == "loop" else "next"
                self.canvas.connect(node.id, port, node.on_true)
            if node.on_false:
                port = "false" if node.type == "condition" else "exit" if node.type == "loop" else "next"
                self.canvas.connect(node.id, port, node.on_false)
            for branch_port, target in (node.branches or {}).items():
                self.canvas.connect(node.id, branch_port, target)

        meta = flow.metadata or {}
        self.target_window.set(meta.get("target_window") or PANTALLA_COMPLETA)
        self.target_focus.set(bool(meta.get("target_focus")))
        self._refresh_target_label()
        if self.editor is not None and self.editor.winfo_exists():
            self.editor._refresh_windows()

        self.canvas.set_selected(start_id)
        self._update_summary()

    # ------------------------------------------------------------------
    # EJECUCIÓN
    # ------------------------------------------------------------------
    def run_flow(self):
        self._ensure_editor()
        if self.worker_thread and self.worker_thread.is_alive():
            return
        try:
            flow = self._build_flow()
            issues = [i for i in validate_flow(flow) if i.severity == "error"]
            if issues:
                raise ValueError("\n".join(f"• {i.message}" for i in issues))
        except Exception as exc:
            messagebox.showerror("Flujo inválido", str(exc),
                                 parent=self.editor if self.editor else self)
            return

        # Resolver la ventana objetivo (si hay una elegida)
        target_title = self.target_window.get().strip()
        if target_title == PANTALLA_COMPLETA:
            target_title = ""
        target_hwnd = None
        if target_title:
            try:
                from vision import hwnd_por_titulo, enfocar_ventana
                target_hwnd = hwnd_por_titulo(target_title)
                if target_hwnd is None:
                    self._log(f"No se encontró la ventana «{target_title}». Se usará toda la pantalla.", "warn")
                elif self.target_focus.get():
                    enfocar_ventana(target_hwnd)
                    self._log(f"Enfocando «{target_title}».", "info")
            except Exception as exc:
                self._log(f"No se pudo preparar la ventana objetivo: {exc}", "warn")

        self.stop_event = threading.Event()
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal", text_color=COLORS["error"])
        self._log(f"Iniciando flujo: {flow.name}", "info")

        self.worker_thread = threading.Thread(
            target=self._run_worker,
            args=(flow, self.stop_event, target_hwnd),
            daemon=True,
        )
        self.worker_thread.start()

    def _run_worker(self, flow: Flow, stop_event: threading.Event, target_hwnd):
        try:
            result = self.service.run(flow, stop_event=stop_event, target_hwnd=target_hwnd)
            self.after(0, self._finish_run, result)
        except Exception as exc:
            self.after(0, self._finish_error, str(exc))

    def _finish_run(self, result):
        self.btn_run.configure(state="normal")
        self.btn_stop.configure(state="disabled", text_color=COLORS["text_dim"])
        self._log(
            f"Resultado: {result.status} · pasos={result.steps} · "
            f"tiempo={result.elapsed_s:.2f}s",
            "ok" if result.status == "completed" else "warn",
        )
        if result.error:
            self._log(f"Error: {result.error}", "err")

    def _finish_error(self, error):
        self.btn_run.configure(state="normal")
        self.btn_stop.configure(state="disabled", text_color=COLORS["text_dim"])
        self._log(f"Error de ejecución: {error}", "err")

    def stop_execution(self):
        self.stop_event.set()
        self._log("Solicitud de detención enviada.", "warn")
        self.btn_stop.configure(state="disabled", text_color=COLORS["text_dim"])

    def stop_from_app(self):
        """Llamado desde main.stop_all() cuando se pulsa Shift+Esc."""
        self.stop_event.set()

    # ------------------------------------------------------------------
    # GUARDAR / ABRIR (carpeta flujos/ del proyecto)
    # ------------------------------------------------------------------
    def _save_dialog(self):
        self._ensure_editor()
        try:
            flow = self._build_flow()
        except Exception as exc:
            messagebox.showerror("Flujo inválido", str(exc),
                                 parent=self.editor if self.editor else self)
            return
        issues = [i for i in validate_flow(flow) if i.severity == "error"]
        if issues:
            messagebox.showerror("Flujo inválido",
                                 "\n".join(f"• {i.message}" for i in issues),
                                 parent=self.editor if self.editor else self)
            return

        os.makedirs(FLOWS_DIR, exist_ok=True)
        initial = flow.name + ".json"
        if self._current_path:
            initial = os.path.basename(self._current_path)

        path = filedialog.asksaveasfilename(
            parent=self.editor if self.editor else self,
            title="Guardar flujo",
            initialdir=FLOWS_DIR,
            defaultextension=".json",
            filetypes=[("Flujos JSON", "*.json")],
            initialfile=initial,
        )
        if not path:
            return
        try:
            self.service.save(flow, path)
            self._current_path = path
            self._update_saved_label()
            self._log(f"Flujo guardado en {path}", "ok")
        except Exception as exc:
            messagebox.showerror("No se pudo guardar", str(exc),
                                 parent=self.editor if self.editor else self)

    def _load_dialog(self):
        self._ensure_editor()
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("Flujos", "Detén la ejecución antes de cargar otro flujo.",
                                   parent=self.editor if self.editor else self)
            return
        os.makedirs(FLOWS_DIR, exist_ok=True)
        path = filedialog.askopenfilename(
            parent=self.editor if self.editor else self,
            title="Abrir flujo",
            initialdir=FLOWS_DIR,
            filetypes=[("Flujos JSON", "*.json"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            flow = self.service.load(path)
            self.flow_name.set(flow.name)
            self._load_flow_into_canvas(flow)
            self._current_path = path
            self._update_saved_label()
            self._log(f"Flujo cargado desde {path}", "ok")
        except Exception as exc:
            messagebox.showerror("No se pudo cargar", str(exc),
                                 parent=self.editor if self.editor else self)

    # ------------------------------------------------------------------
    # EXPORTAR / IMPORTAR (diálogo libre, para compartir)
    # ------------------------------------------------------------------
    def _export_dialog(self):
        self._ensure_editor()
        try:
            flow = self._build_flow()
        except Exception as exc:
            messagebox.showerror("Flujo inválido", str(exc),
                                 parent=self.editor if self.editor else self)
            return
        issues = [i for i in validate_flow(flow) if i.severity == "error"]
        if issues:
            messagebox.showerror("Flujo inválido",
                                 "\n".join(f"• {i.message}" for i in issues),
                                 parent=self.editor if self.editor else self)
            return

        initial = flow.name + ".json"
        path = filedialog.asksaveasfilename(
            parent=self.editor if self.editor else self,
            title="Exportar flujo",
            defaultextension=".json",
            filetypes=[("Flujos JSON", "*.json"), ("Todos", "*.*")],
            initialfile=initial,
        )
        if not path:
            return
        try:
            self.service.save(flow, path)
            self._log(f"Flujo exportado a {path}", "ok")
            self._log("Las imágenes usadas no van dentro del .json: compártelas también si es necesario.", "info")
        except Exception as exc:
            messagebox.showerror("No se pudo exportar", str(exc),
                                 parent=self.editor if self.editor else self)

    def _import_dialog(self):
        self._ensure_editor()
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("Flujos", "Detén la ejecución antes de importar otro flujo.",
                                   parent=self.editor if self.editor else self)
            return
        path = filedialog.askopenfilename(
            parent=self.editor if self.editor else self,
            title="Importar flujo",
            filetypes=[("Flujos JSON", "*.json"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            flow = self.service.load(path)
        except Exception as exc:
            messagebox.showerror("No se pudo importar", str(exc),
                                 parent=self.editor if self.editor else self)
            return

        # Copia automática en flujos/ para tenerlo localizado
        os.makedirs(FLOWS_DIR, exist_ok=True)
        nombre = os.path.splitext(os.path.basename(path))[0]
        destino = os.path.join(FLOWS_DIR, nombre + ".json")
        n = 2
        while os.path.exists(destino) and os.path.abspath(destino) != os.path.abspath(path):
            destino = os.path.join(FLOWS_DIR, f"{nombre} ({n}).json")
            n += 1

        # Si el origen ya está en flujos/, no hacemos copia
        if os.path.abspath(os.path.dirname(path)) != os.path.abspath(FLOWS_DIR):
            try:
                self.service.save(flow, destino)
            except Exception as exc:
                self._log(f"Se cargó el flujo, pero no se pudo copiar a flujos/: {exc}", "warn")

        self.flow_name.set(flow.name)
        self._load_flow_into_canvas(flow)
        self._current_path = destino if os.path.exists(destino) else path
        self._update_saved_label()
        self._log(f"Flujo importado desde {path}", "ok")

    # ------------------------------------------------------------------
    # LOG Y API DE MAIN
    # ------------------------------------------------------------------
    def _log_from_worker(self, message: str, level: str = "info"):
        try:
            self.after(0, self._log, message, level)
        except Exception:
            pass

    def _log(self, message: str, level: str = "info"):
        self._write_log(self.log_box, message, level)
        if self.editor is not None and self.editor.winfo_exists():
            self.editor.write_log(message, level)

    @staticmethod
    def _write_log(textbox, message: str, level: str):
        if textbox is None or not textbox.winfo_exists():
            return
        prefix = {"err": "ERROR", "warn": "AVISO", "ok": "OK", "process": "… "}.get(level, "INFO")
        textbox.configure(state="normal")
        textbox.insert("end", f"[{prefix}] {message}\n")
        textbox.see("end")
        textbox.configure(state="disabled")

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        if self.editor is not None and self.editor.winfo_exists():
            self.editor.clear_log()

    def on_show(self):
        """main._switch_tab lo llama al mostrar esta pestaña."""
        self._ensure_editor()
        self._update_summary()
        self._refresh_target_label()
        if self.canvas is not None:
            self._refresh_inspector(self.canvas.selected_id())


# =====================================================================
# PALETA ARRASTRABLE
# =====================================================================
class PaletteItem:
    """Item de la paleta que se puede arrastrar hasta el lienzo."""

    def __init__(self, parent, label, node_type, params, name, editor: "FlowEditorWindow"):
        self.node_type = node_type
        self.params = params
        self.name = name
        self.editor = editor
        self._ghost: tk.Toplevel | None = None

        self.frame = tk.Frame(parent, bg=COLORS["card_alt"], height=30, cursor="hand2")
        self.frame.pack(fill="x", pady=2)
        self.frame.pack_propagate(False)

        self.label = tk.Label(
            self.frame, text=label, bg=COLORS["card_alt"], fg=COLORS["text"],
            font=(FONT, 10), anchor="w", padx=10, cursor="hand2")
        self.label.pack(fill="both", expand=True)

        self.frame.bind("<Enter>", self._on_enter)
        self.frame.bind("<Leave>", self._on_leave)
        for w in (self.frame, self.label):
            w.bind("<ButtonPress-1>", self._on_press)
            w.bind("<B1-Motion>", self._on_motion)
            w.bind("<ButtonRelease-1>", self._on_release)

    def _set_bg(self, color):
        try:
            self.frame.configure(bg=color)
            self.label.configure(bg=color)
        except Exception:
            pass

    def _on_enter(self, _e):
        self._set_bg(COLORS["border"])

    def _on_leave(self, _e):
        self._set_bg(COLORS["card_alt"])

    def _on_press(self, event):
        self._ghost = tk.Toplevel(self.frame)
        self._ghost.overrideredirect(True)
        try:
            self._ghost.attributes("-topmost", True)
            self._ghost.attributes("-alpha", 0.9)
        except Exception:
            pass
        tk.Label(self._ghost, text=self.label.cget("text"),
                 bg=COLORS["accent"], fg="#FFFFFF",
                 font=(FONT, 10, "bold"), padx=12, pady=6).pack()
        self._move(event.x_root, event.y_root)

    def _on_motion(self, event):
        if self._ghost is not None:
            self._move(event.x_root, event.y_root)

    def _on_release(self, event):
        ghost = self._ghost
        self._ghost = None
        if ghost is not None:
            try:
                ghost.destroy()
            except Exception:
                pass

        canvas = self.editor.tab.canvas
        if canvas is None or not canvas.winfo_exists():
            return

        cx = canvas.winfo_rootx()
        cy = canvas.winfo_rooty()
        cw = canvas.winfo_width()
        ch = canvas.winfo_height()
        if cx <= event.x_root <= cx + cw and cy <= event.y_root <= cy + ch:
            self.editor.tab._add_node(
                self.node_type, self.params, self.name,
                x_root=event.x_root, y_root=event.y_root,
            )

    def _move(self, x_root, y_root):
        if self._ghost is None:
            return
        try:
            self._ghost.geometry(f"+{x_root + 12}+{y_root + 12}")
        except Exception:
            pass


# =====================================================================
# VENTANA FLOTANTE DEL EDITOR
# =====================================================================
class FlowEditorWindow(ctk.CTkToplevel):
    """Ventana flotante con la paleta, el lienzo, el inspector y un log pequeño.

    Se crea una sola vez; cerrarla solo la oculta (withdraw), así no se pierde
    el estado del lienzo ni los widgets del inspector.
    """

    def __init__(self, master, tab: TabFlujos):
        super().__init__(master)
        self.tab = tab
        self._visible = False

        self.title("Editor de flujo")
        self.geometry("1220x780")
        self.minsize(940, 600)
        self.configure(fg_color=COLORS["bg"])
        self.transient(master)
        self.withdraw()

        self.canvas: FlowCanvas | None = None
        self.inspector_body: ctk.CTkScrollableFrame | None = None

        self._build_ui()

        self.protocol("WM_DELETE_WINDOW", self.hide)
        self.bind("<Escape>", lambda _e: self.hide())
        self.after(300, self._ensure_hidden)

    # ------------------------------------------------------------------
    # VISIBILIDAD
    # ------------------------------------------------------------------
    def show(self):
        self._visible = True
        self.deiconify()
        self.lift()
        self.focus_force()

    def hide(self):
        self._visible = False
        self.withdraw()

    def _ensure_hidden(self):
        if not self._visible and self.winfo_exists():
            self.withdraw()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        self._build_toolbar()

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=14, pady=(8, 0))
        main.grid_columnconfigure(0, weight=0)
        main.grid_columnconfigure(1, weight=1)
        main.grid_columnconfigure(2, weight=0)
        main.grid_rowconfigure(0, weight=1)

        self._build_palette(main).grid(row=0, column=0, sticky="nsw", padx=(0, 8))
        self._build_canvas(main).grid(row=0, column=1, sticky="nsew")
        self._build_right_panel(main).grid(row=0, column=2, sticky="nse", padx=(8, 0))

        self._build_log()

    def _build_toolbar(self):
        bar = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=12,
                           border_width=1, border_color=COLORS["border_soft"])
        bar.pack(fill="x", padx=14, pady=(14, 0))

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(inner, text="Nombre:", font=(FONT, 11, "bold"),
                     text_color=COLORS["text_dim"]).pack(side="left", padx=(0, 8))
        styled_entry(inner, textvariable=self.tab.flow_name, width=220, height=30).pack(side="left")

        zoom_box = ctk.CTkFrame(inner, fg_color=COLORS["card_alt"], corner_radius=6)
        zoom_box.pack(side="right", padx=(8, 0))
        ghost_button(zoom_box, "−", command=self._zoom_out,
                     width=26, height=26).pack(side="left", padx=(2, 0))
        self.lbl_zoom = ctk.CTkLabel(zoom_box, text="100%", width=48,
                                     font=(FONT, 10), text_color=COLORS["text_dim"])
        self.lbl_zoom.pack(side="left")
        ghost_button(zoom_box, "+", command=self._zoom_in,
                     width=26, height=26).pack(side="left", padx=(0, 2))
        ghost_button(zoom_box, "⟲", command=self._zoom_reset,
                     width=26, height=26).pack(side="left", padx=(0, 2))

        ghost_button(inner, "💾 Guardar", command=self.tab._save_dialog,
                     width=96, height=30).pack(side="right", padx=(0, 6))
        ghost_button(inner, "📂 Abrir", command=self.tab._load_dialog,
                     width=96, height=30).pack(side="right", padx=(0, 6))
        ghost_button(inner, "🗑️ Nuevo", command=self.tab._confirm_new,
                     width=96, height=30).pack(side="right", padx=(0, 6))

        self.btn_run = ctk.CTkButton(
            inner, text="▶  Ejecutar", command=self.tab.run_flow,
            width=110, height=30, corner_radius=8,
            fg_color=COLORS["success"], hover_color="#16A34A",
            text_color="#FFFFFF", font=(FONT, 11, "bold"))
        self.btn_run.pack(side="right", padx=(0, 6))

    def _build_palette(self, parent):
        card = Card(parent, title="Bloques")
        card.configure(width=210)
        body = card.body
        body.configure(width=178)

        ctk.CTkLabel(body, text="Arrastra al lienzo →",
                     anchor="w", font=(FONT, 9, "bold"),
                     text_color=COLORS["text_mute"]).pack(fill="x", pady=(0, 6))

        for label, tipo, params, nombre, _pos in PALETA:
            PaletteItem(body, label, tipo, params, nombre, self)

        ctk.CTkFrame(body, height=1, fg_color=COLORS["border_soft"]).pack(fill="x", pady=10)
        ctk.CTkLabel(
            body,
            text="Conectar: clic en un puerto de salida y luego clic en la entrada destino "
                 "del otro bloque. También vale arrastrar del puerto a la entrada.\n\n"
                 "Rueda = desplazar.  Botón central = panear.  Ctrl+rueda = zoom.",
            anchor="w", justify="left", wraplength=176,
            font=(FONT, 9), text_color=COLORS["text_mute"],
        ).pack(fill="x")
        return card

    def _build_canvas(self, parent):
        wrap = ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=12,
                            border_width=1, border_color=COLORS["border_soft"])
        inner = ctk.CTkFrame(wrap, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=6, pady=6)

        self.canvas = FlowCanvas(
            inner,
            on_select=self.tab._on_canvas_select,
            on_change=self.tab._on_canvas_change,
            on_zoom=self._on_zoom,
            bg=COLORS["console"],
        )
        self.canvas.pack(fill="both", expand=True)
        return wrap

    def _build_right_panel(self, parent):
        cont = ctk.CTkFrame(parent, fg_color="transparent", width=300)
        cont.configure(width=300)
        cont.grid_columnconfigure(0, weight=1)
        cont.grid_rowconfigure(1, weight=1)

        # --- Tarjeta: Ventana objetivo ---
        wcard = Card(cont, title="Ventana objetivo")
        wcard.grid(row=0, column=0, sticky="ew")
        wbody = wcard.body

        f_row = ctk.CTkFrame(wbody, fg_color="transparent")
        f_row.pack(fill="x")
        self.combo_windows = styled_option_menu(
            f_row, [PANTALLA_COMPLETA], variable=self.tab.target_window, width=180)
        self.combo_windows.pack(side="left", fill="x", expand=True)
        ghost_button(f_row, "⟳", command=self._refresh_windows,
                     width=32, height=28).pack(side="left", padx=(6, 0))

        f_row2 = ctk.CTkFrame(wbody, fg_color="transparent")
        f_row2.pack(fill="x", pady=(10, 0))
        ghost_button(f_row2, "Enfocar ahora", command=self._focus_target_now,
                     width=120, height=26).pack(side="left")
        ctk.CTkCheckBox(
            f_row2, text="Enfocar al ejecutar",
            variable=self.tab.target_focus,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            border_color=COLORS["border"], text_color=COLORS["text"],
            font=(FONT, 10), checkbox_width=16, checkbox_height=16,
        ).pack(side="left", padx=(12, 0))

        ctk.CTkLabel(
            wbody, text="Si eliges una ventana, las imágenes se buscan solo ahí y los clics "
                        "se calculan respecto a su origen. «Toda la pantalla» usa el escritorio completo.",
            anchor="w", justify="left", wraplength=256,
            font=(FONT, 9), text_color=COLORS["text_mute"],
        ).pack(fill="x", pady=(10, 0))

        # --- Tarjeta: Inspector ---
        card = Card(cont, title="Inspector")
        card.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        body = card.body
        self.inspector_body = ctk.CTkScrollableFrame(
            body, fg_color="transparent", width=258, height=340,
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["accent"],
        )
        self.inspector_body.pack(fill="both", expand=True)

        # Al abrir, rellenar el combo
        self.after(200, self._refresh_windows)
        return cont

    def _refresh_windows(self):
        """Rellena el combo con las ventanas visibles del sistema (excluye la app)."""
        try:
            from vision import listar_ventanas_visibles
            ventanas = listar_ventanas_visibles()
        except Exception:
            ventanas = []

        try:
            titulo_app = self.tab.app_ref.title()
        except Exception:
            titulo_app = ""

        titulos = [t for _h, t in ventanas if t != titulo_app]
        titulos.sort(key=str.lower)

        valores = [PANTALLA_COMPLETA] + titulos
        self.combo_windows.configure(values=valores)

        actual = self.tab.target_window.get().strip()
        if not actual:
            self.tab.target_window.set(PANTALLA_COMPLETA)
        elif actual not in valores:
            # La ventana ya no existe: volver al default
            self.tab.target_window.set(PANTALLA_COMPLETA)
            self.tab._refresh_target_label()
            self.write_log("La ventana seleccionada ya no está abierta. Se usará toda la pantalla.", "warn")

    def _focus_target_now(self):
        titulo = self.tab.target_window.get().strip()
        if not titulo or titulo == PANTALLA_COMPLETA:
            self.write_log("Selecciona una ventana primero.", "warn")
            return
        try:
            from vision import hwnd_por_titulo, enfocar_ventana
            hwnd = hwnd_por_titulo(titulo)
            if hwnd and enfocar_ventana(hwnd):
                self.write_log(f"Ventana «{titulo}» traída al frente.", "ok")
            else:
                self.write_log(f"No se pudo enfocar «{titulo}».", "warn")
        except Exception as exc:
            self.write_log(f"Error al enfocar: {exc}", "err")

    def _build_log(self):
        wrap = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=12,
                            border_width=1, border_color=COLORS["border_soft"])
        wrap.pack(fill="x", padx=14, pady=(8, 14))

        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(6, 2))
        ctk.CTkLabel(head, text="Registro", font=(FONT, 11, "bold"),
                     text_color=COLORS["accent_text"]).pack(side="left")

        self.log_box = ctk.CTkTextbox(
            wrap, height=80, fg_color=COLORS["console"], text_color=COLORS["text_dim"],
            border_width=0, corner_radius=8, font=("Consolas", 10), wrap="word")
        self.log_box.pack(fill="x", padx=12, pady=(0, 10))
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------
    # ZOOM
    # ------------------------------------------------------------------
    def _zoom_in(self):
        if self.canvas:
            self.canvas.zoom_in()

    def _zoom_out(self):
        if self.canvas:
            self.canvas.zoom_out()

    def _zoom_reset(self):
        if self.canvas:
            self.canvas.fit_all()

    def _on_zoom(self, zoom: float):
        if hasattr(self, "lbl_zoom") and self.lbl_zoom.winfo_exists():
            self.lbl_zoom.configure(text=f"{int(round(zoom * 100))}%")

    # ------------------------------------------------------------------
    # LOG
    # ------------------------------------------------------------------
    def write_log(self, message: str, level: str = "info"):
        TabFlujos._write_log(self.log_box, message, level)

    def clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")