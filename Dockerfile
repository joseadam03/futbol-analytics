# Imagen en dos etapas: las dependencias se compilan en el builder y la
# imagen final queda limpia y corre como usuario sin privilegios.
FROM python:3.14-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Dependencias fijadas por uv.lock (reproducible), luego el paquete.
# requirements.txt lleva "-e ." como primera línea para Streamlit Community
# Cloud (que solo ejecuta pip install -r requirements.txt); aquí se descarta
# porque el código fuente aún no está copiado y el paquete se instala aparte
# más abajo, ya con src/ disponible.
COPY requirements.txt ./
RUN grep -v '^-e ' requirements.txt > requirements.docker.txt \
    && pip install --prefix=/install -r requirements.docker.txt

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --prefix=/install --no-deps .


FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FUTBOL_ANALYTICS_CACHE=/app/data/cache

RUN useradd --create-home --uid 1000 futbol

WORKDIR /app
COPY --from=builder /install /usr/local
COPY streamlit_app.py app_common.py ./
COPY app_pages ./app_pages
COPY .streamlit ./.streamlit
RUN mkdir -p /app/data/cache && chown -R futbol:futbol /app/data

USER futbol
# 8501 es el puerto de Streamlit en local (docker run -p 8501:8501); Cloud Run
# inyecta su propio $PORT en tiempo de ejecución (normalmente 8080) y CMD/
# HEALTHCHECK lo respetan si está definido, con 8501 como valor por defecto.
EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8501}/_stcore/health')"

CMD streamlit run streamlit_app.py --server.address=0.0.0.0 --server.port=${PORT:-8501}
