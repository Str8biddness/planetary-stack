#!/usr/bin/env python3
"""Deterministic bounded ONNX text-classification runner for AIVM.

This is the fixed, operator-owned executable behind the
``aivm.model.text-classify.v1`` trusted entrypoint.  It runs inside the
immutable profile image with a read-only rootfs, no network, and no
writable mounts.  Contract:

- argv is exactly ``<model_path> <document_path>``; both are read-only
  mounts placed by the executor from admitted content-addressed artifacts.
- the document must be UTF-8 and at most ``MAX_DOCUMENT_BYTES`` bytes.
- the model must be a single-input ``float32 [1, N]`` / single-output
  ``[1, C]`` ONNX classifier; class labels may be published through ONNX
  model metadata key ``labels`` as comma-separated values.
- on success the runner writes exactly one strict JSON line to stdout and
  nothing to stderr, then exits 0.
- on any failure it writes nothing to stdout, one short reason to stderr,
  and exits nonzero.  The executor treats any stdout/stderr deviation as a
  fail-closed output violation.

Determinism: single-threaded onnxruntime, a fixed SHA-256 hashing
vectorizer, and fixed-precision score rounding make the emitted bytes a
pure function of the admitted model and document artifacts.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys

MAX_DOCUMENT_BYTES = 65_536
MAX_LABELS = 64
MAX_FEATURE_DIMS = 65_536
DEFAULT_FEATURE_DIMS = 256
RESULT_SCHEMA = "planetary.aivm.result.text-classification.v1"


def _fail(reason: str) -> "NoReturn":  # noqa: F821 - annotation only
    print(reason, file=sys.stderr)
    raise SystemExit(1)


def _read_bounded(path: str, limit: int) -> bytes:
    try:
        with open(path, "rb") as handle:
            data = handle.read(limit + 1)
    except OSError:
        _fail("input_unreadable")
    if len(data) > limit:
        _fail("input_too_large")
    return data


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for character in text.lower():
        if character.isalnum():
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tokens


def _hashing_features(tokens: list[str], dims: int) -> "np.ndarray":  # noqa: F821
    import numpy as np

    features = np.zeros((1, dims), dtype=np.float32)
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:8], "big") % dims
        sign = 1.0 if digest[8] % 2 == 0 else -1.0
        features[0, index] += sign
    norm = float(np.linalg.norm(features))
    if norm > 0.0:
        features /= norm
    return features


def main() -> int:
    if len(sys.argv) != 3:
        _fail("usage_model_and_document_required")
    model_path, document_path = sys.argv[1], sys.argv[2]

    model_bytes = _read_bounded(model_path, 512 * 1024 * 1024)
    document_bytes = _read_bounded(document_path, MAX_DOCUMENT_BYTES)
    try:
        document = document_bytes.decode("utf-8")
    except UnicodeDecodeError:
        _fail("document_not_utf8")

    try:
        import numpy as np
        import onnxruntime
    except ImportError:
        _fail("runtime_dependencies_missing")

    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.log_severity_level = 4
    try:
        session = onnxruntime.InferenceSession(
            model_bytes,
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
    except Exception:
        _fail("model_load_failed")

    inputs = session.get_inputs()
    outputs = session.get_outputs()
    if len(inputs) != 1 or len(outputs) != 1:
        _fail("model_interface_unsupported")
    shape = inputs[0].shape
    if len(shape) != 2:
        _fail("model_interface_unsupported")
    dims = shape[1] if isinstance(shape[1], int) else DEFAULT_FEATURE_DIMS
    if not 1 <= dims <= MAX_FEATURE_DIMS:
        _fail("model_interface_unsupported")

    features = _hashing_features(_tokenize(document), dims)
    try:
        raw_scores = session.run(
            [outputs[0].name], {inputs[0].name: features}
        )[0]
    except Exception:
        _fail("model_inference_failed")

    scores = np.asarray(raw_scores, dtype=np.float64).reshape(-1)
    if not 1 <= scores.shape[0] <= MAX_LABELS:
        _fail("model_output_unsupported")
    if not np.all(np.isfinite(scores)):
        _fail("model_output_unsupported")

    shifted = scores - float(scores.max())
    exponents = [math.exp(value) for value in shifted.tolist()]
    total = sum(exponents)
    probabilities = [value / total for value in exponents]

    metadata = session.get_modelmeta().custom_metadata_map or {}
    labels_value = metadata.get("labels", "")
    labels = [label.strip() for label in labels_value.split(",") if label.strip()]
    if len(labels) != len(probabilities):
        labels = [f"label_{index}" for index in range(len(probabilities))]

    best_index = max(range(len(probabilities)), key=lambda index: (probabilities[index], -index))
    result = {
        "schema": RESULT_SCHEMA,
        "document_sha256": hashlib.sha256(document_bytes).hexdigest(),
        "feature_dims": dims,
        "label": labels[best_index],
        "model_sha256": hashlib.sha256(model_bytes).hexdigest(),
        "scores": {
            label: round(probability, 6)
            for label, probability in zip(labels, probabilities)
        },
    }
    payload = json.dumps(
        result,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    sys.stdout.write(payload + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
