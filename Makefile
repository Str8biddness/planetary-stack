SHELL := /usr/bin/env bash
PYTHON ?= python3

.PHONY: doctor status test test-contracts test-synthesus test-knowledge test-knowledge-source test-planetary test-planetary-iso

doctor:
	PYTHON_BIN="$(PYTHON)" ./scripts/doctor.sh

status:
	./scripts/component-status.sh

test: test-contracts test-knowledge-source test-synthesus

test-contracts:
	$(PYTHON) -m contracts.chal_vsource.v1.schema_tool --check
	PYTHONHASHSEED=1 $(PYTHON) -m pytest -q tests/test_chal_vsource_contracts.py
	PYTHONHASHSEED=4 $(PYTHON) -m pytest -q tests/test_chal_vsource_contracts.py

test-synthesus:
	cd apps/synthesus/runtime && $(PYTHON) -m pytest -q

test-knowledge:
	cd knowledge/knowledge-cloud && $(PYTHON) scripts/validate_bundle.py --root artifacts
	cd knowledge/knowledge-cloud && $(PYTHON) scripts/validate_source_planes.py --root .

test-knowledge-source:
	cd knowledge/knowledge-cloud && $(PYTHON) scripts/validate_source_planes.py --root .

test-planetary:
	./scripts/test-planetary-kernel.sh

test-planetary-iso:
	./scripts/test-planetary-kernel.sh --iso
