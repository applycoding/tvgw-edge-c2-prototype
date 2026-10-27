PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin
PY := $(BIN)/python
PIP := $(BIN)/pip
MASTER_SEED ?= 424242

.PHONY: setup venv download-data test slice bench ci plots summary audit bench-assoc all clean

venv:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt
	$(PIP) install -e .

setup: venv download-data

download-data:
	$(PY) scripts/download_niem.py
	$(PY) scripts/download_datasets.py

test:
	$(PY) -m pytest -q

slice:
	$(PY) scripts/run_all_benchmarks.py --mode slice --master-seed $(MASTER_SEED)

bench:
	$(PY) scripts/run_all_benchmarks.py --mode full --master-seed $(MASTER_SEED)

bench-assoc:
	$(PY) scripts/bench_association.py

ci:
	$(PY) scripts/run_all_benchmarks.py --mode ci --master-seed $(MASTER_SEED) --results-dir results/ci

plots:
	$(PY) -c "from tvgw.plots import generate_all_plots; generate_all_plots()"

summary:
	$(PY) scripts/run_all_benchmarks.py --mode summary-only --master-seed $(MASTER_SEED)

audit:
	$(PY) scripts/audit_wording.py

all: venv download-data test bench plots summary audit
	@echo "make all complete"

clean:
	rm -rf $(VENV) .pytest_cache .hypothesis
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
