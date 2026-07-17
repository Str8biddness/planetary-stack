"""Export and validate CHAL/vSource v1 JSON Schema documents."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from pydantic.version import VERSION as PYDANTIC_VERSION

from .canonical import signing_bytes
from .models import SCHEMA_EXPORTS, SCHEMA_MODELS, validate_document


SCHEMA_ROOT = Path(__file__).with_name("schemas")
SCHEMA_BASE_URI = "https://schemas.reality-core.systems/chal-vsource/v1"
MANIFEST_NAME = "schema-manifest.json"
EXPECTED_PYDANTIC_VERSION = "2.13.4"


def require_generator_version() -> None:
    if PYDANTIC_VERSION != EXPECTED_PYDANTIC_VERSION:
        raise RuntimeError(
            "schema generation requires "
            f"pydantic=={EXPECTED_PYDANTIC_VERSION}; found {PYDANTIC_VERSION}"
        )


def require_explicit_wire_properties(node: Any) -> None:
    """Make default materialization identical in every language."""

    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict) and properties:
            node["required"] = sorted(properties)
        for value in node.values():
            require_explicit_wire_properties(value)
    elif isinstance(node, list):
        for value in node:
            require_explicit_wire_properties(value)


def require_absolute_json_schema_patterns(node: Any) -> None:
    """Make JSON Schema `$` anchors reject a trailing newline like Pydantic."""

    if isinstance(node, dict):
        pattern = node.get("pattern")
        if isinstance(pattern, str) and pattern.endswith("$"):
            node["pattern"] = pattern + r"(?![\s\S])"
        pattern_properties = node.get("patternProperties")
        if isinstance(pattern_properties, dict):
            node["patternProperties"] = {
                (
                    pattern + r"(?![\s\S])"
                    if pattern.endswith("$")
                    else pattern
                ): value
                for pattern, value in pattern_properties.items()
            }
        for value in node.values():
            require_absolute_json_schema_patterns(value)
    elif isinstance(node, list):
        for value in node:
            require_absolute_json_schema_patterns(value)


def normalize_pydantic_constraint_keywords(node: Any) -> None:
    """Translate constraints wrapped around BeforeValidator into JSON Schema."""

    if isinstance(node, dict):
        for source, target in (
            ("ge", "minimum"),
            ("le", "maximum"),
            ("gt", "exclusiveMinimum"),
            ("lt", "exclusiveMaximum"),
        ):
            if source in node:
                node[target] = node.pop(source)
        for value in node.values():
            normalize_pydantic_constraint_keywords(value)
    elif isinstance(node, list):
        for value in node:
            normalize_pydantic_constraint_keywords(value)


def _nonnull(name: str) -> dict[str, Any]:
    return {
        "properties": {name: {"not": {"type": "null"}}},
        "required": [name],
    }


def add_shared_resource_vector_rules(payload: dict[str, Any]) -> None:
    resource_vector = payload.get("$defs", {}).get("ResourceVector")
    if not isinstance(resource_vector, dict):
        return
    resource_vector["allOf"] = [
        {
            "if": {
                "properties": {"gpu_count": {"const": 0}},
                "required": ["gpu_count"],
            },
            "then": {"properties": {"gpu_memory_bytes": {"const": 0}}},
            "else": {"properties": {"gpu_memory_bytes": {"minimum": 1}}},
        }
    ]


def lease_gpu_id_count_rules() -> list[dict[str, Any]]:
    return [
        {
            "if": {
                "properties": {
                    "resources": {
                        "properties": {"gpu_count": {"const": count}},
                        "required": ["gpu_count"],
                    }
                },
                "required": ["resources"],
            },
            "then": {
                "properties": {
                    "gpu_ids": {"minItems": count, "maxItems": count}
                }
            },
        }
        for count in range(65)
    ]


SCHEMA_CONDITIONALS: dict[str, list[dict[str, Any]]] = {
    "error.schema.json": [
        {
            "if": {
                "properties": {"retryable": {"const": False}},
                "required": ["retryable"],
            },
            "then": {"properties": {"retry_after_ms": {"type": "null"}}},
        }
    ],
    "chal-response.schema.json": [
        {
            "if": {
                "properties": {"status": {"const": "succeeded"}},
                "required": ["status"],
            },
            "then": {"properties": {"error": {"type": "null"}}},
            "else": _nonnull("error"),
        }
    ],
    "lease.schema.json": [
        {
            "if": {
                "properties": {"state": {"const": "revoked"}},
                "required": ["state"],
            },
            "then": _nonnull("revocation_reason"),
            "else": {"properties": {"revocation_reason": {"type": "null"}}},
        },
    ],
    "placement.schema.json": [
        {
            "if": {
                "properties": {"result": {"const": "placed"}},
                "required": ["result"],
            },
            "then": {
                "properties": {
                    "selected_candidate": {
                        "not": {"type": "null"},
                        "properties": {"eligible": {"const": True}},
                        "required": ["eligible"],
                    },
                    "rejection_error": {"type": "null"},
                },
                "required": ["selected_candidate"],
            },
            "else": {
                "properties": {
                    "selected_candidate": {"type": "null"},
                    "rejection_error": {"not": {"type": "null"}},
                },
                "required": ["rejection_error"],
            },
        }
    ],
    "lifecycle.schema.json": [
        {
            "if": {
                "properties": {"state": {"const": "completed"}},
                "required": ["state"],
            },
            "then": {"properties": {"outputs": {"minItems": 1}}},
        },
        {
            "if": {
                "properties": {"state": {"const": "checkpointed"}},
                "required": ["state"],
            },
            "then": _nonnull("checkpoint"),
        },
        {
            "if": {
                "properties": {"state": {"enum": ["failed", "lost"]}},
                "required": ["state"],
            },
            "then": _nonnull("error"),
        },
        {
            "anyOf": [
                {
                    "properties": {
                        "previous_state": {"type": "null"},
                        "state": {"const": "admitted"},
                        "sequence": {"const": 0},
                    },
                    "required": ["previous_state", "state", "sequence"],
                },
                {
                    "properties": {
                        "previous_state": {"const": "admitted"},
                        "state": {"enum": ["cancelled", "failed", "staged"]},
                        "sequence": {"minimum": 1},
                    },
                    "required": ["previous_state", "state", "sequence"],
                },
                {
                    "properties": {
                        "previous_state": {"const": "staged"},
                        "state": {"enum": ["cancelled", "failed", "running"]},
                        "sequence": {"minimum": 1},
                    },
                    "required": ["previous_state", "state", "sequence"],
                },
                {
                    "properties": {
                        "previous_state": {"const": "running"},
                        "state": {
                            "enum": [
                                "cancelled",
                                "checkpointed",
                                "completed",
                                "evicted",
                                "failed",
                                "lost",
                            ]
                        },
                        "sequence": {"minimum": 1},
                    },
                    "required": ["previous_state", "state", "sequence"],
                },
                {
                    "properties": {
                        "previous_state": {"const": "checkpointed"},
                        "state": {
                            "enum": [
                                "cancelled",
                                "completed",
                                "evicted",
                                "failed",
                                "lost",
                                "running",
                            ]
                        },
                        "sequence": {"minimum": 1},
                    },
                    "required": ["previous_state", "state", "sequence"],
                },
                {
                    "properties": {
                        "previous_state": {"const": "evicted"},
                        "state": {"enum": ["cancelled", "failed", "staged"]},
                        "sequence": {"minimum": 1},
                    },
                    "required": ["previous_state", "state", "sequence"],
                },
            ]
        },
    ],
    "telemetry.schema.json": [
        {
            "if": {
                "properties": {"status": {"const": "failed"}},
                "required": ["status"],
            },
            "then": _nonnull("error_id"),
        }
    ],
}


SCHEMA_SEMANTIC_INVARIANTS: dict[str, list[str]] = {
    "capability.schema.json": [
        "Verify Ed25519 over RFC8785(document without signature).",
        "Authority expires at not_before + ttl_seconds; reject before or after that window.",
        "Canonical-order arrays are unique and lexicographically sorted.",
        (
            "A device URI matches a resource_prefix only by literal segment "
            "prefix; no regex or glob expansion."
        ),
        (
            "For an allocation, require request resources componentwise <= capability "
            "resources, reserve+execute actions, matching account/subject, selected-node "
            "audience, minimum attestation, workload membership, device prefix, and "
            "transport membership."
        ),
    ],
    "chal-request.schema.json": [
        "Verify Ed25519 over RFC8785(document without signature).",
        "Authority expires at issued_at + ttl_seconds; reject after that window.",
        "Persist (account_id,idempotency_key)->request_sha256 and reject a conflicting payload.",
    ],
    "chal-response.schema.json": [
        (
            "Verify Ed25519 and require nested error request_id, request_sha256, "
            "and trace_id to match."
        ),
        (
            "Require lease_id, lease_sha256, and fencing_token to equal the current "
            "durable active lease revision before accepting a result."
        ),
    ],
    "error.schema.json": [
        "Verify Ed25519 over RFC8785(document without signature).",
    ],
    "inventory.schema.json": [
        "Verify Ed25519 and node-key ownership; inventory expires at observed_at + ttl_seconds.",
        (
            "The gpus object is keyed by unique GPU IDs and publishes allocatable "
            "rather than physical capacity."
        ),
        "Canonical-order arrays are unique and lexicographically sorted.",
    ],
    "lease.schema.json": [
        "Verify Ed25519 and the bound request_sha256/inventory_sha256 before reservation.",
        (
            "Authority expires at not_before + ttl_seconds; renewal_sequence must "
            "increase and renewals_remaining must not increase."
        ),
        (
            "For a renewal of lease_id, fencing_token and renewal_sequence strictly "
            "increase; consumers accept only the exact active digest/token revision."
        ),
        (
            "Require lease resources componentwise <= signed request and inventory, "
            "gpu_ids to exist in inventory with sufficient aggregate memory, and "
            "transport/workload/action/audience/device/account joins to pass."
        ),
    ],
    "placement.schema.json": [
        "Verify scheduler Ed25519 signature and bound request digest.",
        (
            "Every candidate account_id equals the decision account_id and "
            "references a verified signed inventory digest."
        ),
        "The selected candidate occurs exactly once in candidates and is eligible.",
        "Nested rejection errors identify the same request digest and trace.",
        (
            "Selected transport is present in the signed capability and inventory; "
            "candidate eligibility applies the normative private-cell allocation joins."
        ),
    ],
    "lifecycle.schema.json": [
        (
            "Verify node Ed25519 signature plus request, inventory, placement, and exact "
            "active lease_sha256/fencing_token bindings."
        ),
        "Sequences are durable, contiguous, monotonic, and replay-safe for each workload.",
        "Nested errors identify the same request digest and trace.",
    ],
    "telemetry.schema.json": [
        "Verify node Ed25519 signature and request digest binding.",
        (
            "Producers must apply the metadata allowlist before emission; raw "
            "content has no representable field."
        ),
    ],
}


def schema_payload(filename: str, model: type) -> dict[str, Any]:
    payload = model.model_json_schema(mode="validation", by_alias=True)
    require_explicit_wire_properties(payload)
    require_absolute_json_schema_patterns(payload)
    normalize_pydantic_constraint_keywords(payload)
    add_shared_resource_vector_rules(payload)
    payload["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    payload["$id"] = f"{SCHEMA_BASE_URI}/{filename}"
    if conditionals := SCHEMA_CONDITIONALS.get(filename):
        payload["allOf"] = [*conditionals]
    if filename == "lease.schema.json":
        payload.setdefault("allOf", []).extend(lease_gpu_id_count_rules())
    payload["x-planetary-semantic-invariants"] = SCHEMA_SEMANTIC_INVARIANTS[
        filename
    ]
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
        "canonicalization": {"implementation": "rfc8785==0.1.4", "rfc": 8785},
        "contract_version": "1.0.0",
        "generator": {"pydantic": PYDANTIC_VERSION},
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
    require_generator_version()
    root.mkdir(parents=True, exist_ok=True)
    for filename, model in sorted(SCHEMA_EXPORTS.items()):
        (root / filename).write_text(
            rendered_schema(filename, model),
            encoding="utf-8",
            newline="\n",
        )
    (root / MANIFEST_NAME).write_text(
        rendered_manifest(),
        encoding="utf-8",
        newline="\n",
    )


def check_schemas(root: Path = SCHEMA_ROOT) -> list[str]:
    require_generator_version()
    drift: list[str] = []
    expected_names = set(SCHEMA_EXPORTS)
    actual_names = {path.name for path in root.glob("*.schema.json")}
    for unexpected in sorted(actual_names - expected_names):
        drift.append(f"unexpected schema file: {unexpected}")
    for filename, model in sorted(SCHEMA_EXPORTS.items()):
        path = root / filename
        expected = rendered_schema(filename, model)
        try:
            Draft202012Validator.check_schema(json.loads(expected))
        except SchemaError as exc:
            drift.append(f"invalid Draft 2020-12 schema {filename}: {exc.message}")
        if not path.exists():
            drift.append(f"missing schema file: {filename}")
        elif path.read_bytes() != expected.encode("utf-8"):
            drift.append(f"schema drift: {filename}")
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.exists():
        drift.append(f"missing schema manifest: {MANIFEST_NAME}")
    elif manifest_path.read_bytes() != rendered_manifest().encode("utf-8"):
        drift.append(f"schema manifest drift: {MANIFEST_NAME}")
    return drift


def validate_schema_document(data: dict[str, Any], root: Path = SCHEMA_ROOT) -> None:
    schema_id = str(data.get("schema"))
    model = SCHEMA_MODELS.get(schema_id)
    filename = next(
        (name for name, candidate in SCHEMA_EXPORTS.items() if candidate is model),
        None,
    )
    if filename is None:
        raise ValueError(f"unsupported CHAL/vSource schema: {schema_id!r}")
    schema = json.loads((root / filename).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(data), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<document>"
        raise ValueError(f"JSON Schema rejection at {location}: {first.message}")


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
    validate_schema_document(payload)
    validated = validate_document(payload)
    signing_bytes(validated)


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
