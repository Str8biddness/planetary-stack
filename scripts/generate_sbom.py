#!/usr/bin/env python3
"""Generate a Software Bill of Materials (SBOM) from the installed environment.

This script does NOT hand-write dependency data. It enumerates the Python
distributions actually installed in the running interpreter via
``importlib.metadata`` and emits two artifacts:

1. A CycloneDX-style JSON SBOM (``python-sbom.json``).
2. A human-readable third-party license/notice bundle
   (``THIRD_PARTY_NOTICES.md``).

License detection is deliberately conservative. Where a license cannot be
determined from distribution metadata it is recorded verbatim as
``UNKNOWN — needs manual review`` rather than guessed. Run this with the
project's virtual environment interpreter so the output reflects the real
installed environment.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import importlib.metadata as importlib_metadata
import json
import sys
from pathlib import Path
from typing import Any

UNKNOWN_LICENSE = "UNKNOWN — needs manual review"

# CycloneDX specification version this document targets.
CYCLONEDX_SPEC_VERSION = "1.5"

# A License field longer than this (or containing newlines) is almost
# certainly the full license text dumped into metadata rather than a concise
# identifier, so it is not trusted as a detected license string.
MAX_LICENSE_FIELD_LEN = 200


def _clean(value: str | None) -> str | None:
    """Return a stripped non-empty string, or ``None``."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if value.upper() in {"UNKNOWN", "UNKNOWN LICENSE", "NONE"}:
        return None
    return value


def _license_from_classifiers(classifiers: list[str]) -> str | None:
    """Derive a license string from Trove ``License ::`` classifiers.

    Returns the distinct human-readable license names joined with ``OR``, or
    ``None`` when no license classifier is present.
    """
    names: list[str] = []
    for classifier in classifiers:
        if not classifier.startswith("License"):
            continue
        # e.g. "License :: OSI Approved :: Apache Software License"
        tail = classifier.split("::")[-1].strip()
        if not tail or tail.lower() in {"osi approved"}:
            continue
        if tail not in names:
            names.append(tail)
    if not names:
        return None
    return " OR ".join(names)


def detect_license(meta: Any) -> tuple[str, str]:
    """Detect a license for a distribution's metadata.

    Returns a ``(license_string, source)`` tuple. ``source`` records which
    metadata field the license was detected from so the report is auditable.
    When nothing can be detected the license string is ``UNKNOWN_LICENSE``.
    """
    # 1. Modern SPDX License-Expression (PEP 639) is the most authoritative.
    expression = _clean(meta.get("License-Expression"))
    if expression:
        return expression, "License-Expression"

    # 2. A concise free-form License field.
    license_field = _clean(meta.get("License"))
    if (
        license_field
        and "\n" not in license_field
        and len(license_field) <= MAX_LICENSE_FIELD_LEN
    ):
        return license_field, "License"

    # 3. Trove license classifiers.
    classifiers = meta.get_all("Classifier") or []
    from_classifiers = _license_from_classifiers(list(classifiers))
    if from_classifiers:
        return from_classifiers, "Classifier"

    # 4. A License field that existed but was too long to trust as an id —
    #    record that text was present but still needs manual review.
    if license_field:
        return UNKNOWN_LICENSE, "License (unparsable full text)"

    return UNKNOWN_LICENSE, "none"


def collect_components() -> list[dict[str, Any]]:
    """Enumerate installed distributions and their detected licenses.

    Deduplicates on (name, version) and returns a list sorted by
    case-insensitive name then version for stable, diffable output.
    """
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for dist in importlib_metadata.distributions():
        meta = dist.metadata
        raw_name = meta.get("Name") or getattr(dist, "name", None)
        if not raw_name:
            continue
        name = raw_name.strip()
        version = (meta.get("Version") or "0").strip()
        key = (name.lower(), version)
        if key in seen:
            continue
        license_str, source = detect_license(meta)
        seen[key] = {
            "name": name,
            "version": version,
            "license": license_str,
            "license_source": source,
        }
    return sorted(
        seen.values(),
        key=lambda c: (c["name"].lower(), c["version"]),
    )


