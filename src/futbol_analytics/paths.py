"""Rutas de datos de la aplicación.

La caché vive por defecto en `data/cache/` relativo al directorio de
trabajo (el raíz del repo al ejecutar la app o el CLI). En contenedores
u otros despliegues se puede reubicar con la variable de entorno
`FUTBOL_ANALYTICS_CACHE`.
"""

from __future__ import annotations

import os
from pathlib import Path

CACHE_DIR = Path(os.environ.get("FUTBOL_ANALYTICS_CACHE", "data/cache"))
