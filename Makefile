.PHONY: help install test lint demo import serve docker-up docker-import docker-down clean

help:
	@echo "install        pip install -e '.[dev]'"
	@echo "test           run the test suite (offline, uses the synthetic fixture)"
	@echo "lint           ruff check"
	@echo "demo           load the synthetic demo fixture into ./data (no network)"
	@echo "import         download RxNorm + DDInter and build ./data/localddi.sqlite"
	@echo "serve          run the API on http://127.0.0.1:8080"
	@echo "docker-up      docker compose up -d --build"
	@echo "docker-import  run the import inside the container"
	@echo "docker-down    docker compose down"

install:
	pip install -e '.[dev]'

test:
	python -m pytest -q

lint:
	ruff check .

demo:
	python -m localddi import --demo

import:
	python -m localddi import

serve:
	python -m localddi serve

docker-up:
	docker compose up -d --build

docker-import:
	docker compose run --rm api localddi import

docker-down:
	docker compose down

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache
