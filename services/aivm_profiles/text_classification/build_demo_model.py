#!/usr/bin/env python3
"""Build the deterministic demo ONNX classifier for the physical AIVM gate.

The produced model is a real ONNX graph executed by onnxruntime inside the
immutable profile image: ``scores = features @ W + b`` over the runner's
fixed 256-dimension hashing features, with class labels published through
model metadata. Every weight is derived from SHA-256 of a fixed seed, so
the artifact bytes are reproducible from this script alone and the model
digest can be pinned in workload manifests and audit evidence.

Usage: build_demo_model.py <output-path>
"""

from __future__ import annotations

import hashlib
import struct
import sys

FEATURE_DIMS = 256
CLASSES = ("negative", "positive")
SEED = "planetary.aivm.demo.text-classification.v1"


def _unit_float(tag: str, index: int) -> float:
    digest = hashlib.sha256(f"{SEED}:{tag}:{index}".encode("ascii")).digest()
    raw = int.from_bytes(digest[:8], "big") / float(1 << 64)
    return (raw * 2.0) - 1.0


def build() -> bytes:
    import onnx
    from onnx import TensorProto, helper

    weights = [
        _unit_float("weight", index) for index in range(FEATURE_DIMS * len(CLASSES))
    ]
    biases = [_unit_float("bias", index) for index in range(len(CLASSES))]

    weight_tensor = helper.make_tensor(
        "W",
        TensorProto.FLOAT,
        (FEATURE_DIMS, len(CLASSES)),
        struct.pack(f"<{len(weights)}f", *weights),
        raw=True,
    )
    bias_tensor = helper.make_tensor(
        "b",
        TensorProto.FLOAT,
        (len(CLASSES),),
        struct.pack(f"<{len(biases)}f", *biases),
        raw=True,
    )
    graph = helper.make_graph(
        nodes=[
            helper.make_node("MatMul", ["features", "W"], ["projected"]),
            helper.make_node("Add", ["projected", "b"], ["scores"]),
        ],
        name="planetary_demo_text_classifier",
        inputs=[
            helper.make_tensor_value_info(
                "features", TensorProto.FLOAT, (1, FEATURE_DIMS)
            )
        ],
        outputs=[
            helper.make_tensor_value_info(
                "scores", TensorProto.FLOAT, (1, len(CLASSES))
            )
        ],
        initializer=[weight_tensor, bias_tensor],
    )
    model = helper.make_model(
        graph,
        opset_imports=[helper.make_opsetid("", 13)],
        producer_name="planetary-stack",
        doc_string="Deterministic demo text classifier for the AIVM physical gate.",
    )
    model.ir_version = 8
    entry = model.metadata_props.add()
    entry.key = "labels"
    entry.value = ",".join(CLASSES)
    onnx.checker.check_model(model)
    return model.SerializeToString()


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: build_demo_model.py <output-path>", file=sys.stderr)
        return 2
    payload = build()
    with open(sys.argv[1], "wb") as handle:
        handle.write(payload)
    print(hashlib.sha256(payload).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
