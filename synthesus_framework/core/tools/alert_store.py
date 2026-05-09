"""
AlertStore — Persistent Security Alert Management for Ghostkey

SQLite-backed alert storage with lifecycle management, deduplication,
and severity-based querying. Foundation of the cybersecurity agent.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependency at module load
_db_module = None


def _get_db():
    """Lazy-load database module."""
    global _db_module
    if _db_module is None:
        from api.database import SessionLocal, SecurityAlert, ScanResult
        _db_module = {
            "SessionLocal": SessionLocal,
            "SecurityAlert": SecurityAlert,
            "ScanResult": ScanResult,
        }
    return _db_module


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


class AlertStore:
    """
    Persistent alert store backed by SQLite.

    Provides create, query, lifecycle transitions, deduplication,
    and summary statistics for the security dashboard.
    """

    def __init__(self):
        logger.info("AlertStore initialized.")

    # ─── Create ──────────────────────────────────────────────────────

    def create_alert(
        self,
        severity: str,
        source: str,
        title: str,
        description: str,
        metadata: Optional[Dict[str, Any]] = None,
        deduplicate: bool = True,
        dedup_window_minutes: int = 5,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new security alert. Returns the alert dict or None if deduplicated.

        Args:
            severity: critical, high, medium, low, info
            source: immune_system, baseliner, breach, ghostnet, scan, audit
            title: Short alert title
            description: Detailed description
            metadata: Arbitrary JSON-safe extra data
            deduplicate: If True, skip if identical title+source exists within window
            dedup_window_minutes: Dedup window in minutes
        """
        db_mod = _get_db()
        db = db_mod["SessionLocal"]()
        SecurityAlert = db_mod["SecurityAlert"]

        try:
            # Deduplication check
            if deduplicate:
                cutoff = datetime.utcnow() - timedelta(minutes=dedup_window_minutes)
                existing = (
                    db.query(SecurityAlert)
                    .filter(
                        SecurityAlert.title == title,
                        SecurityAlert.source == source,
                        SecurityAlert.created_at >= cutoff,
                        SecurityAlert.status.in_(["new", "acknowledged"]),
                    )
                    .first()
                )
                if existing:
                    logger.debug(f"Alert deduplicated: {title}")
                    return None

            alert = SecurityAlert(
                severity=severity.lower(),
                source=source,
                title=title,
                description=description,
                metadata_json=metadata or {},
                status="new",
            )
            db.add(alert)
            db.commit()
            db.refresh(alert)

            result = self._alert_to_dict(alert)
            logger.info(f"Alert created: [{severity.upper()}] {title}")
            return result
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create alert: {e}")
            return None
        finally:
            db.close()

    # ─── Query ───────────────────────────────────────────────────────

    def get_alerts(
        self,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Query alerts with optional filters, ordered by severity then recency."""
        db_mod = _get_db()
        db = db_mod["SessionLocal"]()
        SecurityAlert = db_mod["SecurityAlert"]

        try:
            query = db.query(SecurityAlert)

            if severity:
                query = query.filter(SecurityAlert.severity == severity.lower())
            if status:
                query = query.filter(SecurityAlert.status == status.lower())
            if source:
                query = query.filter(SecurityAlert.source == source)

            alerts = (
                query.order_by(SecurityAlert.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )

            result = [self._alert_to_dict(a) for a in alerts]
            # Sort by severity order then recency
            result.sort(key=lambda a: (SEVERITY_ORDER.get(a["severity"], 99),))
            return result
        except Exception as e:
            logger.error(f"Failed to query alerts: {e}")
            return []
        finally:
            db.close()

    def get_alert(self, alert_id: int) -> Optional[Dict[str, Any]]:
        """Get a single alert by ID."""
        db_mod = _get_db()
        db = db_mod["SessionLocal"]()
        SecurityAlert = db_mod["SecurityAlert"]

        try:
            alert = db.query(SecurityAlert).filter(SecurityAlert.id == alert_id).first()
            return self._alert_to_dict(alert) if alert else None
        finally:
            db.close()

    # ─── Lifecycle ───────────────────────────────────────────────────

    def acknowledge_alert(self, alert_id: int) -> bool:
        """Transition alert from 'new' to 'acknowledged'."""
        return self._transition(alert_id, "acknowledged", "acknowledged_at")

    def resolve_alert(self, alert_id: int) -> bool:
        """Transition alert to 'resolved'."""
        return self._transition(alert_id, "resolved", "resolved_at")

    def archive_alert(self, alert_id: int) -> bool:
        """Transition alert to 'archived'."""
        return self._transition(alert_id, "archived", None)

    def _transition(self, alert_id: int, new_status: str, timestamp_field: Optional[str]) -> bool:
        db_mod = _get_db()
        db = db_mod["SessionLocal"]()
        SecurityAlert = db_mod["SecurityAlert"]

        try:
            alert = db.query(SecurityAlert).filter(SecurityAlert.id == alert_id).first()
            if not alert:
                return False
            alert.status = new_status
            if timestamp_field:
                setattr(alert, timestamp_field, datetime.utcnow())
            db.commit()
            logger.info(f"Alert {alert_id} → {new_status}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to transition alert {alert_id}: {e}")
            return False
        finally:
            db.close()

    # ─── Statistics ──────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get alert counts grouped by severity and status."""
        db_mod = _get_db()
        db = db_mod["SessionLocal"]()
        SecurityAlert = db_mod["SecurityAlert"]

        try:
            all_alerts = db.query(SecurityAlert).all()
            by_severity = {}
            by_status = {}
            for a in all_alerts:
                by_severity[a.severity] = by_severity.get(a.severity, 0) + 1
                by_status[a.status] = by_status.get(a.status, 0) + 1

            return {
                "total": len(all_alerts),
                "by_severity": by_severity,
                "by_status": by_status,
                "active": by_status.get("new", 0) + by_status.get("acknowledged", 0),
            }
        except Exception as e:
            logger.error(f"Failed to get alert stats: {e}")
            return {"total": 0, "by_severity": {}, "by_status": {}, "active": 0}
        finally:
            db.close()

    # ─── Scan Results ────────────────────────────────────────────────

    def record_scan(
        self,
        scan_type: str,
        started_at: datetime,
        findings_count: int,
        result_data: Dict[str, Any],
    ) -> Optional[int]:
        """Record a completed scan result. Returns the scan ID."""
        db_mod = _get_db()
        db = db_mod["SessionLocal"]()
        ScanResult = db_mod["ScanResult"]

        try:
            scan = ScanResult(
                scan_type=scan_type,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                findings_count=findings_count,
                result_data=result_data,
            )
            db.add(scan)
            db.commit()
            db.refresh(scan)
            logger.info(f"Scan recorded: {scan_type} with {findings_count} findings")
            return scan.id
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to record scan: {e}")
            return None
        finally:
            db.close()

    def get_recent_scans(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent scan results."""
        db_mod = _get_db()
        db = db_mod["SessionLocal"]()
        ScanResult = db_mod["ScanResult"]

        try:
            scans = (
                db.query(ScanResult)
                .order_by(ScanResult.completed_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": s.id,
                    "scan_type": s.scan_type,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                    "findings_count": s.findings_count,
                    "result_data": s.result_data or {},
                }
                for s in scans
            ]
        except Exception as e:
            logger.error(f"Failed to get recent scans: {e}")
            return []
        finally:
            db.close()

    # ─── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _alert_to_dict(alert) -> Dict[str, Any]:
        return {
            "id": alert.id,
            "severity": alert.severity,
            "source": alert.source,
            "title": alert.title,
            "description": alert.description,
            "status": alert.status,
            "metadata": alert.metadata_json or {},
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
            "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        }
