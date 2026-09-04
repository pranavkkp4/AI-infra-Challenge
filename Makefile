.PHONY: install demo-data ingest test lint audit evaluate dev build

install:
	python -m pip install -e "backend[dev]"
	npm --prefix frontend install

demo-data:
	python scripts/generate_demo_data.py

ingest:
	python scripts/run_pipeline.py

test:
	python -m pytest tests
	npm --prefix frontend run typecheck
	npm --prefix frontend test

lint:
	ruff check backend/app scripts tests
	ruff format --check backend/app scripts tests

audit:
	python scripts/sample_audit.py

evaluate:
	python scripts/evaluate_audit.py

dev:
	docker compose up --build

build:
	npm --prefix frontend run build
	docker compose build
