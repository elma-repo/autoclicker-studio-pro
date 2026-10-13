"""Lienzo de bloques conectados para el editor visual de flujos.

Es un tk.Canvas (no CustomTkinter) porque CustomTkinter no expone primitivas de dibujo
libres. El resto de la app sigue usando CustomTkinter.

Interacción:
  • Clic en un puerto de salida  → queda pendiente la conexión.
    - Mueve el ratón: la línea sigue al cursor (sin pulsar nada).
    - Clic en la entrada de otro bloque: conecta.
    - Clic en otro puerto de salida: cambia el origen.
    - Clic en zona vacía / clic derecho / Esc: cancela.
  • Arrastrar desde un puerto de salida y soltar sobre la entrada: también conecta.
  • Botón central del ratón (rueda presionada): paneo omnidireccional.
  • Rueda del ratón: desplazamiento vertical (Shift = horizontal).
  • Ctrl+rueda: zoom.
"""
from __future__ import annotations

import os
import tkinter as tk
from typing import Callable

from logic_engine.flow_model import FlowNode

NODE_W, NODE_H = 190, 70
PORT_R = 5
PORT_HIT = 14

# Zoom
ZOOM_MIN = 0.4
ZOOM_MAX = 2.5
ZOOM_STEP = 1.15

# Cuánto hay que mover el ratón entre pulsar y soltar para considerarlo "arrastre"
DRAG_PX2 = 36          # 6 px al cuadrado

PORTS_POR_TIPO: dict[str, tuple[str, ...]] = {
    "start":        ("next",),
    "end":          (),
    "action":       ("next",),
    "wait":         ("next",),
    "set_variable": ("next",),
    "condition":    ("true", "false"),
    "loop":         ("body", "exit"),
    "switch":       ("branch_1", "branch_2", "branch_3"),
}

ETIQUETA_PUERTO = {
    "next": "", "true": "Sí", "false": "No",
    "body": "Repetir", "exit": "Salir",
    "branch_1": "Caso 1", "branch_2": "Caso 2", "branch_3": "Caso 3",
}

COLOR_PUERTO = {
    "next": "#A855F7", "true": "#22C55E", "false": "#EF4444",
    "body": "#A855F7", "exit": "#71717A",
    "branch_1": "#3B82F6", "branch_2": "#EAB308", "branch_3": "#EC4899",
}

ESTILO_NODO = {
    "start":        {"fill": "#0F2A1A", "border": "#22C55E", "title": "#DCFCE7", "badge": "#22C55E", "label": "INICIO"},
    "end":          {"fill": "#2A0F0F", "border": "#EF4444", "title": "#FEE2E2", "badge": "#EF4444", "label": "FIN"},
    "action":       {"fill": "#1A1533", "border": "#7C3AED", "title": "#EDE9FE", "badge": "#A78BFA", "label": "ACCIÓN"},
    "condition":    {"fill": "#2A1F0A", "border": "#EAB308", "title": "#FEF3C7", "badge": "#EAB308", "label": "SI"},
    "wait":         {"fill": "#0A1A2E", "border": "#3B82F6", "title": "#DBEAFE", "badge": "#60A5FA", "label": "ESPERA"},
    "loop":         {"fill": "#1E0F33", "border": "#A855F7", "title": "#F3E8FF", "badge": "#A855F7", "label": "BUCLE"},
    "set_variable": {"fill": "#0A1E1C", "border": "#14B8A6", "title": "#CCFBF1", "badge": "#14B8A6", "label": "VARIABLE"},
    "switch":       {"fill": "#200B3A", "border": "#C084FC", "title": "#F3E8FF", "badge": "#C084FC", "label": "CASO"},
}


