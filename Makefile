.PHONY: build test demo evidence clean-generated doctor lint typecheck check compose-config compose-build compose-doctor

build: compose-build

doctor:
	python -m baby_first_steps_medallion.cli doctor

test:
	pytest

demo:
	python scripts/run_demo.py --fresh --yes

evidence:
	python -m baby_first_steps_medallion.cli evidence

clean-generated:
	python -m baby_first_steps_medallion.cli clean-generated --yes

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
