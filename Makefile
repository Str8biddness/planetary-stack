SHELL := /usr/bin/env bash

.PHONY: doctor status test test-synthesus test-knowledge test-knowledge-source test-planetary

doctor:
	./scripts/doctor.sh

status:
	./scripts/component-status.sh

test: test-knowledge-source test-synthesus

test-synthesus:
	cd apps/synthesus/runtime && python -m pytest -q

test-knowledge:
	cd knowledge/knowledge-cloud && python scripts/validate_bundle.py --root artifacts
	cd knowledge/knowledge-cloud && python scripts/validate_source_planes.py --root .

test-knowledge-source:
	cd knowledge/knowledge-cloud && python scripts/validate_source_planes.py --root .

test-planetary:
	$(MAKE) -C platform/planetary-os/Synthesus_Kernel clean
	$(MAKE) -C platform/planetary-os/Synthesus_Kernel

