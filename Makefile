PYTHON ?= python3

.PHONY: install lint test run migrate

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m mypy agents config storage

test:
	$(PYTHON) -m pytest

run:
	$(PYTHON) -m uvicorn api_server:app --reload --port 5001

migrate:
	$(PYTHON) -m storage.migrate
