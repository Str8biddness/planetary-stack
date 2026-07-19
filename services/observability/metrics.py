"""Bounded in-process metrics registry (counters + gauges).

A deliberately small, dependency-free registry for local observability.  Its
one non-obvious job is to *stay bounded*: an unbounded label space is a memory
and cardinality hazard (a classic metrics footgun), so the registry caps both
the number of distinct metric names and the number of distinct label-value
series per metric.  Exceeding a cap raises :class:`CardinalityLimitError`
rather than silently growing.

``snapshot()`` returns a plain, JSON-safe ``dict`` so callers can serialize or
diff it without touching registry internals.  All mutation is guarded by a lock
so the registry is safe to share across threads.
"""

from __future__ import annotations

from collections.abc import Mapping
from threading import RLock

__all__ = [
    "CardinalityLimitError",
    "MetricsError",
    "MetricsRegistry",
]

_DEFAULT_MAX_METRICS = 128
_DEFAULT_MAX_SERIES_PER_METRIC = 64
_MAX_LABEL_KEYS = 8
_MAX_NAME_CHARS = 128
_MAX_LABEL_CHARS = 128


class MetricsError(Exception):
    """Base class for metrics registry errors."""


class CardinalityLimitError(MetricsError):
    """Raised when adding a metric or series would exceed a cardinality cap."""


def _validate_name(name: str) -> None:
    if not isinstance(name, str) or not name:
        raise MetricsError("metric name must be a non-empty string")
    if len(name) > _MAX_NAME_CHARS:
        raise MetricsError("metric name exceeds max length")


def _series_key(labels: Mapping[str, str] | None) -> tuple[tuple[str, str], ...]:
    """Normalize labels into a hashable, order-independent series key."""

    if not labels:
        return ()
    if not isinstance(labels, Mapping):
        raise MetricsError("labels must be a mapping")
    if len(labels) > _MAX_LABEL_KEYS:
        raise CardinalityLimitError(
            f"metric has {len(labels)} label keys; max is {_MAX_LABEL_KEYS}"
        )
    items: list[tuple[str, str]] = []
    for key, value in labels.items():
        if not isinstance(key, str) or not key:
            raise MetricsError("label keys must be non-empty strings")
        if not isinstance(value, str):
            raise MetricsError("label values must be strings")
        if len(key) > _MAX_LABEL_CHARS or len(value) > _MAX_LABEL_CHARS:
            raise MetricsError("label key/value exceeds max length")
        items.append((key, value))
    items.sort()
    return tuple(items)


class _Metric:
    __slots__ = ("kind", "series")

    def __init__(self, kind: str) -> None:
        self.kind = kind  # "counter" or "gauge"
        self.series: dict[tuple[tuple[str, str], ...], float] = {}


class MetricsRegistry:
    """A thread-safe, bounded counter/gauge registry.

    Parameters
    ----------
    max_metrics:
        Maximum number of distinct metric names.
    max_series_per_metric:
        Maximum number of distinct label-value series stored per metric name.
    """

    def __init__(
        self,
        *,
        max_metrics: int = _DEFAULT_MAX_METRICS,
        max_series_per_metric: int = _DEFAULT_MAX_SERIES_PER_METRIC,
    ) -> None:
        if max_metrics < 1 or max_series_per_metric < 1:
            raise MetricsError("cardinality caps must be >= 1")
        self._max_metrics = max_metrics
        self._max_series = max_series_per_metric
        self._metrics: dict[str, _Metric] = {}
        self._lock = RLock()

    # -- internal ------------------------------------------------------------

    def _metric(self, name: str, kind: str) -> _Metric:
        metric = self._metrics.get(name)
        if metric is None:
            if len(self._metrics) >= self._max_metrics:
                raise CardinalityLimitError(
                    f"metric registry full ({self._max_metrics} names); "
                    f"refusing to register {name!r}"
                )
            metric = _Metric(kind)
            self._metrics[name] = metric
        elif metric.kind != kind:
            raise MetricsError(
                f"metric {name!r} already registered as {metric.kind}, not {kind}"
            )
        return metric

    def _series_slot(
        self,
        metric: _Metric,
        name: str,
        key: tuple[tuple[str, str], ...],
    ) -> None:
        if key not in metric.series and len(metric.series) >= self._max_series:
            raise CardinalityLimitError(
                f"metric {name!r} reached its series cap ({self._max_series}); "
                "refusing new label combination"
            )

    # -- counters ------------------------------------------------------------

    def increment(
        self,
        name: str,
        value: float = 1.0,
        labels: Mapping[str, str] | None = None,
    ) -> float:
        """Add ``value`` (must be >= 0) to a counter series; return the total."""

        _validate_name(name)
        if value < 0:
            raise MetricsError("counters cannot decrease")
        key = _series_key(labels)
        with self._lock:
            metric = self._metric(name, "counter")
            self._series_slot(metric, name, key)
            metric.series[key] = metric.series.get(key, 0.0) + float(value)
            return metric.series[key]

    # -- gauges --------------------------------------------------------------

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Mapping[str, str] | None = None,
    ) -> float:
        """Set a gauge series to ``value``; return it."""

        _validate_name(name)
        key = _series_key(labels)
        with self._lock:
            metric = self._metric(name, "gauge")
            self._series_slot(metric, name, key)
            metric.series[key] = float(value)
            return metric.series[key]

    # -- introspection -------------------------------------------------------

    def series_count(self, name: str) -> int:
        """Number of distinct series stored for ``name`` (0 if absent)."""

        with self._lock:
            metric = self._metrics.get(name)
            return 0 if metric is None else len(metric.series)

    def snapshot(self) -> dict[str, object]:
        """Return a plain, JSON-safe copy of the current registry state.

        Shape::

            {
              "metric_name": {
                "kind": "counter" | "gauge",
                "series": [
                  {"labels": {"k": "v", ...}, "value": <float>},
                  ...
                ]
              },
              ...
            }
        """

        with self._lock:
            out: dict[str, object] = {}
            for name, metric in self._metrics.items():
                series = [
                    {"labels": dict(key), "value": value}
                    for key, value in sorted(metric.series.items())
                ]
                out[name] = {"kind": metric.kind, "series": series}
            return out
