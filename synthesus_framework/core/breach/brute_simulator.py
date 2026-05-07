"""
BruteForceSimulator - Credential Pressure Training System

Generates high-volume, varying-delay login attempts to train the ImmuneSystem
in detecting timing attacks and dictionary patterns. Phase 3 of AGENTS.md.
"""

import logging
import asyncio
import random
import time
from typing import Dict, List, Optional, Any, AsyncGenerator, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class AttackPattern(Enum):
    """Types of brute-force attack patterns."""
    DICTIONARY = "dictionary"           # Sequential from wordlist
    SPRAYING = "spraying"               # Same password, many users
    SMART_GUESSING = "smart_guessing"   # Common patterns, seasons, years
    CREDENTIAL_STUFFING = "stuffing"    # Breached credentials
    HYBRID = "hybrid"                   # Dictionary + mutations
    ADAPTIVE_TIMING = "adaptive_timing"  # Timing attack simulation


@dataclass
class CredentialPressureConfig:
    """Configuration for credential pressure simulation."""
    pattern: AttackPattern
    requests_per_second: float  # Target rate
    duration_seconds: int
    user_list: List[str] = field(default_factory=list)
    password_list: List[str] = field(default_factory=list)
    target_endpoint: str = "http://localhost:8080/api/auth/login"
    jitter_percent: float = 0.3  # Timing variation ±30%
    follow_redirects: bool = False
    track_responses: bool = True
    stop_on_success: bool = False
    
    def __post_init__(self):
        if not self.user_list:
            self.user_list = ["admin", "root", "user", "test", "guest"]
        if not self.password_list:
            self.password_list = self._load_default_passwords()
    
    def _load_default_passwords(self) -> List[str]:
        """Load default common passwords for simulation."""
        return [
            "password", "123456", "admin", "root", "welcome",
            "12345678", "qwerty", "password123", "letmein",
            "admin123", "user123", "test123", "guest123",
            "Password1", "Welcome2024", "Summer2024", "Winter2024",
            "changeme", "default", "secret", "login",
        ]


@dataclass
class LoginAttempt:
    """Record of a single login attempt."""
    timestamp: float
    username: str
    password: str
    response_time_ms: float
    response_code: Optional[int] = None
    response_body: Optional[str] = None
    success: bool = False
    attempt_number: int = 0
    source_ip: str = "127.0.0.1"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "username": self.username,
            "password_hash": self._hash_password(),  # Don't log plaintext
            "response_time_ms": self.response_time_ms,
            "response_code": self.response_code,
            "success": self.success,
            "attempt_number": self.attempt_number,
            "source_ip": self.source_ip,
        }
    
    def _hash_password(self) -> str:
        import hashlib
        return hashlib.sha256(self.password.encode()).hexdigest()[:16]


@dataclass
class SimulationResult:
    """Results of a credential pressure simulation."""
    config: CredentialPressureConfig
    start_time: float
    end_time: float
    total_attempts: int
    attempts: List[LoginAttempt] = field(default_factory=list)
    success_count: int = 0
    failure_count: int = 0
    avg_response_time_ms: float = 0.0
    timing_anomalies: List[Dict[str, Any]] = field(default_factory=list)
    detected_pattern: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "config": {
                "pattern": self.config.pattern.value,
                "requests_per_second": self.config.requests_per_second,
                "duration_seconds": self.config.duration_seconds,
                "target_endpoint": self.config.target_endpoint,
            },
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_attempts": self.total_attempts,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "avg_response_time_ms": self.avg_response_time_ms,
            "timing_anomalies_count": len(self.timing_anomalies),
            "detected_pattern": self.detected_pattern,
            "attempts": [a.to_dict() for a in self.attempts[-100:]],  # Last 100 only
        }