def build_cyclonedx(components: list[dict[str, Any]], timestamp: str) -> dict[str, Any]:
    """Build a CycloneDX-style SBOM document from collected components."""
    cyclonedx_components: list[dict[str, Any]] = []
    for comp in components:
        purl = f"pkg:pypi/{comp['name']}@{comp['version']}"
        license_str = comp["license"]
        # SPDX expressions contain boolean operators; represent those with the
        # CycloneDX "expression" form, everything else as a named license.
        if license_str == UNKNOWN_LICENSE:
            licenses = [{"license": {"name": UNKNOWN_LICENSE}}]
        elif any(op in license_str for op in (" OR ", " AND ", " WITH ")):
            licenses = [{"expression": license_str}]
        else:
            licenses = [{"license": {"name": license_str}}]
        cyclonedx_components.append(
            {
                "type": "library",
                "bom-ref": purl,
                "name": comp["name"],
                "version": comp["version"],
                "purl": purl,
                "licenses": licenses,
                "properties": [
                    {
                        "name": "planetary:license_source",
                        "value": comp["license_source"],
                    }
                ],
            }
        )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": CYCLONEDX_SPEC_VERSION,
        "version": 1,
        "metadata": {
            "timestamp": timestamp,
            "tools": [
                {
                    "vendor": "Planetary Stack",
                    "name": "generate_sbom.py",
                    "version": "1.0.0",
                }
            ],
            "properties": [
                {
                    "name": "planetary:python_version",
                    "value": sys.version.split()[0],
                },
                {
                    "name": "planetary:component_count",
                    "value": str(len(components)),
                },
            ],
        },
        "components": cyclonedx_components,
    }


def build_notices(components: list[dict[str, Any]], timestamp: str) -> str:
    """Build the human-readable THIRD_PARTY_NOTICES.md content."""
    unknown = [c for c in components if c["license"] == UNKNOWN_LICENSE]
    lines: list[str] = []
    lines.append("# Third-Party Notices")
    lines.append("")
    lines.append(
        "This bundle lists every Python distribution installed in the "
        "environment used to build Planetary Stack, with its version and the "
        "license detected from distribution metadata."
    )
    lines.append("")
    lines.append(
        "It is generated by `scripts/generate_sbom.py` from the actual "
        "installed environment. Do not edit it by hand."
    )
    lines.append("")
    lines.append(f"- Generated: {timestamp}")
    lines.append(f"- Python: {sys.version.split()[0]}")
    lines.append(f"- Total dependencies: {len(components)}")
    lines.append(
        f"- Dependencies with an undetected license: {len(unknown)} "
        "(marked `UNKNOWN — needs manual review`)"
    )
    lines.append("")
    lines.append(
        "Where a license could not be detected from metadata it is recorded "
        "as `UNKNOWN — needs manual review` and must be resolved manually "
        "before public distribution."
    )
    lines.append("")
    lines.append("| # | Dependency | Version | Detected license | Source |")
    lines.append("| --- | --- | --- | --- | --- |")
    for index, comp in enumerate(components, start=1):
        lines.append(
            f"| {index} | {comp['name']} | {comp['version']} | "
            f"{comp['license']} | {comp['license_source']} |"
        )
    lines.append("")
    if unknown:
        lines.append("## Dependencies needing manual license review")
        lines.append("")
        for comp in unknown:
            lines.append(f"- {comp['name']} {comp['version']}")
        lines.append("")
    return "\n".join(lines)


def generate(output_dir: Path, timestamp: str | None = None) -> dict[str, Any]:
    """Generate both SBOM artifacts into ``output_dir``.

    Returns a small summary dict describing what was written.
    """
    if timestamp is None:
        timestamp = (
            _dt.datetime.now(_dt.timezone.utc)
            .replace(microsecond=0)
            .isoformat()
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    components = collect_components()
    sbom = build_cyclonedx(components, timestamp)
    notices = build_notices(components, timestamp)

    sbom_path = output_dir / "python-sbom.json"
    notices_path = output_dir / "THIRD_PARTY_NOTICES.md"
    sbom_path.write_text(json.dumps(sbom, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    notices_path.write_text(notices + "\n", encoding="utf-8")

    unknown_count = sum(1 for c in components if c["license"] == UNKNOWN_LICENSE)
    return {
        "sbom_path": sbom_path,
        "notices_path": notices_path,
        "component_count": len(components),
        "unknown_count": unknown_count,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "docs" / "sbom",
        help="Directory to write the SBOM artifacts into.",
    )
    parser.add_argument(
        "--timestamp",
        default=None,
        help="Override the ISO-8601 generation timestamp (mainly for tests).",
    )
    args = parser.parse_args(argv)

    summary = generate(args.output_dir, timestamp=args.timestamp)
    print(f"Wrote {summary['sbom_path']}")
    print(f"Wrote {summary['notices_path']}")
    print(f"Components: {summary['component_count']}")
    print(f"UNKNOWN licenses (need manual review): {summary['unknown_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
