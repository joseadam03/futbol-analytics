# Imagen en dos etapas: las dependencias se compilan en el builder y la
# imagen final queda limpia y corre como usuario sin privilegios.
FROM python:3.14-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Dependencias fijadas por uv.lock (reproducible), luego el paquete.
COPY requirements.txt ./
RUN pip install --prefix=/install -r requirements.txt

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
EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

CMD ["streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0"]
