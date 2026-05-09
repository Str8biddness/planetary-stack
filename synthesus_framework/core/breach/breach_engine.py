"""
BreachEngine - Red Team Adversarial Discovery Engine

Implements the Clinical Adversary persona using Abductive Reasoning
to identify theoretical attack surfaces and architectural flaws.

This is Phase 2 of the Red/Blue Team Architecture as defined in AGENTS.md.
"""

import logging
import json
import hashlib
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class AttackSeverity(Enum):
    CRITICAL = "critical"      # Remote code execution, privilege escalation
    HIGH = "high"              # Data exfiltration, authentication bypass
    MEDIUM = "medium"          # Information disclosure, DoS
    LOW = "low"                # Minor misconfigurations
    INFO = "info"              # Reconnaissance data


class AttackCategory(Enum):
    MEMORY_CORRUPTION = "memory_corruption"
    INJECTION = "injection"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    CONFIGURATION = "configuration"
    LOGIC_FLAW = "logic_flaw"
    SIDE_CHANNEL = "side_channel"


@dataclass
class AttackVector:
    """Structured representation of a discovered attack vector."""
    id: str = ""
    name: str = ""
    description: str = ""
    category: AttackCategory = AttackCategory.LOGIC_FLAW
    severity: AttackSeverity = AttackSeverity.INFO
    target_component: str = "unknown"
    prerequisites: List[str] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)
    indicators: List[str] = field(default_factory=list)
    cvss_score: Optional[float] = None
    mitigations: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    discovered_at: Optional[float] = None
    
    def __post_init__(self):
        if self.discovered_at is None:
            import time
            self.discovered_at = time.time()
        if not self.id:
            # Generate deterministic ID from name and description
            content = f"{self.name}:{self.description}:{self.target_component}"
            self.id = hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "severity": self.severity.value,
            "target_component": self.target_component,
            "prerequisites": self.prerequisites,
            "steps": self.steps,
            "indicators": self.indicators,
            "cvss_score": self.cvss_score,
            "mitigations": self.mitigations,
            "references": self.references,
            "discovered_at": self.discovered_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AttackVector":
        return cls(
            id=data.get("id", ""),
            name=data["name"],
            description=data["description"],
            category=AttackCategory(data["category"]),
            severity=AttackSeverity(data["severity"]),
            target_component=data["target_component"],
            prerequisites=data.get("prerequisites", []),
            steps=data.get("steps", []),
            indicators=data.get("indicators", []),
            cvss_score=data.get("cvss_score"),
            mitigations=data.get("mitigations", []),
            references=data.get("references", []),
            discovered_at=data.get("discovered_at"),
        )


