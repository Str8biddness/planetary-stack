"""Structured local observability for Planetary Stack (checklist gate F-110).

Two self-contained, owner-confined primitives:

* :mod:`services.observability.audit` — an append-only, owner-only audit log
  that records events as canonical one-line JSON with a stable event ``code``,
  a UTC timestamp, an event category, and a bounded, secret-scrubbed ``detail``
  mapping.  It refuses to persist raw secrets or raw prompt/user content.
* :mod:`services.observability.metrics` — a bounded in-process counter/gauge
  registry whose ``snapshot()`` returns a plain dict and whose label
  cardinality is capped to reject unbounded growth.

Neither module opens a socket, spawns a process, or emits data off-host.
"""

from services.observability.audit import (
    DENYLIST_KEY_SUBSTRINGS,
    AuditLogError,
    AuditReader,
    AuditRecord,
    AuditWriter,
    DetailTooLargeError,
    EventCategory,
    EventCode,
    SecretRedactionError,
    scrub_detail,
)
from services.observability.metrics import (
    CardinalityLimitError,
    MetricsError,
    MetricsRegistry,
)

__all__ = [
    "AuditLogError",
    "AuditReader",
    "AuditRecord",
    "AuditWriter",
    "CardinalityLimitError",
    "DENYLIST_KEY_SUBSTRINGS",
    "DetailTooLargeError",
    "EventCategory",
    "EventCode",
    "MetricsError",
    "MetricsRegistry",
    "SecretRedactionError",
    "scrub_detail",
]
