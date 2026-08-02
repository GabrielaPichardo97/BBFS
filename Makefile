.PHONY: doctor test lint typecheck check compose-config compose-build compose-doctor

doctor:
	python -m baby_first_steps_medallion.cli doctor

test:
	pytest

lint:
	ruff check src tests

typecheck:
	mypy src

check: lint typecheck test

compose-config:
	docker compose config

compose-build:
	docker compose build

compose-doctor:
	docker compose run --rm pipeline doctor
