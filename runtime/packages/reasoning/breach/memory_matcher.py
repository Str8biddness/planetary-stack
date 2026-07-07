"""
MemoryPatternMatcher - Sandbox Memory Vulnerability Scanner

Scans EmulationTool sandbox memory for known insecure primitives and
vulnerable library versions. Part of Phase 2 Adversarial Discovery Engine.
"""

import logging
import re
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class VulnType(Enum):
    """Types of memory vulnerabilities detectable."""
    UNSAFE_FUNCTION = "unsafe_function"
    VULNERABLE_LIBRARY = "vulnerable_library"
    INSECURE_PATTERN = "insecure_pattern"
    MEMORY_LEAK = "memory_leak"
    USE_AFTER_FREE = "use_after_free"
    BUFFER_OVERFLOW = "buffer_overflow"


@dataclass
class VulnerabilitySignature:
    """Signature for detecting a specific vulnerability in memory."""
    id: str
    name: str
    vuln_type: VulnType
    patterns: List[str]  # Regex patterns or literal strings to match
    description: str
    severity: str  # critical, high, medium, low
    affected_versions: Optional[str] = None  # Version regex for library vulns
    cve_ids: List[str] = field(default_factory=list)
    
    def matches(self, content: str) -> List[Dict[str, Any]]:
        """Check if this signature matches the given memory content."""
        matches = []
        for pattern in self.patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                matches.append({
                    "pattern": pattern,
                    "match": match.group(0),
                    "position": match.start(),
                    "context": content[max(0, match.start()-50):min(len(content), match.end()+50)],
                })
        return matches


@dataclass
class MemoryMatch:
    """A detected vulnerability match in memory."""
    signature_id: str
    signature_name: str
    vuln_type: VulnType
    severity: str
    host_id: str
    memory_region: str
    matches: List[Dict[str, Any]]
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "signature_id": self.signature_id,
            "signature_name": self.signature_name,
            "vuln_type": self.vuln_type.value,
            "severity": self.severity,
            "host_id": self.host_id,
            "memory_region": self.memory_region,
            "match_count": len(self.matches),
            "matches": self.matches,
            "timestamp": self.timestamp,
        }


