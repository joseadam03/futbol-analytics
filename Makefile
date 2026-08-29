.DEFAULT_GOAL := help

.PHONY: help install lint format test run report docker-build docker-run lock

help:  ## esta ayuda
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:  ## dependencias fijadas + paquete editable + hooks de pre-commit
	pip install -r requirements-dev.txt
	pip install --no-deps -e .
	pre-commit install

lint:  ## ruff check + comprobación de formato
	ruff check src scripts tests streamlit_app.py app_common.py app_pages
	ruff format --check .

format:  ## aplica formato y autofixes de ruff
	ruff format .
	ruff check --fix src scripts tests streamlit_app.py app_common.py app_pages

test:  ## tests con cobertura
	python -m pytest -q --cov=futbol_analytics --cov-report=term-missing

run:  ## la app en local
	streamlit run streamlit_app.py

report:  ## informe CLI de ejemplo (make report PLAYER="Messi")
	python scripts/player_report.py --player "$(or $(PLAYER),Messi)"

docker-build:  ## imagen de producción
	docker build -t futbol-analytics .

docker-run:  ## la app containerizada en http://localhost:8501
	docker run --rm -p 8501:8501 futbol-analytics

lock:  ## re-resuelve dependencias (uv.lock + requirements*.txt)
	uv lock
	uv export --no-hashes --no-emit-project -o requirements.txt
	uv export --no-hashes --no-emit-project --extra dev -o requirements-dev.txt
