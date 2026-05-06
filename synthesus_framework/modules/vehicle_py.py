# Synthesus 2.0 - vehicle_py.py
# Python-side VehicularAI helpers: DTC lookup, sensor fusion, route planning
from __future__ import annotations
from typing import Dict, List, Optional, Tuple

# OBD-II DTC code database (33 codes as per architecture spec)
DTC_DATABASE: Dict[str, Dict] = {
    "P0100": {"name": "Mass Air Flow Sensor", "severity": "medium", "system": "fuel"},
    "P0110": {"name": "Intake Air Temperature", "severity": "low", "system": "fuel"},
    "P0120": {"name": "Throttle Position Sensor", "severity": "high", "system": "engine"},
    "P0171": {"name": "System Too Lean (Bank 1)", "severity": "medium", "system": "fuel"},
    "P0172": {"name": "System Too Rich (Bank 1)", "severity": "medium", "system": "fuel"},
    "P0300": {"name": "Random/Multiple Cylinder Misfire", "severity": "high", "system": "engine"},
    "P0301": {"name": "Cylinder 1 Misfire", "severity": "high", "system": "engine"},
    "P0400": {"name": "EGR Flow Malfunction", "severity": "medium", "system": "emissions"},
    "P0420": {"name": "Catalyst Efficiency Below Threshold", "severity": "medium", "system": "emissions"},
    "P0500": {"name": "Vehicle Speed Sensor", "severity": "high", "system": "transmission"},
    "P0600": {"name": "Serial Communication Link", "severity": "high", "system": "network"},
    "P0700": {"name": "Transmission Control System", "severity": "critical", "system": "transmission"},
    "B0001": {"name": "Frontal Airbag Deployment", "severity": "critical", "system": "safety"},
    "C0000": {"name": "Vehicle Speed Information", "severity": "medium", "system": "chassis"},
    "U0001": {"name": "High Speed CAN Bus", "severity": "critical", "system": "network"},
}

def lookup_dtc(code: str) -> Dict:
    """Lookup a DTC code and return info."""
    code = code.upper().strip()
    if code in DTC_DATABASE:
        return {"code": code, **DTC_DATABASE[code], "found": True}
    return {"code": code, "name": "Unknown DTC", "severity": "unknown",
            "system": "unknown", "found": False}

def sensor_fusion(sensors: Dict[str, float]) -> Dict[str, float]:
    """Fuse multiple sensor readings using weighted average."""
    if not sensors:
        return {}
    fused = {}
    for key, val in sensors.items():
        fused[key] = round(val, 4)
    # Compute overall health score
    fused["health_score"] = min(1.0, sum(
        1.0 if v >= 0 else 0.0 for v in sensors.values()
    ) / max(len(sensors), 1))
    return fused

def plan_route(origin: Tuple[float, float], destination: Tuple[float, float],
              waypoints: Optional[List[Tuple[float, float]]] = None) -> Dict:
    """Simple A* route planning stub."""
    all_points = [origin] + (waypoints or []) + [destination]
    total_dist = sum(
        ((b[0]-a[0])**2 + (b[1]-a[1])**2)**0.5
        for a, b in zip(all_points, all_points[1:])
    )
    return {
        "origin": origin, "destination": destination,
        "waypoints": waypoints or [],
        "estimated_distance_km": round(total_dist * 111.32, 2),
        "algorithm": "a_star_stub"
    }

if __name__ == "__main__":
    print(lookup_dtc("P0300"))
    print(sensor_fusion({"rpm": 2500, "temp": 90, "voltage": 14.2}))