"""Registro de proveedores de datos."""

from __future__ import annotations

import os

from .base import Provider
from .fake import FakeProvider
from .statsbomb import StatsBombProvider
from .wyscout import WyscoutProvider

_REGISTRY: dict[str, type[Provider]] = {
    "fake": FakeProvider,
    "statsbomb": StatsBombProvider,
    "wyscout": WyscoutProvider,
}


def get_provider(key: str) -> Provider:
    """Resuelve cualquier proveedor por clave, incluido "fake".

    Sin gate aquí a propósito: un usuario del login con proveedor forzado a
    "fake" (ver auth.py) tiene que poder cargarlo aunque FUTBOL_ANALYTICS_FAKE
    no esté activo para todo el despliegue. El gate de "¿se ofrece en el
    desplegable?" vive solo en list_providers().
    """
    if key not in _REGISTRY:
        raise KeyError(f"Proveedor desconocido: {key}. Disponibles: {list(_REGISTRY)}")
    return _REGISTRY[key]()


def list_providers(*, include_fake: bool | None = None) -> dict[str, Provider]:
    """Proveedores que se ofrecen en el desplegable de la barra lateral.

    `include_fake=None` (por defecto) sigue la variable de entorno
    FUTBOL_ANALYTICS_FAKE (modo demo global, para tests y `make demo`);
    forzarlo a True lo añade también para un usuario concreto del login
    aunque el despliegue no esté en modo demo global.
    """
    if include_fake is None:
        include_fake = bool(os.environ.get("FUTBOL_ANALYTICS_FAKE"))
    keys = (["fake"] if include_fake else []) + ["statsbomb", "wyscout"]  # fake primero: por defecto en demo
    return {key: _REGISTRY[key]() for key in keys}