class TrafficGenerator:
    """
    Generates credential traffic patterns for training detection systems.
    """
    
    def __init__(self, config: CredentialPressureConfig):
        self.config = config
        self.attempt_count = 0
        self._load_wordlists()
    
    def _load_wordlists(self):
        """Load extended wordlists based on pattern."""
        if self.config.pattern == AttackPattern.DICTIONARY:
            # Extended dictionary
            self.passwords = self.config.password_list + [
                "dragon", "master", "monkey", "shadow", "sunshine",
                "princess", "football", "baseball", "iloveyou", "trustno1",
            ]
        elif self.config.pattern == AttackPattern.SMART_GUESSING:
            # Pattern-based: seasons, years, company names
            years = [str(y) for y in range(2020, 2026)]
            seasons = ["Spring", "Summer", "Fall", "Winter"]
            self.passwords = [
                f"{s}{y}" for s in seasons for y in years
            ] + [
                f"{s}{y}!" for s in seasons for y in years
            ] + [
                f"Password{y}" for y in years
            ] + [
                f"Welcome{y}!" for y in years
            ]
        elif self.config.pattern == AttackPattern.SPRAYING:
            # Password spraying: few passwords, many users
            self.passwords = ["Password1", "Welcome1", "Spring2024"]
            self.users = [
                "admin", "administrator", "root", "user", "test",
                "john.smith", "jane.doe", "bob.wilson", "alice.jones",
                "dev", "ops", "qa", "prod", "service", "api",
            ]
        else:
            self.passwords = self.config.password_list
            self.users = self.config.user_list
    
    def generate_attempts(self) -> List[tuple]:
        """Generate (username, password) pairs based on pattern."""
        attempts = []
        
        if self.config.pattern == AttackPattern.SPRAYING:
            # Spray pattern: each password tried against all users
            for password in self.passwords:
                for user in self.users:
                    attempts.append((user, password))
        elif self.config.pattern == AttackPattern.CREDENTIAL_STUFFING:
            # Breached credential pairs
            breached_pairs = [
                ("admin", "password123"),
                ("user", "123456"),
                ("test", "test123"),
                ("root", "root123"),
                ("guest", "guest"),
            ]
            attempts.extend(breached_pairs)
        else:
            # Standard dictionary attack
            for user in self.config.user_list:
                for password in self.passwords:
                    attempts.append((user, password))
        
        return attempts
    
    async def generate_timed_attempts(self) -> AsyncGenerator[LoginAttempt, None]:
        """
        Generate login attempts with configurable timing patterns.
        
        Yields login attempts with jitter to simulate real attacker behavior.
        """
        attempts = self.generate_attempts()
        base_delay = 1.0 / self.config.requests_per_second
        
        for i, (username, password) in enumerate(attempts):
            self.attempt_count += 1
            
            # Calculate jittered delay
            jitter = random.uniform(-self.config.jitter_percent, self.config.jitter_percent)
            delay = base_delay * (1 + jitter)
            
            # Adaptive timing attack pattern
            if self.config.pattern == AttackPattern.ADAPTIVE_TIMING:
                # Vary timing based on username to probe timing side-channels
                delay += self._timing_probe(username)
            
            await asyncio.sleep(max(0, delay))
            
            attempt = LoginAttempt(
                timestamp=time.time(),
                username=username,
                password=password,
                response_time_ms=0,  # Set during execution
                attempt_number=self.attempt_count,
                source_ip=self._generate_source_ip(),
            )
            
            yield attempt
    
    def _timing_probe(self, username: str) -> float:
        """Generate timing probe variation based on username (simulating timing attacks)."""
        # Simulate checking if user exists (longer time for valid users)
        hash_val = sum(ord(c) for c in username) % 100
        if hash_val > 80:  # Simulate "valid user" path
            return random.uniform(0.05, 0.15)  # Longer processing
        return random.uniform(-0.02, 0.02)  # Shorter processing
    
    def _generate_source_ip(self) -> str:
        """Generate varied source IPs for distributed attack simulation."""
        # Simulate distributed attack from various IPs
        subnets = ["192.168.1", "10.0.0", "172.16.0"]
        subnet = random.choice(subnets)
        host = random.randint(2, 254)
        return f"{subnet}.{host}"


