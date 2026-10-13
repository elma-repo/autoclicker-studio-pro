"""Modelo serializable de un flujo de automatización (formato JSON versionado)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

FLOW_FORMAT = "AutoClickerStudio_Flow"
FLOW_VERSION = 1

@dataclass
class FlowNode:
    id: str
    type: str
    name: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    next: str | None = None
    on_true: str | None = None
    on_false: str | None = None
    on_timeout: str | None = None
    on_error: str | None = None
    # Para nodos tipo switch: {"valor": "node_id", ...}
    branches: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FlowNode":
        if not isinstance(data, dict):
            raise ValueError("Cada nodo debe ser un objeto JSON.")
        return cls(
            id=str(data.get("id", "")).strip(),
            type=str(data.get("type", "")).strip(),
            name=str(data.get("name", "")).strip(),
            params=dict(data.get("params") or {}),
            next=data.get("next"),
            on_true=data.get("on_true"),
            on_false=data.get("on_false"),
            on_timeout=data.get("on_timeout"),
            on_error=data.get("on_error"),
            branches=dict(data.get("branches") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "params": self.params,
        }
        for key in ("next", "on_true", "on_false", "on_timeout", "on_error"):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        if self.branches:
            data["branches"] = self.branches
        return data


@dataclass
class Flow:
    name: str
    start_node: str
    nodes: list[FlowNode] = field(default_factory=list)
    version: int = FLOW_VERSION
    variables: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Flow":
        if not isinstance(data, dict):
            raise ValueError("El flujo debe ser un objeto JSON.")
        if data.get("format", FLOW_FORMAT) != FLOW_FORMAT:
            raise ValueError("El archivo no es un flujo de AutoClicker Studio.")
        version = int(data.get("version", FLOW_VERSION))
        if version != FLOW_VERSION:
            raise ValueError(f"Versión de flujo no compatible: {version}.")
        raw_nodes = data.get("nodes", [])
        if not isinstance(raw_nodes, list):
            raise ValueError("'nodes' debe ser una lista.")
        return cls(
            name=str(data.get("name") or "Flujo sin nombre"),
            start_node=str(data.get("start_node") or ""),
            nodes=[FlowNode.from_dict(n) for n in raw_nodes],
            version=version,
            variables=dict(data.get("variables") or {}),
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": FLOW_FORMAT,
            "version": self.version,
            "name": self.name,
            "start_node": self.start_node,
            "variables": self.variables,
            "metadata": self.metadata,
            "nodes": [node.to_dict() for node in self.nodes],
        }

    def node_map(self) -> dict[str, FlowNode]:
        return {node.id: node for node in self.nodes}


def load_flow(path: str | Path) -> Flow:
    with open(path, "r", encoding="utf-8") as stream:
        return Flow.from_dict(json.load(stream))


def save_flow(flow: Flow, path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(flow.to_dict(), stream, ensure_ascii=False, indent=2)
    temporary.replace(destination)