class MemoryPatternMatcher:
    """
    Scans sandbox memory for vulnerable patterns and insecure primitives.
    
    This implements the Memory Pattern Matcher from AGENTS.md Phase 2,
    scanning for known insecure primitives (e.g., specific glibc versions,
    unsafe C functions, buffer overflow patterns).
    """
    
    def __init__(self):
        self.signatures: Dict[str, VulnerabilitySignature] = {}
        self._load_builtin_signatures()
    
    def _load_builtin_signatures(self):
        """Load built-in vulnerability signatures."""
        
        # Unsafe C functions
        self.add_signature(VulnerabilitySignature(
            id="unsafe_strcpy",
            name="Unsafe strcpy() usage",
            vuln_type=VulnType.UNSAFE_FUNCTION,
            patterns=[r"\bstrcpy\s*\(", r"strcpy@GLIBC"],
            description="strcpy() does not check buffer bounds, enabling buffer overflow attacks",
            severity="critical",
        ))
        
        self.add_signature(VulnerabilitySignature(
            id="unsafe_gets",
            name="Unsafe gets() usage",
            vuln_type=VulnType.UNSAFE_FUNCTION,
            patterns=[r"\bgets\s*\(", r"gets@GLIBC"],
            description="gets() is inherently unsafe as it cannot check buffer size",
            severity="critical",
        ))
        
        self.add_signature(VulnerabilitySignature(
            id="unsafe_sprintf",
            name="Unsafe sprintf() usage",
            vuln_type=VulnType.UNSAFE_FUNCTION,
            patterns=[r"\bsprintf\s*\([^,]+,\s*[^\"]", r"sprintf@GLIBC"],
            description="sprintf() without format string checking can cause buffer overflow",
            severity="high",
        ))
        
        # Memory management issues
        self.add_signature(VulnerabilitySignature(
            id="use_after_free_pattern",
            name="Potential Use-After-Free pattern",
            vuln_type=VulnType.USE_AFTER_FREE,
            patterns=[r"free\s*\([^)]+\).*\1", r"\bfree\b.*\n.*\b\w+\[.*\]"],
            description="Code pattern suggests potential use-after-free vulnerability",
            severity="critical",
        ))
        
        self.add_signature(VulnerabilitySignature(
            id="double_free",
            name="Potential Double-Free",
            vuln_type=VulnType.MEMORY_LEAK,
            patterns=[r"\bfree\s*\([^)]+\).*\bfree\s*\(\s*\1\s*\)"],
            description="Same memory region freed twice, indicating double-free vulnerability",
            severity="critical",
        ))
        
        # Vulnerable library versions
        self.add_signature(VulnerabilitySignature(
            id="glibc_old",
            name="Old glibc Version",
            vuln_type=VulnType.VULNERABLE_LIBRARY,
            patterns=[r"GLIBC_2\.(0|1|2|3|4|5|6|7|8|9|10|11|12|13|14|15|16|17|18|19|20|21|22)"],
            description="glibc versions before 2.23 have known vulnerabilities (CVE-2015-7547, etc.)",
            severity="high",
            affected_versions=r"2\.(0|1|2|3|4|5|6|7|8|9|10|11|12|13|14|15|16|17|18|19|20|21|22)",
            cve_ids=["CVE-2015-7547", "CVE-2014-7817", "CVE-2014-9402"],
        ))
        
        self.add_signature(VulnerabilitySignature(
            id="openssl_old",
            name="Old OpenSSL Version",
            vuln_type=VulnType.VULNERABLE_LIBRARY,
            patterns=[r"OpenSSL\s+0\.(9|10)\."],
            description="OpenSSL versions before 1.0.1 have known vulnerabilities",
            severity="critical",
            affected_versions=r"0\.(9|10)\.",
            cve_ids=["CVE-2014-0160", "CVE-2013-4353"],
        ))
        
        # Shell injection patterns
        self.add_signature(VulnerabilitySignature(
            id="shell_injection",
            name="Shell Command Injection Risk",
            vuln_type=VulnType.INSECURE_PATTERN,
            patterns=[
                r"system\s*\(\s*[^\"]*\+",
                r"popen\s*\(\s*[^\"]*\+",
                r"exec\s*\(\s*[^\"]*\+",
                r"subprocess\.call\s*\([^)]*shell\s*=\s*True",
            ],
            description="User input may be concatenated into shell commands, enabling command injection",
            severity="critical",
        ))
        
        # SQL injection patterns
        self.add_signature(VulnerabilitySignature(
            id="sql_injection_risk",
            name="SQL Injection Risk",
            vuln_type=VulnType.INSECURE_PATTERN,
            patterns=[
                r"SELECT\s+.*\+.*\+",
                r"INSERT\s+INTO.*\+.*\+",
                r"f\"[^\"]*SELECT[^\"]*\{[^}]+\}",
                r"format\s*\(\s*[^\"]*SELECT",
            ],
            description="SQL query construction with string concatenation enables SQL injection",
            severity="high",
        ))
        
        # Buffer overflow patterns
        self.add_signature(VulnerabilitySignature(
            id="unchecked_copy",
            name="Unchecked Memory Copy",
            vuln_type=VulnType.BUFFER_OVERFLOW,
            patterns=[
                r"memcpy\s*\([^,]+,[^,]+,\s*[^)]+\)",
                r"memmove\s*\([^,]+,[^,]+,\s*[^)]+\)",
            ],
            description="Memory copy without bounds checking may enable buffer overflow",
            severity="medium",
        ))
    
    def add_signature(self, signature: VulnerabilitySignature):
        """Add a new vulnerability signature."""
        self.signatures[signature.id] = signature
        logger.debug(f"Added vulnerability signature: {signature.id}")
    
    def scan_memory_dump(self, host_id: str, memory_dump: str, 
                         region: str = "unknown") -> List[MemoryMatch]:
        """
        Scan a memory dump for vulnerability signatures.
        
        Args:
            host_id: Identifier for the sandbox host
            memory_dump: String content of memory to scan
            region: Name of the memory region being scanned
        
        Returns:
            List of vulnerability matches found
        """
        import time
        matches = []
        
        for sig_id, signature in self.signatures.items():
            sig_matches = signature.matches(memory_dump)
            
            if sig_matches:
                match = MemoryMatch(
                    signature_id=sig_id,
                    signature_name=signature.name,
                    vuln_type=signature.vuln_type,
                    severity=signature.severity,
                    host_id=host_id,
                    memory_region=region,
                    matches=sig_matches,
                    timestamp=time.time(),
                )
                matches.append(match)
                logger.info(f"Found {len(sig_matches)} matches for {sig_id} in {host_id}:{region}")
        
        return matches
    
    def scan_process_memory(self, host_id: str, pid: int, 
                           memory_segments: List[Tuple[str, str]]) -> List[MemoryMatch]:
        """
        Scan process memory segments.
        
        Args:
            host_id: Sandbox host identifier
            pid: Process ID
            memory_segments: List of (segment_name, content) tuples
        
        Returns:
            List of vulnerability matches
        """
        all_matches = []
        
        for segment_name, content in memory_segments:
            matches = self.scan_memory_dump(host_id, content, f"pid_{pid}:{segment_name}")
            all_matches.extend(matches)
        
        return all_matches
    
    def scan_file_system(self, host_id: str, files: Dict[str, str]) -> List[MemoryMatch]:
        """
        Scan files for vulnerability patterns (static analysis).
        
        Args:
            host_id: Sandbox host identifier
            files: Dict mapping file paths to file content
        
        Returns:
            List of vulnerability matches
        """
        all_matches = []
        
        for filepath, content in files.items():
            matches = self.scan_memory_dump(host_id, content, f"file:{filepath}")
            all_matches.extend(matches)
        
        return all_matches
    
    def generate_report(self, matches: List[MemoryMatch]) -> Dict[str, Any]:
        """Generate a structured report from memory scan results."""
        if not matches:
            return {
                "summary": "No vulnerabilities detected",
                "total_matches": 0,
                "by_severity": {},
                "by_type": {},
                "matches": [],
            }
        
        by_severity: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        
        for match in matches:
            by_severity[match.severity] = by_severity.get(match.severity, 0) + 1
            by_type[match.vuln_type.value] = by_type.get(match.vuln_type.value, 0) + 1
        
        return {
            "summary": f"Detected {len(matches)} vulnerability signatures",
            "total_matches": len(matches),
            "by_severity": by_severity,
            "by_type": by_type,
            "matches": [m.to_dict() for m in matches],
        }
    
    def export_signatures(self, output_path: str) -> None:
        """Export all loaded signatures to JSON."""
        data = []
        for sig in self.signatures.values():
            data.append({
                "id": sig.id,
                "name": sig.name,
                "vuln_type": sig.vuln_type.value,
                "patterns": sig.patterns,
                "description": sig.description,
                "severity": sig.severity,
                "affected_versions": sig.affected_versions,
                "cve_ids": sig.cve_ids,
            })
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            import json
            json.dump(data, f, indent=2)
        logger.info(f"Exported {len(data)} signatures to {output_path}")
