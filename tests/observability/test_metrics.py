"""Metrics registry: counters, gauges, bounded cardinality, snapshot shape."""

from __future__ import annotations

import pytest

from services.observability.metrics import (
    CardinalityLimitError,
    MetricsError,
    MetricsRegistry,
)


def test_counter_accumulates() -> None:
    reg = MetricsRegistry()
    assert reg.increment("jobs_total") == 1.0
    assert reg.increment("jobs_total", 4) == 5.0
    snap = reg.snapshot()
    assert snap["jobs_total"]["kind"] == "counter"
    assert snap["jobs_total"]["series"] == [{"labels": {}, "value": 5.0}]


def test_counter_rejects_negative() -> None:
    reg = MetricsRegistry()
    with pytest.raises(MetricsError):
        reg.increment("jobs_total", -1)


def test_gauge_sets_and_overwrites() -> None:
    reg = MetricsRegistry()
    reg.set_gauge("queue_depth", 3)
    assert reg.set_gauge("queue_depth", 7) == 7.0
    snap = reg.snapshot()
    assert snap["queue_depth"]["kind"] == "gauge"
    assert snap["queue_depth"]["series"] == [{"labels": {}, "value": 7.0}]


def test_counter_and_gauge_name_collision_rejected() -> None:
    reg = MetricsRegistry()
    reg.increment("thing")
    with pytest.raises(MetricsError):
        reg.set_gauge("thing", 1)


def test_labels_produce_distinct_series() -> None:
    reg = MetricsRegistry()
    reg.increment("jobs_total", labels={"state": "completed"})
    reg.increment("jobs_total", labels={"state": "failed"})
    reg.increment("jobs_total", labels={"state": "completed"})
    assert reg.series_count("jobs_total") == 2
    # Label order does not create a new series.
    reg.increment("http", labels={"a": "1", "b": "2"})
    reg.increment("http", labels={"b": "2", "a": "1"})
    assert reg.series_count("http") == 1


def test_series_cardinality_is_bounded() -> None:
    reg = MetricsRegistry(max_series_per_metric=4)
    for i in range(4):
        reg.increment("req", labels={"id": str(i)})
    assert reg.series_count("req") == 4
    with pytest.raises(CardinalityLimitError):
        reg.increment("req", labels={"id": "overflow"})
    # An existing series can still be updated after the cap is reached.
    assert reg.increment("req", labels={"id": "0"}) == 2.0


def test_metric_name_cardinality_is_bounded() -> None:
    reg = MetricsRegistry(max_metrics=3)
    for i in range(3):
        reg.increment(f"m{i}")
    with pytest.raises(CardinalityLimitError):
        reg.increment("m_overflow")


def test_too_many_label_keys_rejected() -> None:
    reg = MetricsRegistry()
    labels = {f"k{i}": "v" for i in range(9)}
    with pytest.raises(CardinalityLimitError):
        reg.increment("m", labels=labels)


def test_non_string_label_value_rejected() -> None:
    reg = MetricsRegistry()
    with pytest.raises(MetricsError):
        reg.increment("m", labels={"state": 5})  # type: ignore[dict-item]


def test_snapshot_is_plain_and_isolated() -> None:
    reg = MetricsRegistry()
    reg.increment("jobs_total", labels={"state": "ok"})
    snap = reg.snapshot()
    assert isinstance(snap, dict)
    # Mutating the snapshot must not affect the registry.
    snap["jobs_total"]["series"].append("garbage")
    fresh = reg.snapshot()
    assert fresh["jobs_total"]["series"] == [
        {"labels": {"state": "ok"}, "value": 1.0}
    ]


def test_invalid_caps_rejected() -> None:
    with pytest.raises(MetricsError):
        MetricsRegistry(max_metrics=0)
    with pytest.raises(MetricsError):
        MetricsRegistry(max_series_per_metric=0)


def test_empty_name_rejected() -> None:
    reg = MetricsRegistry()
    with pytest.raises(MetricsError):
        reg.increment("")