class AbductiveAnalyzer:
    """
    Abductive Reasoning Engine for Breach.
    
    Works backward from observed symptoms (crashes, anomalies) to find
    the most likely causes and attack paths.
    """
    
    def __init__(self):
        self.causal_rules: Dict[str, List[str]] = {
            # symptom -> possible causes
            "segmentation_fault": ["buffer_overflow", "use_after_free", "null_dereference"],
            "heap_corruption": ["double_free", "heap_overflow", "use_after_free"],
            "authentication_failure": ["credential_stuffing", "brute_force", "timing_attack"],
            "high_cpu_anomaly": ["infinite_loop", "cryptomining", "denial_of_service"],
            "unexpected_network_traffic": ["data_exfiltration", "command_control", "reconnaissance"],
            "privilege_escalation": ["sudo_misconfig", "suid_binary", "kernel_exploit"],
        }
        self.hypothesis_confidence: Dict[str, float] = {}
    
    def add_causal_rule(self, symptom: str, causes: List[str]):
        """Add a new causal relationship rule."""
        self.causal_rules[symptom] = causes
    
    def work_backward(self, observed_symptoms: List[str], context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Given observed symptoms, work backward to find likely attack vectors.
        
        Args:
            observed_symptoms: List of observed anomaly symptoms
            context: Additional context (logs, system state, etc.)
        
        Returns:
            List of hypotheses with confidence scores
        """
        hypotheses = []
        
        for symptom in observed_symptoms:
            possible_causes = self.causal_rules.get(symptom, [])
            
            for cause in possible_causes:
                # Calculate confidence based on context evidence
                confidence = self._score_hypothesis(cause, symptom, context)
                
                hypotheses.append({
                    "symptom": symptom,
                    "hypothesized_cause": cause,
                    "confidence": confidence,
                    "explanation": self._generate_explanation(cause, symptom, context),
                    "supporting_evidence": self._find_evidence(cause, context),
                })
        
        # Sort by confidence descending
        hypotheses.sort(key=lambda x: x["confidence"], reverse=True)
        return hypotheses
    
    def _score_hypothesis(self, cause: str, symptom: str, context: Dict[str, Any]) -> float:
        """Score a hypothesis based on available evidence."""
        score = 0.5  # Base confidence
        
        # Check for supporting log patterns
        logs = context.get("logs", [])
        for log in logs:
            log_text = json.dumps(log).lower()
            if cause.replace("_", " ") in log_text:
                score += 0.15
            if symptom.replace("_", " ") in log_text:
                score += 0.1
        
        # Check system state indicators
        state = context.get("system_state", {})
        if "memory_pressure" in state and cause in ["buffer_overflow", "heap_overflow"]:
            score += 0.1
        if "auth_failures" in state and cause in ["credential_stuffing", "brute_force"]:
            score += 0.2
        
        # Cap at 0.95 (never 100% certain in abductive reasoning)
        return min(score, 0.95)
    
    def _generate_explanation(self, cause: str, symptom: str, context: Dict[str, Any]) -> str:
        """Generate a human-readable explanation of the hypothesis."""
        explanations = {
            "buffer_overflow": f"An unchecked buffer write likely caused the {symptom} by overwriting adjacent memory",
            "use_after_free": f"A dangling pointer dereference after memory deallocation triggered the {symptom}",
            "credential_stuffing": f"Automated credential attempts from breached databases caused {symptom}",
            "timing_attack": f"Differential timing in authentication responses suggests {symptom}",
        }
        return explanations.get(cause, f"{cause} is a possible explanation for {symptom}")
    
    def _find_evidence(self, cause: str, context: Dict[str, Any]) -> List[str]:
        """Find specific evidence supporting the hypothesis."""
        evidence = []
        logs = context.get("logs", [])
        
        for log in logs:
            log_str = json.dumps(log)
            if any(indicator in log_str.lower() for indicator in cause.split("_")):
                evidence.append(f"Log entry: {log_str[:200]}")
        
        return evidence[:5]  # Top 5 evidence items


class BreachEngine:
    """
    Core Red Team Engine implementing the Clinical Adversary persona.
    
    Uses Abductive Reasoning to identify attack surfaces and generate
    structured attack vectors for the Blue Team to defend against.
    """
    
    def __init__(self, emulation_tool=None, live_mode: bool = False):
        self.emulation = emulation_tool
        self.live_mode = live_mode
        self.analyzer = AbductiveAnalyzer()
        self.discovered_vectors: Dict[str, AttackVector] = {}
        self.sandbox_results: List[Dict[str, Any]] = []
        
        # Known vulnerable patterns to watch for
        self.vulnerability_catalog = self._load_vulnerability_catalog()
    
    def _load_vulnerability_catalog(self) -> Dict[str, Any]:
        """Load built-in vulnerability patterns."""
        return {
            "buffer_overflow": {
                "indicators": ["strcpy", "gets", "sprintf", "unchecked copy"],
                "severity": AttackSeverity.CRITICAL,
                "category": AttackCategory.MEMORY_CORRUPTION,
            },
            "command_injection": {
                "indicators": ["system(", "popen(", "exec(", "shell=True"],
                "severity": AttackSeverity.CRITICAL,
                "category": AttackCategory.INJECTION,
            },
            "sql_injection": {
                "indicators": ["f-string query", "+ ' SELECT", "format query"],
                "severity": AttackSeverity.HIGH,
                "category": AttackCategory.INJECTION,
            },
            "weak_crypto": {
                "indicators": ["md5", "sha1", "des", "ecb mode"],
                "severity": AttackSeverity.HIGH,
                "category": AttackCategory.CONFIGURATION,
            },
            "privilege_escalation": {
                "indicators": ["setuid", "sudo", "chmod 777", "world writable"],
                "severity": AttackSeverity.HIGH,
                "category": AttackCategory.AUTHORIZATION,
            },
        }
    
    def analyze_crash(self, crash_data: Dict[str, Any]) -> List[AttackVector]:
        """
        Work backward from a crash to identify the attack vector.
        
        Args:
            crash_data: Dict containing crash info (type, logs, stack trace, etc.)
        
        Returns:
            List of likely attack vectors that could have caused the crash
        """
        crash_type = crash_data.get("type", "unknown")
        logs = crash_data.get("logs", [])
        context = crash_data.get("context", {})
        
        # Map crash types to symptoms
        symptom_map = {
            "segfault": "segmentation_fault",
            "sigsegv": "segmentation_fault",
            "heap_error": "heap_corruption",
            "auth_fail": "authentication_failure",
            "cpu_spike": "high_cpu_anomaly",
            "network_anomaly": "unexpected_network_traffic",
        }
        
        symptoms = [symptom_map.get(crash_type, crash_type)]
        
        # Run abductive analysis
        hypotheses = self.analyzer.work_backward(symptoms, {
            "logs": logs,
            "system_state": context,
            "crash_data": crash_data,
        })
        
        # Convert top hypotheses to attack vectors
        vectors = []
        for hyp in hypotheses[:3]:  # Top 3 hypotheses
            vector = AttackVector(
                name=f"Abductive: {hyp['hypothesized_cause']}",
                description=hyp["explanation"],
                category=self._categorize_cause(hyp["hypothesized_cause"]),
                severity=self._severity_for_cause(hyp["hypothesized_cause"]),
                target_component=crash_data.get("component", "unknown"),
                prerequisites=[f"Trigger: {hyp['symptom']}"],
                steps=[f"Induce {hyp['symptom']}", f"Exploit {hyp['hypothesized_cause']}"],
                indicators=hyp["supporting_evidence"],
            )
            self.discovered_vectors[vector.id] = vector
            vectors.append(vector)
        
        logger.info(f"BreachEngine analyzed crash '{crash_type}' and generated {len(vectors)} attack vectors")
        return vectors
    
    def scan_attack_surface(self, target_config: Dict[str, Any]) -> List[AttackVector]:
        """
        Proactively scan for attack surfaces in a target system or sandbox.
        
        Args:
            target_config: Configuration describing the target to analyze
        
        Returns:
            List of discovered attack vectors
        """
        vectors = []
        
        # Check for known vulnerable patterns in target
        target_type = target_config.get("type", "generic")
        exposed_services = target_config.get("services", [])
        
        # Service-based attack surface analysis
        for service in exposed_services:
            service_vectors = self._analyze_service(service)
            vectors.extend(service_vectors)
        
        # Configuration-based analysis
        config_vectors = self._analyze_configuration(target_config)
        vectors.extend(config_vectors)
        
        logger.info(f"BreachEngine scanned attack surface and discovered {len(vectors)} vectors")
        return vectors
    
    def _analyze_service(self, service: Dict[str, Any]) -> List[AttackVector]:
        """Analyze a specific service for attack vectors."""
        vectors = []
        service_name = service.get("name", "unknown")
        port = service.get("port", 0)
        version = service.get("version", "unknown")
        
        # Check for common misconfigurations
        if service.get("authentication") == "none":
            vectors.append(AttackVector(
                name=f"Unauthenticated {service_name} Access",
                description=f"{service_name} on port {port} has no authentication enabled",
                category=AttackCategory.AUTHENTICATION,
                severity=AttackSeverity.CRITICAL,
                target_component=service_name,
                prerequisites=[f"Network access to port {port}"],
                steps=[f"Connect to {service_name}:{port}", "Access without credentials"],
                indicators=[f"Port {port} open without auth"],
                mitigations=["Enable authentication", "Use firewall rules"],
            ))
        
        # Check for default credentials
        if service.get("uses_defaults", False):
            vectors.append(AttackVector(
                name=f"Default Credentials on {service_name}",
                description=f"{service_name} appears to use default/weak credentials",
                category=AttackCategory.AUTHENTICATION,
                severity=AttackSeverity.HIGH,
                target_component=service_name,
                prerequisites=[f"Network access to {service_name}"],
                steps=["Attempt default credential pairs", "Gain authenticated access"],
                mitigations=["Change default passwords", "Implement MFA"],
            ))
        
        return vectors
    
    def _analyze_configuration(self, config: Dict[str, Any]) -> List[AttackVector]:
        """Analyze configuration for security weaknesses."""
        vectors = []
        
        # Check for debug mode in production
        if config.get("debug_mode", False):
            vectors.append(AttackVector(
                name="Debug Mode Enabled",
                description="Target system has debug mode enabled in production",
                category=AttackCategory.CONFIGURATION,
                severity=AttackSeverity.HIGH,
                target_component="system",
                prerequisites=["Access to system"],
                steps=["Access debug endpoints", "Extract sensitive information"],
                indicators=["Debug flags enabled", "Verbose error messages"],
                mitigations=["Disable debug mode in production", "Use environment-specific configs"],
            ))
        
        # Check for exposed sensitive files
        exposed_files = config.get("exposed_files", [])
        sensitive_patterns = [".env", "config.json", "secrets", "key", "password"]
        for file in exposed_files:
            if any(pattern in file.lower() for pattern in sensitive_patterns):
                vectors.append(AttackVector(
                    name=f"Exposed Sensitive File: {file}",
                    description=f"Potentially sensitive file {file} is publicly accessible",
                    category=AttackCategory.CONFIGURATION,
                    severity=AttackSeverity.MEDIUM,
                    target_component="file_system",
                    prerequisites=["Web access to file path"],
                    steps=[f"Request {file}", "Extract sensitive configuration"],
                    mitigations=["Remove sensitive files from public access", "Use .htaccess or equivalent"],
                ))
        
        return vectors
    
    def _categorize_cause(self, cause: str) -> AttackCategory:
        """Map a cause to an attack category."""
        category_map = {
            "buffer_overflow": AttackCategory.MEMORY_CORRUPTION,
            "use_after_free": AttackCategory.MEMORY_CORRUPTION,
            "credential_stuffing": AttackCategory.AUTHENTICATION,
            "brute_force": AttackCategory.AUTHENTICATION,
            "timing_attack": AttackCategory.SIDE_CHANNEL,
        }
        return category_map.get(cause, AttackCategory.LOGIC_FLAW)
    
    def _severity_for_cause(self, cause: str) -> AttackSeverity:
        """Determine severity for a given cause."""
        severity_map = {
            "buffer_overflow": AttackSeverity.CRITICAL,
            "use_after_free": AttackSeverity.CRITICAL,
            "credential_stuffing": AttackSeverity.HIGH,
            "brute_force": AttackSeverity.MEDIUM,
            "timing_attack": AttackSeverity.MEDIUM,
        }
        return severity_map.get(cause, AttackSeverity.LOW)
    
    def get_attack_vectors(self, severity: Optional[AttackSeverity] = None) -> List[AttackVector]:
        """Get all discovered attack vectors, optionally filtered by severity."""
        vectors = list(self.discovered_vectors.values())
        if severity:
            vectors = [v for v in vectors if v.severity == severity]
        return vectors
    
    def export_attack_vectors(self, output_path: str) -> None:
        """Export discovered attack vectors to JSON."""
        data = [v.to_dict() for v in self.discovered_vectors.values()]
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Exported {len(data)} attack vectors to {output_path}")
