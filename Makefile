.PHONY: setup lint test api ui demo data features train eval format

VENV ?= .venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip
RUFF = $(VENV)/bin/ruff
PYTEST = $(VENV)/bin/pytest
UVICORN = $(VENV)/bin/uvicorn

setup:
	@if [ ! -d "$(VENV)" ]; then python3 -m venv $(VENV); fi
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	@if [ -d "ui" ] && [ -f "ui/package.json" ]; then npm --prefix ui install; fi

lint:
	$(RUFF) check .

format:
	$(RUFF) format .

test:
	$(PYTEST) tests
	@if [ -d "ui" ] && [ -f "ui/package.json" ]; then npm --prefix ui run test:run; fi

api:
	$(PYTHON) -m uvicorn goldenminutes.api.main:app --host 0.0.0.0 --port 8000 --reload

ui:
	npm --prefix ui run dev

PROFILE ?= small

# macOS Accelerate BLAS crashes when PyTorch uses multiple threads alongside
# another BLAS library.  Pin to 1 thread for all targets that invoke torch.
export OMP_NUM_THREADS ?= 1
export MKL_NUM_THREADS ?= 1

data:
	$(PYTHON) -m goldenminutes.simulator.generate --profile $(PROFILE)

features:
	$(PYTHON) -m goldenminutes.features.offline --profile $(PROFILE)

train:
	$(PYTHON) -m goldenminutes.models.train --profile $(PROFILE)
	$(PYTHON) -m goldenminutes.eval.ablation --profile $(PROFILE)

eval:
	$(PYTHON) -m goldenminutes.eval.run_eval --profile $(PROFILE)

demo:
	@if [ -d "ui" ] && [ -f "ui/package.json" ]; then npm --prefix ui run build; fi
	$(PYTHON) -m goldenminutes.demo

