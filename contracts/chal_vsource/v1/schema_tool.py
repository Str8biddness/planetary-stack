"""Export and validate CHAL/vSource v1 JSON Schema documents."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .models import SCHEMA_EXPORTS, validate_document


SCHEMA_ROOT = Path(__file__).with_name("schemas")
SCHEMA_BASE_URI = "https://schemas.reality-core.systems/chal-vsource/v1"
MANIFEST_NAME = "schema-manifest.json"


def schema_payload(filename: str, model: type) -> dict[str, Any]:
    payload = model.model_json_schema(mode="validation", by_alias=True)
    payload["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    payload["$id"] = f"{SCHEMA_BASE_URI}/{filename}"
    return payload


def rendered_schema(filename: str, model: type) -> str:
    return json.dumps(
        schema_payload(filename, model),
        indent=2,
        sort_keys=True,
    ) + "\n"


def rendered_manifest() -> str:
    payload = {
        "bundle": "planetary.chal-vsource.v1",
        "json_schema_draft": "2020-12",
        "schemas": {
            filename: {
                "id": f"{SCHEMA_BASE_URI}/{filename}",
                "sha256": hashlib.sha256(
                    rendered_schema(filename, model).encode("utf-8")
                ).hexdigest(),
            }
            for filename, model in sorted(SCHEMA_EXPORTS.items())
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def write_schemas(root: Path = SCHEMA_ROOT) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for filename, model in sorted(SCHEMA_EXPORTS.items()):
        (root / filename).write_text(
            rendered_schema(filename, model),
            encoding="utf-8",
        )
    (root / MANIFEST_NAME).write_text(rendered_manifest(), encoding="utf-8")


def check_schemas(root: Path = SCHEMA_ROOT) -> list[str]:
    drift: list[str] = []
    expected_names = set(SCHEMA_EXPORTS)
    actual_names = {path.name for path in root.glob("*.schema.json")}
    for unexpected in sorted(actual_names - expected_names):
        drift.append(f"unexpected schema file: {unexpected}")
    for filename, model in sorted(SCHEMA_EXPORTS.items()):
        path = root / filename
        expected = rendered_schema(filename, model)
        if not path.exists():
            drift.append(f"missing schema file: {filename}")
        elif path.read_text(encoding="utf-8") != expected:
            drift.append(f"schema drift: {filename}")
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.exists():
        drift.append(f"missing schema manifest: {MANIFEST_NAME}")
    elif manifest_path.read_text(encoding="utf-8") != rendered_manifest():
        drift.append(f"schema manifest drift: {MANIFEST_NAME}")
    return drift


def validate_path(path: Path) -> None:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key is prohibited: {key!r}")
            result[key] = value
        return result

    payload = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_keys,
    )
    validate_document(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="regenerate JSON Schemas")
    mode.add_argument("--check", action="store_true", help="fail if schemas drift")
    mode.add_argument("--validate", type=Path, help="validate one contract document")
    args = parser.parse_args()

    if args.write:
        write_schemas()
        return 0
    if args.check:
        drift = check_schemas()
        if drift:
            for issue in drift:
                print(issue)
            return 1
        print(f"validated {len(SCHEMA_EXPORTS)} frozen schemas")
        return 0
    validate_path(args.validate)
    print(f"valid contract: {args.validate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
