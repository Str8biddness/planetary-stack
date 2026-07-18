"""Production-shaped useful CPU model profiles for the AIVM executor.

A profile is an operator-owned, fixed :class:`TrustedEntrypoint` plus the
immutable container image that carries the trusted runner.  Manifest text
never becomes argv; the runner, its arguments, and every mount destination
are fixed here, and the workload manifest may only bind admitted
content-addressed artifacts to the fixed mount points.

The first useful profile is bounded ONNX text classification: one admitted
ONNX model artifact plus one admitted UTF-8 document artifact produce one
strict, bounded JSON result on stdout that the executor content-addresses
and persists immutably.  The trusted runner source and its image build
context live in ``services/aivm_profiles/text_classification``.
"""

from __future__ import annotations

from .podman import TrustedEntrypoint

TEXT_CLASSIFICATION_ENTRYPOINT_ID = "aivm.model.text-classify.v1"
TEXT_CLASSIFICATION_RESULT_SCHEMA = "planetary.aivm.result.text-classification.v1"
TEXT_CLASSIFICATION_EXECUTABLE = "/opt/aivm/bin/aivm-text-classify"
TEXT_CLASSIFICATION_MODEL_MOUNT = "/work/input/model.onnx"
TEXT_CLASSIFICATION_DOCUMENT_MOUNT = "/work/input/document.txt"


def text_classification_entrypoint(
    *,
    model_artifact_id: str,
    document_artifact_id: str,
    output_id: str,
) -> TrustedEntrypoint:
    """Return the fixed bounded ONNX text-classification entrypoint.

    The caller only chooses which admitted artifact identifiers are bound to
    the fixed model and document mount points; every path, argument, and the
    result schema stay operator-owned.
    """

    if model_artifact_id == document_artifact_id:
        raise ValueError("model and document artifacts must be distinct")
    mounts = {
        model_artifact_id: TEXT_CLASSIFICATION_MODEL_MOUNT,
        document_artifact_id: TEXT_CLASSIFICATION_DOCUMENT_MOUNT,
    }
    return TrustedEntrypoint(
        entrypoint_id=TEXT_CLASSIFICATION_ENTRYPOINT_ID,
        executable=TEXT_CLASSIFICATION_EXECUTABLE,
        arguments=(
            TEXT_CLASSIFICATION_MODEL_MOUNT,
            TEXT_CLASSIFICATION_DOCUMENT_MOUNT,
        ),
        input_mounts=tuple(sorted(mounts.items())),
        output_id=output_id,
        output_transport="bounded_stdout_json",
        result_schema=TEXT_CLASSIFICATION_RESULT_SCHEMA,
    )
