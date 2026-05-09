"""
SecurityAgent — Central Cybersecurity Orchestrator for Synthesus 4.0

Ties together Breach, ImmuneSystem, Baseliner, GhostNet, SecurityTools,
and AlertStore into a unified security operations layer with scheduled
scanning and real-time threat response.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SecurityAgent:
    """
    The main cybersecurity agent orchestrator.

    Coordinates all security subsystems and manages scan scheduling,
    alert generation, and threat aggregation.
    """

    def __init__(self):
        # Core subsystems
        from core.tools.alert_store import AlertStore
        from core.tools.immune_system import ImmuneSystem
        from core.tools.baseliner import Baseliner
        from core.tools.security import SecurityTools
        from core.tools.ghost_net import GhostNetNode

        self.alert_store = AlertStore()
        self.immune_system = ImmuneSystem()
        self.baseliner = Baseliner()
        self.security_tools = SecurityTools()
        self.ghost_net = GhostNetNode()

        # Breach engine (lazy-loaded to avoid heavy imports at startup)
        self._breach_engine = None
        self._brute_simulator = None

        # State
        self._scanning = False
        self._scheduler_task: Optional[asyncio.Task] = None
        self._last_scan_time: Optional[float] = None
        self._scan_interval_seconds: int = 300  # 5 minutes default
        self._started = False

        logger.info("SecurityAgent initialized with all subsystems.")

    def start(self):
        """Start background services (GhostNet, scheduled scanning)."""
        if self._started:
            return
        self._started = True
        self.ghost_net.start()
        logger.info("SecurityAgent started.")

    def stop(self):
        """Stop background services."""
        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
        self.ghost_net.stop()
        self._started = False
        logger.info("SecurityAgent stopped.")

    # ─── Lazy Loaders ────────────────────────────────────────────────

    def _get_breach_engine(self):
        if self._breach_engine is None:
            from core.breach.breach_engine import BreachEngine
            self._breach_engine = BreachEngine()
        return self._breach_engine

    def _get_brute_simulator(self):
        if self._brute_simulator is None:
            from core.breach.brute_simulator import BruteForceSimulator
            self._brute_simulator = BruteForceSimulator()
        return self._brute_simulator

    # ─── Full Scan ───────────────────────────────────────────────────

    async def run_full_scan(self) -> Dict[str, Any]:
        """
        Execute a comprehensive security scan:
        1. System audit (ports, processes, OS info)
        2. Immune system integrity check
        3. Baseline anomaly comparison
        4. GhostNet threat ingestion

        Generates alerts for any findings and records the scan.
        """
        if self._scanning:
            return {"status": "already_scanning"}

        self._scanning = True
        scan_start = datetime.utcnow()
        t0 = time.time()
        findings = []

        try:
            # 1. System Audit
            logger.info("SecurityAgent: Running system audit...")
            audit_result = await self.security_tools.system_audit()
            audit_data = audit_result.get("audit", {})

            # Parse listening ports for baseline
            ports = []
            processes = []
            if isinstance(audit_data.get("listening_ports"), list):
                for entry in audit_data["listening_ports"]:
                    if isinstance(entry, dict):
                        try:
                            addr = entry.get("local_addr", "")
                            port = int(addr.split(":")[-1]) if ":" in addr else 0
                            if port:
                                ports.append(port)
                        except (ValueError, IndexError):
                            pass
                    elif isinstance(entry, str):
                        # Windows format: parse port from netstat output
                        parts = entry.split()
                        for part in parts:
                            if ":" in part:
                                try:
                                    port = int(part.split(":")[-1])
                                    if port:
                                        ports.append(port)
                                except (ValueError, IndexError):
                                    pass

            if isinstance(audit_data.get("running_processes"), list):
                for proc in audit_data["running_processes"]:
                    if isinstance(proc, dict):
                        processes.append(proc.get("name", ""))

            # 2. Baseline comparison
            self.baseliner.record_sample(ports, processes)

            # Check for port anomalies
            for port in ports:
                if self.baseliner.is_anomaly(port=port):
                    finding = f"Anomalous port detected: {port}"
                    findings.append(finding)
                    self.alert_store.create_alert(
                        severity="medium",
                        source="baseliner",
                        title=f"Anomalous Port: {port}",
                        description=f"Port {port} was found open but appears in less than 5% of baseline samples.",
                        metadata={"port": port},
                    )

            # Check for process anomalies
            for proc_name in processes:
                if proc_name and self.baseliner.is_anomaly(process=proc_name):
                    finding = f"Anomalous process detected: {proc_name}"
                    findings.append(finding)
                    self.alert_store.create_alert(
                        severity="low",
                        source="baseliner",
                        title=f"Anomalous Process: {proc_name}",
                        description=f"Process '{proc_name}' appears in less than 5% of baseline samples.",
                        metadata={"process": proc_name},
                    )

            # 3. Immune System integrity check
            logger.info("SecurityAgent: Running integrity check...")
            anomalies = self.immune_system.check_integrity()
            for anomaly in anomalies:
                findings.append(anomaly)
                severity = "critical" if "COMPROMISED" in anomaly else "high"
                self.alert_store.create_alert(
                    severity=severity,
                    source="immune_system",
                    title="File Integrity Violation",
                    description=anomaly,
                    metadata={"raw": anomaly},
                )

            # 4. GhostNet threat ingestion
            p2p_threats = self.ghost_net.get_recent_external_threats()
            for threat in p2p_threats:
                findings.append(f"GhostNet: {threat}")
                self.alert_store.create_alert(
                    severity="medium",
                    source="ghostnet",
                    title=f"P2P Threat: {threat}",
                    description=f"Threat received from GhostNet mesh: {threat}",
                    metadata={"threat_key": threat},
                )

            elapsed_ms = (time.time() - t0) * 1000
            self._last_scan_time = time.time()

            # Record the scan
            self.alert_store.record_scan(
                scan_type="full",
                started_at=scan_start,
                findings_count=len(findings),
                result_data={
                    "audit": audit_data,
                    "findings": findings,
                    "elapsed_ms": round(elapsed_ms, 1),
                    "ports_scanned": len(ports),
                    "processes_scanned": len(processes),
                },
            )

            logger.info(f"SecurityAgent: Full scan complete in {elapsed_ms:.0f}ms — {len(findings)} findings.")

            return {
                "status": "complete",
                "findings_count": len(findings),
                "findings": findings,
                "elapsed_ms": round(elapsed_ms, 1),
                "audit": audit_data,
            }

        except Exception as e:
            logger.error(f"SecurityAgent full scan failed: {e}")
            return {"status": "error", "error": str(e)}
        finally:
            self._scanning = False

    # ─── Breach Exercise ─────────────────────────────────────────────

    async def run_breach_exercise(
        self, target_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Run a Breach red-team exercise and generate alerts for findings."""
        t0 = time.time()
        scan_start = datetime.utcnow()
        engine = self._get_breach_engine()

        config = target_config or {
            "type": "self_assessment",
            "services": [],
            "debug_mode": False,
        }

        try:
            vectors = engine.scan_attack_surface(config)

            for vector in vectors:
                self.alert_store.create_alert(
                    severity=vector.severity.value,
                    source="breach",
                    title=f"Attack Vector: {vector.name}",
                    description=vector.description,
                    metadata=vector.to_dict(),
                )

            elapsed_ms = (time.time() - t0) * 1000

            self.alert_store.record_scan(
                scan_type="breach",
                started_at=scan_start,
                findings_count=len(vectors),
                result_data={
                    "vectors": [v.to_dict() for v in vectors],
                    "elapsed_ms": round(elapsed_ms, 1),
                },
            )

            return {
                "status": "complete",
                "vectors_found": len(vectors),
                "vectors": [v.to_dict() for v in vectors],
                "elapsed_ms": round(elapsed_ms, 1),
            }
        except Exception as e:
            logger.error(f"Breach exercise failed: {e}")
            return {"status": "error", "error": str(e)}

    # ─── Brute-Force Simulation ──────────────────────────────────────

    async def run_brute_simulation(
        self, pattern: str = "dictionary", duration: int = 10, rps: float = 5.0
    ) -> Dict[str, Any]:
        """Run a brute-force credential pressure simulation."""
        from core.breach.brute_simulator import CredentialPressureConfig, AttackPattern

        pattern_map = {
            "dictionary": AttackPattern.DICTIONARY,
            "spraying": AttackPattern.SPRAYING,
            "stuffing": AttackPattern.CREDENTIAL_STUFFING,
            "timing": AttackPattern.ADAPTIVE_TIMING,
        }

        sim = self._get_brute_simulator()
        config = CredentialPressureConfig(
            pattern=pattern_map.get(pattern, AttackPattern.DICTIONARY),
            requests_per_second=rps,
            duration_seconds=duration,
        )

        try:
            result = await sim.run_simulation(config)

            if result.detected_pattern:
                self.alert_store.create_alert(
                    severity="info",
                    source="breach",
                    title=f"Brute-Force Simulation: {result.detected_pattern}",
                    description=f"Simulation completed with {result.total_attempts} attempts. Pattern detected: {result.detected_pattern}",
                    metadata={"pattern": result.detected_pattern, "attempts": result.total_attempts},
                )

            return {
                "status": "complete",
                "total_attempts": result.total_attempts,
                "detected_pattern": result.detected_pattern,
                "timing_anomalies": len(result.timing_anomalies),
                "avg_response_time_ms": round(result.avg_response_time_ms, 2),
            }
        except Exception as e:
            logger.error(f"Brute simulation failed: {e}")
            return {"status": "error", "error": str(e)}

    # ─── Scheduled Scanning ──────────────────────────────────────────

    async def start_scheduled_scanning(self, interval_seconds: int = 300):
        """Start a background loop that runs full scans periodically."""
        self._scan_interval_seconds = interval_seconds
        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()

        async def _loop():
            while True:
                try:
                    await asyncio.sleep(self._scan_interval_seconds)
                    logger.info("SecurityAgent: Scheduled scan starting...")
                    await self.run_full_scan()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Scheduled scan error: {e}")
                    await asyncio.sleep(30)

        self._scheduler_task = asyncio.create_task(_loop())
        logger.info(f"SecurityAgent: Scheduled scanning started (every {interval_seconds}s).")

    # ─── Dashboard State ─────────────────────────────────────────────

    def get_dashboard_state(self) -> Dict[str, Any]:
        """Get aggregated state for the security dashboard."""
        alert_stats = self.alert_store.get_stats()
        recent_alerts = self.alert_store.get_alerts(limit=20)
        recent_scans = self.alert_store.get_recent_scans(limit=5)
        threats = self.ghost_net.get_recent_external_threats()

        # Determine overall status
        critical_count = alert_stats.get("by_severity", {}).get("critical", 0)
        high_count = alert_stats.get("by_severity", {}).get("high", 0)
        active_count = alert_stats.get("active", 0)

        if critical_count > 0:
            overall_status = "critical"
        elif high_count > 0:
            overall_status = "warning"
        elif active_count > 0:
            overall_status = "monitoring"
        else:
            overall_status = "secure"

        return {
            "overall_status": overall_status,
            "alert_stats": alert_stats,
            "recent_alerts": recent_alerts,
            "recent_scans": recent_scans,
            "ghostnet_threats": threats,
            "last_scan_time": self._last_scan_time,
            "scan_interval_seconds": self._scan_interval_seconds,
            "is_scanning": self._scanning,
            "subsystems": {
                "immune_system": "active",
                "baseliner": f"samples={self.baseliner.sample_count}",
                "ghostnet": "active" if self.ghost_net.running else "stopped",
                "breach_engine": "loaded" if self._breach_engine else "standby",
            },
        }

    def get_threat_feed(self) -> List[Dict[str, Any]]:
        """Get combined threat feed from all sources."""
        threats = []

        # GhostNet threats
        for threat_key in self.ghost_net.get_recent_external_threats():
            threats.append({
                "source": "ghostnet",
                "threat": threat_key,
                "severity": "medium",
            })

        # Recent critical/high alerts
        critical_alerts = self.alert_store.get_alerts(severity="critical", limit=10)
        high_alerts = self.alert_store.get_alerts(severity="high", limit=10)
        for alert in critical_alerts + high_alerts:
            threats.append({
                "source": alert["source"],
                "threat": alert["title"],
                "severity": alert["severity"],
                "created_at": alert["created_at"],
            })

        return threats