class BruteForceSimulator:
    """
    Brute-Force Pressure Simulator for training Blue Team detection.
    
    Generates high-volume credential pressure against authentication endpoints
    to train the ImmuneSystem in detecting timing attacks and patterns.
    """
    
    def __init__(self, emulation_tool=None):
        self.emulation = emulation_tool
        self.active_simulations: Dict[str, SimulationResult] = {}
        self.detection_rules: List[Callable] = []
        self._load_detection_rules()
    
    def _load_detection_rules(self):
        """Load pattern detection rules for analyzing simulation results."""
        self.detection_rules = [
            self._detect_timing_anomalies,
            self._detect_spray_pattern,
            self._detect_dictionary_pattern,
            self._detect_credential_stuffing,
        ]
    
    async def run_simulation(self, 
                           config: CredentialPressureConfig,
                           simulation_id: Optional[str] = None) -> SimulationResult:
        """
        Run a credential pressure simulation.
        
        Args:
            config: Simulation configuration
            simulation_id: Optional identifier for this simulation
        
        Returns:
            SimulationResult with full attempt history and analysis
        """
        if simulation_id is None:
            simulation_id = f"sim_{int(time.time())}"
        
        logger.info(f"Starting credential pressure simulation {simulation_id}: "
                   f"{config.pattern.value} @ {config.requests_per_second} req/s")
        
        generator = TrafficGenerator(config)
        
        result = SimulationResult(
            config=config,
            start_time=time.time(),
            end_time=0,
            total_attempts=0,
        )
        
        # Run simulation
        attempt_gen = generator.generate_timed_attempts()
        timeout = time.time() + config.duration_seconds
        
        try:
            async for attempt in attempt_gen:
                if time.time() > timeout:
                    break
                
                # Execute the attempt (simulated or real)
                executed = await self._execute_attempt(attempt, config)
                result.attempts.append(executed)
                result.total_attempts += 1
                
                if executed.success:
                    result.success_count += 1
                    if config.stop_on_success:
                        break
                else:
                    result.failure_count += 1
        
        except asyncio.CancelledError:
            logger.info(f"Simulation {simulation_id} cancelled")
        
        result.end_time = time.time()
        
        # Analyze results
        result.avg_response_time_ms = self._calculate_avg_response_time(result.attempts)
        result.timing_anomalies = self._detect_timing_anomalies(result.attempts)
        result.detected_pattern = self._classify_attack_pattern(result)
        
        self.active_simulations[simulation_id] = result
        
        logger.info(f"Simulation {simulation_id} complete: "
                   f"{result.total_attempts} attempts, "
                   f"pattern detected: {result.detected_pattern}")
        
        return result
    
    async def _execute_attempt(self, attempt: LoginAttempt, 
                               config: CredentialPressureConfig) -> LoginAttempt:
        """Execute a single login attempt (simulated or actual)."""
        start_time = time.time()
        
        if self.emulation and not config.target_endpoint.startswith("http://localhost"):
            # Use emulation tool for sandboxed execution
            response = await self._execute_via_emulation(attempt, config)
        else:
            # Simulated execution for training
            response = self._simulate_execution(attempt)
        
        attempt.response_time_ms = (time.time() - start_time) * 1000
        attempt.response_code = response.get("code", 401)
        attempt.success = response.get("success", False)
        
        return attempt
    
    async def _execute_via_emulation(self, attempt: LoginAttempt, 
                                     config: CredentialPressureConfig) -> Dict:
        """Execute login attempt via emulation sandbox."""
        # This would integrate with EmulationTool to test actual containers
        # For now, simulate with realistic timing
        await asyncio.sleep(random.uniform(0.01, 0.1))
        return {"code": 401, "success": False}
    
    def _simulate_execution(self, attempt: LoginAttempt) -> Dict:
        """Simulate authentication backend response."""
        # Simulate realistic auth behavior
        # Successful credentials (for testing detection)
        valid_creds = {"admin": "Password1", "user": "Welcome2024"}
        
        # Simulate processing time (with timing side-channel)
        base_time = 0.05
        if attempt.username in valid_creds:
            # Valid user: check password (longer time)
            base_time += 0.03
            if attempt.password == valid_creds[attempt.username]:
                return {"code": 200, "success": True}
        else:
            # Invalid user: quick reject
            base_time += 0.01
        
        return {"code": 401, "success": False}
    
    def _calculate_avg_response_time(self, attempts: List[LoginAttempt]) -> float:
        """Calculate average response time."""
        if not attempts:
            return 0.0
        return sum(a.response_time_ms for a in attempts) / len(attempts)
    
    def _detect_timing_anomalies(self, attempts: List[LoginAttempt]) -> List[Dict]:
        """Detect timing attack patterns in response times."""
        anomalies = []
        if len(attempts) < 10:
            return anomalies
        
        # Group by username and check for timing differences
        user_times: Dict[str, List[float]] = {}
        for attempt in attempts:
            user = attempt.username
            if user not in user_times:
                user_times[user] = []
            user_times[user].append(attempt.response_time_ms)
        
        # Calculate average per user
        user_avgs = {u: sum(times)/len(times) for u, times in user_times.items()}
        global_avg = sum(user_avgs.values()) / len(user_avgs) if user_avgs else 0
        
        # Flag users with significantly different timing
        for user, avg_time in user_avgs.items():
            if abs(avg_time - global_avg) > (global_avg * 0.3):  # 30% difference
                anomalies.append({
                    "type": "timing_side_channel",
                    "username": user,
                    "avg_response_time": avg_time,
                    "global_avg": global_avg,
                    "difference_percent": ((avg_time - global_avg) / global_avg) * 100,
                    "indication": "Valid user enumeration via timing" if avg_time > global_avg else "Different code path",
                })
        
        return anomalies
    
    def _detect_spray_pattern(self, result: SimulationResult) -> bool:
        """Detect password spraying pattern."""
        attempts = result.attempts
        if len(attempts) < 20:
            return False
        
        # Check for same password used many times
        password_counts: Dict[str, int] = {}
        for a in attempts:
            pwd = a.password
            password_counts[pwd] = password_counts.get(pwd, 0) + 1
        
        # Spray pattern: few passwords, many attempts each
        max_reuse = max(password_counts.values()) if password_counts else 0
        return max_reuse > len(attempts) * 0.3  # >30% reuse
    
    def _detect_dictionary_pattern(self, result: SimulationResult) -> bool:
        """Detect sequential dictionary attack."""
        # Check for sequential common passwords
        common_passwords = set([
            "password", "123456", "admin", "welcome", "password123",
            "12345678", "qwerty", "letmein", "12345", "123456789",
        ])
        
        attempts = result.attempts
        if len(attempts) < 10:
            return False
        
        common_count = sum(1 for a in attempts if a.password.lower() in common_passwords)
        return common_count > len(attempts) * 0.5  # >50% common passwords
    
    def _detect_credential_stuffing(self, result: SimulationResult) -> bool:
        """Detect credential stuffing pattern."""
        # Check for unique (user, pass) pairs with no reuse
        attempts = result.attempts
        if len(attempts) < 5:
            return False
        
        pairs = [(a.username, a.password) for a in attempts]
        unique_pairs = len(set(pairs))
        
        # Stuffing: many unique pairs, few repeated passwords
        password_reuse = len(attempts) - len(set(a.password for a in attempts))
        return unique_pairs > len(attempts) * 0.9 and password_reuse < len(attempts) * 0.1
    
    def _classify_attack_pattern(self, result: SimulationResult) -> str:
        """Classify the detected attack pattern from simulation results."""
        config_pattern = result.config.pattern.value
        
        # Override based on observed behavior
        if self._detect_spray_pattern(result):
            return "password_spraying_detected"
        elif self._detect_credential_stuffing(result):
            return "credential_stuffing_detected"
        elif self._detect_dictionary_pattern(result):
            return "dictionary_attack_detected"
        elif result.timing_anomalies:
            return "timing_attack_detected"
        
        return config_pattern
    
    def generate_detection_training_data(self, simulation_id: str) -> List[Dict]:
        """Generate labeled training data for Blue Team ML models."""
        if simulation_id not in self.active_simulations:
            return []
        
        result = self.active_simulations[simulation_id]
        training_data = []
        
        label = 1 if result.detected_pattern else 0  # 1 = attack, 0 = benign
        
        # Feature extraction for each attempt window
        window_size = 10
        for i in range(0, len(result.attempts), window_size):
            window = result.attempts[i:i+window_size]
            
            features = {
                "window_id": i // window_size,
                "request_rate": len(window) / (window[-1].timestamp - window[0].timestamp + 0.001),
                "unique_usernames": len(set(a.username for a in window)),
                "unique_passwords": len(set(a.password for a in window)),
                "avg_response_time": self._calculate_avg_response_time(window),
                "failure_rate": sum(1 for a in window if not a.success) / len(window),
                "source_ip_count": len(set(a.source_ip for a in window)),
            }
            
            training_data.append({
                "features": features,
                "label": label,
                "attack_pattern": result.detected_pattern,
            })
        
        return training_data
    
    def export_results(self, simulation_id: str, output_path: str) -> None:
        """Export simulation results to JSON."""
        if simulation_id not in self.active_simulations:
            raise ValueError(f"Simulation {simulation_id} not found")
        
        result = self.active_simulations[simulation_id]
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        
        logger.info(f"Exported simulation {simulation_id} to {output_path}")
    
    def get_simulation_summary(self) -> Dict[str, Any]:
        """Get summary of all simulations."""
        return {
            "total_simulations": len(self.active_simulations),
            "patterns_tested": list(set(
                s.config.pattern.value for s in self.active_simulations.values()
            )),
            "total_attempts_generated": sum(
                s.total_attempts for s in self.active_simulations.values()
            ),
        }
