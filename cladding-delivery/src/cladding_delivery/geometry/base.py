from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

class GeometryUnsupported(RuntimeError): pass

class GeometryProvider(ABC):
    name='base'
    @abstractmethod
    def health(self) -> dict[str, Any]: ...
    @abstractmethod
    def build_component(self, component: dict, out_dir: Path) -> dict: ...
    @abstractmethod
    def unfold_component(self, component: dict, out_dir: Path) -> dict: ...
