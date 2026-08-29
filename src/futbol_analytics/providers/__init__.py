"""Registro de proveedores de datos."""

from __future__ import annotations

import os

from .base import Provider
from .statsbomb import StatsBombProvider
from .wyscout import WyscoutProvider


def _registry() -> dict[str, type[Provider]]:
    """Se evalúa en cada llamada para que FUTBOL_ANALYTICS_FAKE surta efecto
    sin juegos de recarga de módulos (lo usan los tests de interfaz y el modo demo)."""
    reg: dict[str, type[Provider]] = {}
    if os.environ.get("FUTBOL_ANALYTICS_FAKE"):
        from .fake import FakeProvider

        reg["fake"] = FakeProvider  # primero: es el proveedor por defecto en modo demo
    reg["statsbomb"] = StatsBombProvider
    reg["wyscout"] = WyscoutProvider
    return reg


def get_provider(key: str) -> Provider:
    registry = _registry()
    if key not in registry:
        raise KeyError(f"Proveedor desconocido: {key}. Disponibles: {list(registry)}")
    return registry[key]()


def list_providers() -> dict[str, Provider]:
    return {key: cls() for key, cls in _registry().items()}
