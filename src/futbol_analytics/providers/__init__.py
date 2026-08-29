"""Registro de proveedores de datos."""

from __future__ import annotations

from .base import Provider
from .statsbomb import StatsBombProvider
from .wyscout import WyscoutProvider

_REGISTRY: dict[str, type[Provider]] = {
    "statsbomb": StatsBombProvider,
    "wyscout": WyscoutProvider,
}


def get_provider(key: str) -> Provider:
    if key not in _REGISTRY:
        raise KeyError(f"Proveedor desconocido: {key}. Disponibles: {list(_REGISTRY)}")
    return _REGISTRY[key]()


def list_providers() -> dict[str, Provider]:
    return {key: cls() for key, cls in _REGISTRY.items()}