class FlowCanvas(tk.Canvas):
    """Canvas con nodos arrastrables, conexiones por puertos y paneo con botón central."""

    def __init__(self, master,
                 on_select: Callable[[str | None], None] | None = None,
                 on_change: Callable[[], None] | None = None,
                 on_zoom: Callable[[float], None] | None = None,
                 bg: str = "#101014"):
        super().__init__(master, bg=bg, highlightthickness=0, bd=0)
        self._on_select = on_select
        self._on_change = on_change
        self._on_zoom = on_zoom

        self._nodes: dict[str, dict] = {}
        self._edges: list[dict] = []
        self._selected: str | None = None

        self._drag_id: str | None = None
        self._drag_dx = 0.0
        self._drag_dy = 0.0
        self._drag_moved = False

        # Conexión pendiente (modo clic-clic o arrastre)
        self._connect_from: tuple[str, str] | None = None
        self._connect_cursor: tuple[int, int] = (0, 0)
        self._connect_press_pos: tuple[float, float] | None = None
        self._drag_from_port = False

        self._port_hits: list[tuple[int, int, str, str, bool]] = []
        self._node_hits: dict[str, tuple[int, int, int, int]] = {}

        self._zoom = 1.0
        self._panning = False

        self.configure(scrollregion=(0, 0, 4000, 4000))

        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Motion>", self._on_motion)
        self.bind("<ButtonPress-3>", self._on_right)
        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Shift-MouseWheel>", self._on_wheel_h)
        self.bind("<Control-MouseWheel>", self._on_ctrl_wheel)
        # Paneo con botón central del ratón
        self.bind("<ButtonPress-2>", self._on_mb_press)
        self.bind("<B2-Motion>", self._on_mb_drag)
        self.bind("<ButtonRelease-2>", self._on_mb_release)
        # Esc cancela la conexión pendiente
        self.bind("<Escape>", lambda _e: self._cancel_pending())
        self.configure(takefocus=1)

    # ---- Zoom ---------------------------------------------------------

    @property
    def zoom(self) -> float:
        return self._zoom

    def zoom_in(self):
        self._set_zoom(self._zoom * ZOOM_STEP)

    def zoom_out(self):
        self._set_zoom(self._zoom / ZOOM_STEP)

    def zoom_reset(self):
        self._set_zoom(1.0)

    def fit_all(self):
        """Vuelve al 100 % y recoloca la vista al origen del contenido."""
        self._set_zoom(1.0)
        if not self._nodes:
            self.configure(scrollregion=(0, 0, 4000, 4000))
        else:
            xs = [d["x"] for d in self._nodes.values()]
            ys = [d["y"] for d in self._nodes.values()]
            x0 = max(0, int(min(xs)) - 40)
            y0 = max(0, int(min(ys)) - 40)
            x1 = int(max(xs)) + NODE_W + 40
            y1 = int(max(ys)) + NODE_H + 40
            self.configure(scrollregion=(x0, y0, x1, y1))
        self.xview_moveto(0)
        self.yview_moveto(0)

    def _set_zoom(self, value: float):
        value = max(ZOOM_MIN, min(ZOOM_MAX, float(value)))
        if abs(value - self._zoom) < 1e-3:
            return
        self._zoom = value
        self.redraw()
        if self._on_zoom:
            self._on_zoom(self._zoom)

    # ---- API ----------------------------------------------------------

    def add_node(self, node: FlowNode, x: int, y: int):
        self._nodes[node.id] = {"x": int(x), "y": int(y), "node": node}
        self.redraw()
        self._changed()

    def remove_node(self, node_id: str):
        if node_id not in self._nodes:
            return
        self._nodes.pop(node_id, None)
        self._edges = [e for e in self._edges if e["from"] != node_id and e["to"] != node_id]
        if self._selected == node_id:
            self._selected = None
            if self._on_select:
                self._on_select(None)
        self.redraw()
        self._changed()

    def set_selected(self, node_id: str | None):
        if self._selected == node_id:
            return
        self._selected = node_id if node_id in self._nodes else None
        self.redraw()
        if self._on_select:
            self._on_select(self._selected)

    def get_node(self, node_id: str) -> FlowNode | None:
        d = self._nodes.get(node_id)
        return d["node"] if d else None

    def all_nodes(self) -> dict[str, FlowNode]:
        return {nid: d["node"] for nid, d in self._nodes.items()}

    def selected_id(self) -> str | None:
        return self._selected

    def node_positions(self) -> dict[str, tuple[int, int]]:
        return {nid: (int(d["x"]), int(d["y"])) for nid, d in self._nodes.items()}

    def edges(self) -> list[dict]:
        return [dict(e) for e in self._edges]

    def connect(self, from_id: str, port: str, to_id: str) -> bool:
        if not from_id or not to_id or from_id == to_id:
            return False
        self._edges = [e for e in self._edges if not (e["from"] == from_id and e["port"] == port)]
        self._edges.append({"from": from_id, "port": port, "to": to_id})
        self.redraw()
        self._changed()
        return True

    def free_port(self, node_id: str) -> str | None:
        d = self._nodes.get(node_id)
        if not d:
            return None
        ports = PORTS_POR_TIPO.get(d["node"].type, ())
        used = {e["port"] for e in self._edges if e["from"] == node_id}
        for p in ports:
            if p not in used:
                return p
        return None

    def free_spot(self, near_id: str | None, prefer: str = "down") -> tuple[int, int]:
        if near_id and near_id in self._nodes:
            x, y = self._nodes[near_id]["x"], self._nodes[near_id]["y"]
            if prefer == "right":
                return x + NODE_W + 60, y
            if prefer == "left":
                return max(20, x - NODE_W - 60), y
            return x, y + NODE_H + 50
        used = {(d["x"], d["y"]) for d in self._nodes.values()}
        x, y = 60, 60
        for _ in range(60):
            if (x, y) not in used:
                return x, y
            y += NODE_H + 50
        return x, y

    def screen_to_logical(self, x_root: int, y_root: int) -> tuple[int, int]:
        """Coordenadas absolutas de pantalla → coordenadas lógicas (sin scroll ni zoom).

        Se usa al soltar un bloque arrastrado desde la paleta.
        """
        x_local = x_root - self.winfo_rootx()
        y_local = y_root - self.winfo_rooty()
        z = self._zoom if self._zoom > 0 else 1.0
        return int(self.canvasx(x_local) / z), int(self.canvasy(y_local) / z)

    def clear(self):
        self._nodes.clear()
        self._edges.clear()
        self._selected = None
        self._connect_from = None
        self._drag_from_port = False
        self._connect_press_pos = None
        self.redraw()

    # ---- Dibujo -------------------------------------------------------

    def redraw(self):
        self.delete("all")
        self._port_hits.clear()
        self._node_hits.clear()

        for edge in self._edges:
            self._draw_edge(edge)
        for nid, d in self._nodes.items():
            self._draw_node(nid, d)

        if self._connect_from is not None:
            pa = self._port_pos(*self._connect_from)
            if pa:
                cx, cy = self._connect_cursor
                self.create_line(
                    pa[0], pa[1], cx, cy,
                    fill=COLOR_PUERTO.get(self._connect_from[1], "#A855F7"),
                    width=2, dash=(4, 3), tags="temp_line",
                )

    def _update_temp_line(self):
        """Actualiza solo la línea punteada pendiente (sin redibujar todo)."""
        if self._connect_from is None:
            return
        pa = self._port_pos(*self._connect_from)
        if pa is None:
            return
        cx, cy = self._connect_cursor
        color = COLOR_PUERTO.get(self._connect_from[1], "#A855F7")
        if self.find_withtag("temp_line"):
            self.coords("temp_line", pa[0], pa[1], cx, cy)
        else:
            self.create_line(pa[0], pa[1], cx, cy, fill=color,
                             width=2, dash=(4, 3), tags="temp_line")

    def _draw_node(self, nid: str, d: dict):
        node: FlowNode = d["node"]
        z = self._zoom
        x, y = int(round(d["x"] * z)), int(round(d["y"] * z))
        w, h = int(round(NODE_W * z)), int(round(NODE_H * z))
        x2, y2 = x + w, y + h
        style = ESTILO_NODO.get(node.type, ESTILO_NODO["action"])
        selected = (nid == self._selected)

        border = "#FFFFFF" if selected else style["border"]
        width = 2 if selected else 1
        radius = max(4, int(12 * z))
        self._round_rect(x, y, x2, y2, radius, fill=style["fill"], outline=border, width=width)

        base_font = max(6, int(round(10 * z)))
        font_badge = ("Segoe UI", max(5, base_font - 3), "bold")
        font_title = ("Segoe UI", base_font, "bold")
        font_sub = ("Segoe UI", max(5, base_font - 2))

        self.create_text(x + int(12 * z), y + int(12 * z), anchor="w",
                         text=style["label"], fill=style["badge"], font=font_badge)
        title = node.name or node.id or node.type
        self.create_text(x + int(12 * z), y + int(30 * z), anchor="w",
                         text=self._fit(title, 24), fill=style["title"], font=font_title)
        sub = self._summary(node)
        if sub:
            self.create_text(x + int(12 * z), y + int(50 * z), anchor="w",
                             text=self._fit(sub, 30), fill=style["title"], font=font_sub)

        self._node_hits[nid] = (x, y, w, h)

        r = max(3, int(round(PORT_R * z)))
        ports = PORTS_POR_TIPO.get(node.type, ())
        if node.type != "start":
            cx = x + w // 2
            self._draw_port(cx, y, "#A1A1AA", r)
            self._port_hits.append((cx, y, nid, "__in__", True))

        n = len(ports)
        for i, port in enumerate(ports):
            cx = x + int(w * (i + 1) / (n + 1))
            color = COLOR_PUERTO.get(port, "#A855F7")
            self._draw_port(cx, y2, color, r)
            self._port_hits.append((cx, y2, nid, port, False))
            label = ETIQUETA_PUERTO.get(port, "")
            if label:
                self.create_text(cx, y2 + int(12 * z), text=label, fill=color,
                                 font=font_badge, anchor="n")

    def _draw_port(self, cx, cy, color, r):
        self.create_oval(cx - r, cy - r, cx + r, cy + r,
                         fill=color, outline="#0F0F12", width=1)

    def _draw_edge(self, edge: dict):
        pa = self._port_pos(edge["from"], edge["port"])
        pb = self._port_pos(edge["to"], "__in__")
        if pa is None or pb is None:
            return
        color = COLOR_PUERTO.get(edge["port"], "#A855F7")
        x0, y0 = pa
        x1, y1 = pb
        dy = max(int(30 * self._zoom), abs(y1 - y0) * 0.4)
        self.create_line(
            x0, y0, x0, y0 + dy, x1, y1 - dy, x1, y1,
            smooth=True, splinesteps=18, fill=color, width=2, capstyle="round",
        )
        arrow = max(4, int(5 * self._zoom))
        self.create_polygon(x1, y1, x1 - arrow, y1 - arrow - 3, x1 + arrow, y1 - arrow - 3,
                            fill=color, outline=color)

    def _port_pos(self, nid: str, port: str) -> tuple[int, int] | None:
        d = self._nodes.get(nid)
        if not d:
            return None
        node: FlowNode = d["node"]
        z = self._zoom
        x, y = int(round(d["x"] * z)), int(round(d["y"] * z))
        w, h = int(round(NODE_W * z)), int(round(NODE_H * z))
        if port == "__in__":
            return x + w // 2, y
        ports = PORTS_POR_TIPO.get(node.type, ())
        if port not in ports:
            return None
        i = ports.index(port)
        n = len(ports)
        return x + int(w * (i + 1) / (n + 1)), y + h

    def _round_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    @staticmethod
    def _fit(text: str, max_chars: int) -> str:
        text = str(text)
        return text if len(text) <= max_chars else text[:max_chars - 1] + "…"

    def _summary(self, node: FlowNode) -> str:
        p = node.params or {}
        if node.type == "action":
            a = p.get("action", "")
            args = p.get("arguments") or {}
            if a == "click_image":
                return "Ver imagen y hacer clic"
            if a == "click_at":
                return f"({args.get('x', '?')}, {args.get('y', '?')})"
            if a == "press_key":
                return f"Tecla {args.get('key', '?')}"
            if a == "log":
                return str(args.get("message", ""))[:30]
            return str(a)
        if node.type == "wait":
            return f"{p.get('seconds', 0)} s"
        if node.type == "condition":
            cond = p.get("condition") or {}
            op = cond.get("op", "")
            if op == "image_visible":
                img = str(cond.get("image") or "")
                return f"¿{os.path.basename(img) or 'imagen'}?"
            if op == "variable":
                return f"{cond.get('name', '?')} {cond.get('operator', '==')}"
            return str(op)
        if node.type == "loop":
            return f"Hasta {p.get('max_iterations', '?')} veces"
        if node.type == "set_variable":
            return f"{p.get('name', '?')} ← {p.get('value', '?')}"
        if node.type == "switch":
            return str(p.get("value", ""))[:30]
        return ""

    # ---- Interacción --------------------------------------------------

    def _to_canvas(self, event) -> tuple[float, float]:
        """Coordenadas del evento en el espacio del canvas (con scroll aplicado)."""
        return self.canvasx(event.x), self.canvasy(event.y)

    def _find_port_at(self, x, y):
        best, best_d = None, PORT_HIT * PORT_HIT
        for (px, py, nid, port, is_in) in self._port_hits:
            d = (px - x) ** 2 + (py - y) ** 2
            if d < best_d:
                best_d, best = d, (nid, port, is_in)
        return best

    def _find_node_at(self, x, y):
        for nid in reversed(list(self._node_hits.keys())):
            nx, ny, nw, nh = self._node_hits[nid]
            if nx <= x <= nx + nw and ny <= y <= ny + nh:
                return nid
        return None

    def _cancel_pending(self):
        if self._connect_from is None:
            return
        self._connect_from = None
        self._drag_from_port = False
        self._connect_press_pos = None
        self.configure(cursor="")
        self.redraw()

    def _on_press(self, event):
        # Para poder recibir Esc, pedimos el foco al pulsar dentro del lienzo
        self.focus_set()

        cx, cy = self._to_canvas(event)

        # 1) ¿Hay una conexión pendiente esperando destino?
        if self._connect_from is not None:
            port = self._find_port_at(cx, cy)
            if port:
                nid, pname, is_in = port
                if is_in:
                    if nid != self._connect_from[0]:
                        src_id, src_port = self._connect_from
                        self._connect_from = None
                        self._drag_from_port = False
                        self.connect(src_id, src_port, nid)
                    else:
                        self._cancel_pending()
                    return
                # Otro puerto de salida: cambiamos el origen
                self._connect_from = (nid, pname)
                self._connect_cursor = (int(cx), int(cy))
                self._connect_press_pos = (cx, cy)
                self._drag_from_port = True
                self.redraw()
                return
            # Clic en zona vacía o en un nodo (sin puerto): cancelar la pendiente
            self._cancel_pending()

        # 2) Comportamiento normal
        port = self._find_port_at(cx, cy)
        if port:
            nid, pname, is_in = port
            if is_in:
                # Clic sobre la entrada: desconecta lo que llega
                before = len(self._edges)
                self._edges = [e for e in self._edges if e["to"] != nid]
                if len(self._edges) != before:
                    self.redraw()
                    self._changed()
                return
            # Puerto de salida: iniciar conexión pendiente (clic-clic) / arrastre
            self._connect_from = (nid, pname)
            self._connect_cursor = (int(cx), int(cy))
            self._connect_press_pos = (cx, cy)
            self._drag_from_port = True
            self.redraw()
            return

        nid = self._find_node_at(cx, cy)
        if nid:
            self.set_selected(nid)
            d = self._nodes[nid]
            self._drag_id = nid
            self._drag_dx = (cx / self._zoom) - d["x"]
            self._drag_dy = (cy / self._zoom) - d["y"]
            self._drag_moved = False
            return

        self.set_selected(None)

    def _on_drag(self, event):
        cx, cy = self._to_canvas(event)
        if self._connect_from is not None:
            self._connect_cursor = (int(cx), int(cy))
            self._update_temp_line()
            return
        if self._drag_id is not None:
            d = self._nodes[self._drag_id]
            nx = max(0.0, (cx / self._zoom) - self._drag_dx)
            ny = max(0.0, (cy / self._zoom) - self._drag_dy)
            if abs(nx - d["x"]) > 1 or abs(ny - d["y"]) > 1:
                self._drag_moved = True
            d["x"], d["y"] = nx, ny
            self.redraw()

    def _on_release(self, event):
        cx, cy = self._to_canvas(event)

        # ¿Estábamos conectando desde un puerto?
        if self._connect_from is not None and self._drag_from_port:
            press = self._connect_press_pos
            if press is not None:
                dx = cx - press[0]
                dy = cy - press[1]
                moved = (dx * dx + dy * dy) > DRAG_PX2
                self._connect_press_pos = None

                if moved:
                    # Fue un arrastre: intentamos cerrar la conexión aquí
                    target = self._find_port_at(cx, cy)
                    if target and target[2] and target[0] != self._connect_from[0]:
                        src_id, src_port = self._connect_from
                        self._connect_from = None
                        self._drag_from_port = False
                        self.connect(src_id, src_port, target[0])
                        return
                    # Arrastró pero soltó en vacío o sobre otra salida: cancelar
                    self._cancel_pending()
                    return
                # No se movió: fue un clic → dejamos la conexión pendiente para
                # que el siguiente clic (en la entrada destino) la cierre.
            return

        if self._drag_id is not None:
            if self._drag_moved:
                self._changed()
            self._drag_id = None
            self._drag_moved = False

    def _on_motion(self, event):
        """Cuando hay conexión pendiente, la línea sigue al cursor aunque no se pulse nada."""
        cx, cy = self._to_canvas(event)
        if self._connect_from is not None:
            self._connect_cursor = (int(cx), int(cy))
            self._update_temp_line()
            return
        # Feedback de cursor: manita cuando se pasa por un puerto de salida
        port = self._find_port_at(cx, cy)
        if port and not port[2]:
            self.configure(cursor="hand2")
        else:
            self.configure(cursor="")

    def _on_right(self, event):
        if self._connect_from is not None:
            self._cancel_pending()
            return
        cx, cy = self._to_canvas(event)
        nid = self._find_node_at(cx, cy)
        self.set_selected(nid)

    # ---- Rueda y paneo con botón central ------------------------------

    def _on_wheel(self, event):
        self.yview_scroll(int(-1 * (event.delta / 120)) * 2, "units")

    def _on_wheel_h(self, event):
        self.xview_scroll(int(-1 * (event.delta / 120)) * 2, "units")

    def _on_ctrl_wheel(self, event):
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()
        return "break"

    def _on_mb_press(self, event):
        """Botón central pulsado: empezamos a panear."""
        self._panning = True
        self.configure(cursor="fleur")
        self.scan_mark(event.x, event.y)

    def _on_mb_drag(self, event):
        if self._panning:
            self.scan_dragto(event.x, event.y, gain=1)

    def _on_mb_release(self, event):
        self._panning = False
        self.configure(cursor="")

    def _changed(self):
        if self._on_change:
            self._on_change()