"""
Tests for the Breach Red Team Module.

Tests cover:
- BreachEngine abductive analysis
- MemoryPatternMatcher vulnerability detection
- ExploitModeler attack tree generation
- BruteForceSimulator credential pressure simulation
"""

import sys
import pytest
from pathlib import Path

# Add synthesus_framework to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.breach import (
    BreachEngine,
    MemoryPatternMatcher,
    ExploitModeler,
    BruteForceSimulator,
    AttackVector,
    AttackSeverity,
    AttackCategory,
    VulnerabilitySignature,
    VulnType,
    AttackTree,
    AttackNode,
    AttackPhase,
    CredentialPressureConfig,
    AttackPattern,
)


class TestBreachEngine:
    """Tests for the BreachEngine abductive reasoning system."""
    
    def test_analyze_crash_segfault(self):
        """Test abductive analysis of segmentation fault."""
        engine = BreachEngine()
        
        crash_data = {
            "type": "segfault",
            "logs": [{"message": "Segmentation fault at 0xdeadbeef"}],
            "component": "auth_service",
            "context": {"memory_pressure": 0.9},
        }
        
        vectors = engine.analyze_crash(crash_data)
        
        assert len(vectors) > 0
        assert any("buffer" in v.name.lower() or "use_after_free" in v.name.lower() 
                   for v in vectors)
    
    def test_scan_attack_surface(self):
        """Test proactive attack surface scanning."""
        engine = BreachEngine()
        
        target_config = {
            "type": "web_app",
            "services": [
                {"name": "api", "port": 8080, "authentication": "none"},
                {"name": "database", "port": 5432, "uses_defaults": True},
            ],
            "debug_mode": True,
            "exposed_files": [".env", "config.json"],
        }
        
        vectors = engine.scan_attack_surface(target_config)
        
        assert len(vectors) > 0
        # Should find unauthenticated access vector
        assert any(v.category == AttackCategory.AUTHENTICATION for v in vectors)
    
    def test_attack_vector_serialization(self):
        """Test attack vector to_dict/from_dict roundtrip."""
        vector = AttackVector(
            name="Test Vector",
            description="Test description",
            category=AttackCategory.MEMORY_CORRUPTION,
            severity=AttackSeverity.CRITICAL,
            target_component="test_service",
        )
        
        data = vector.to_dict()
        restored = AttackVector.from_dict(data)
        
        assert restored.name == vector.name
        assert restored.category == vector.category
        assert restored.severity == vector.severity
    
    def test_get_attack_vectors_by_severity(self):
        """Test filtering attack vectors by severity."""
        engine = BreachEngine()
        
        # Add vectors of different severities
        engine.discovered_vectors["v1"] = AttackVector(
            name="Critical Vuln",
            description="Critical",
            category=AttackCategory.MEMORY_CORRUPTION,
            severity=AttackSeverity.CRITICAL,
            target_component="test",
        )
        engine.discovered_vectors["v2"] = AttackVector(
            name="Low Vuln",
            description="Low",
            category=AttackCategory.CONFIGURATION,
            severity=AttackSeverity.LOW,
            target_component="test",
        )
        
        critical = engine.get_attack_vectors(AttackSeverity.CRITICAL)
        assert len(critical) == 1
        assert critical[0].severity == AttackSeverity.CRITICAL


class TestMemoryPatternMatcher:
    """Tests for the MemoryPatternMatcher vulnerability scanner."""
    
    def test_scan_memory_dump_strcpy(self):
        """Test detection of unsafe strcpy in memory."""
        matcher = MemoryPatternMatcher()
        
        memory_content = """
        void vulnerable_function(char* input) {
            char buffer[64];
            strcpy(buffer, input);  // Unsafe!
            printf("%s", buffer);
        }
        """
        
        matches = matcher.scan_memory_dump("test_host", memory_content, "code")
        
        # Should find strcpy vulnerability
        assert any(m.signature_id == "unsafe_strcpy" for m in matches)
    
    def test_scan_memory_dump_glibc_old(self):
        """Test detection of vulnerable glibc version."""
        matcher = MemoryPatternMatcher()
        
        memory_content = "Binary compiled with GLIBC_2.17 linked at runtime"
        
        matches = matcher.scan_memory_dump("test_host", memory_content, "libraries")
        
        # Should find old glibc vulnerability
        assert any(m.signature_id == "glibc_old" for m in matches)
    
    def test_scan_memory_dump_sql_injection(self):
        """Test detection of SQL injection patterns."""
        matcher = MemoryPatternMatcher()
        
        memory_content = '''
        query = f"SELECT * FROM users WHERE id = {user_id}"
        cursor.execute(query)
        '''
        
        matches = matcher.scan_memory_dump("test_host", memory_content, "source")
        
        # Should find SQL injection risk
        assert any(m.signature_id == "sql_injection_risk" for m in matches)
    
    def test_custom_signature(self):
        """Test adding custom vulnerability signatures."""
        matcher = MemoryPatternMatcher()
        
        custom_sig = VulnerabilitySignature(
            id="custom_test",
            name="Custom Test Pattern",
            vuln_type=VulnType.INSECURE_PATTERN,
            patterns=[r"TEST_PATTERN_123"],
            description="Test custom signature",
            severity="medium",
        )
        matcher.add_signature(custom_sig)
        
        matches = matcher.scan_memory_dump("test_host", "code with TEST_PATTERN_123 here", "test")
        
        assert any(m.signature_id == "custom_test" for m in matches)
    
    def test_generate_report_no_matches(self):
        """Test report generation with no matches."""
        matcher = MemoryPatternMatcher()
        report = matcher.generate_report([])
        
        assert report["total_matches"] == 0
        assert "No vulnerabilities detected" in report["summary"]
    
    def test_generate_report_with_matches(self):
        """Test report generation with matches."""
        import time
        matcher = MemoryPatternMatcher()
        
        # Create a match
        match = matcher.scan_memory_dump("host", "strcpy(test)", "code")
        report = matcher.generate_report(match)
        
        assert report["total_matches"] > 0
        assert "Detected" in report["summary"]
        assert "by_severity" in report
        assert "by_type" in report


class TestExploitModeler:
    """Tests for the ExploitModeler attack tree generator."""
    
    def test_model_attack_basic(self):
        """Test basic attack tree generation."""
        modeler = ExploitModeler()
        
        tree = modeler.model_attack(
            target="test_app",
            objective="root access",
            entry_point="web interface",
        )
        
        assert tree.id is not None
        assert tree.name == "Attack on test_app for root access"
        assert tree.objective == "root access"
        assert tree.root_node is not None
    
    def test_attack_tree_serialization(self):
        """Test attack tree JSON serialization."""
        modeler = ExploitModeler()
        
        tree = modeler.model_attack(
            target="test",
            objective="data exfiltration",
            entry_point="api",
        )
        
        json_str = tree.to_json()
        assert isinstance(json_str, str)
        assert "test" in json_str
        assert "data exfiltration" in json_str
    
    def test_get_critical_path(self):
        """Test extracting critical path from attack tree."""
        modeler = ExploitModeler()
        
        tree = modeler.model_attack(
            target="test",
            objective="root access",
            entry_point="web",
        )
        
        path = tree.get_critical_path()
        assert len(path) > 0
        assert path[0] == tree.root_node
    
    def test_get_all_paths(self):
        """Test getting all paths through attack tree."""
        modeler = ExploitModeler()
        
        # Create tree with branches
        root = AttackNode(
            name="Root",
            phase=AttackPhase.INITIAL_ACCESS,
            description="Initial access",
            techniques=["T1190"],
        )
        child1 = AttackNode(
            name="Branch A",
            phase=AttackPhase.EXECUTION,
            description="Branch A",
            techniques=["T1059"],
        )
        child2 = AttackNode(
            name="Branch B",
            phase=AttackPhase.EXECUTION,
            description="Branch B",
            techniques=["T1059"],
        )
        root.children = [child1, child2]
        
        import time
        tree = AttackTree(
            id="test",
            name="Test Tree",
            description="Test",
            target_system="test",
            objective="test",
            root_node=root,
            created_at=time.time(),
        )
        
        paths = tree.get_all_paths()
        assert len(paths) == 2  # Should have 2 paths to leaves
    
    def test_tree_summary(self):
        """Test attack tree summary generation."""
        modeler = ExploitModeler()
        
        tree = modeler.model_attack(
            target="test",
            objective="access",
            entry_point="ssh",
        )
        
        summary = modeler.get_tree_summary(tree.id)
        
        assert "id" in summary
        assert "name" in summary
        assert "objective" in summary
        assert "critical_path_length" in summary
        assert "total_paths" in summary


class TestBruteForceSimulator:
    """Tests for the BruteForceSimulator credential pressure system."""
    
    def test_traffic_generator_dictionary(self):
        """Test dictionary attack pattern generation."""
        from core.breach import TrafficGenerator
        
        config = CredentialPressureConfig(
            pattern=AttackPattern.DICTIONARY,
            requests_per_second=10.0,
            duration_seconds=60,
            user_list=["admin", "root"],
            password_list=["password", "123456"],
        )
        
        generator = TrafficGenerator(config)
        attempts = generator.generate_attempts()
        
        # Should generate user * password combinations
        assert len(attempts) == 4  # 2 users * 2 passwords
        assert ("admin", "password") in attempts
        assert ("root", "123456") in attempts
    
    def test_traffic_generator_spraying(self):
        """Test password spraying pattern generation."""
        from core.breach import TrafficGenerator
        
        config = CredentialPressureConfig(
            pattern=AttackPattern.SPRAYING,
            requests_per_second=1.0,
            duration_seconds=60,
        )
        
        generator = TrafficGenerator(config)
        attempts = generator.generate_attempts()
        
        # Spray pattern: few passwords, many users
        passwords_used = set(a[1] for a in attempts)
        assert len(passwords_used) <= 3  # Should use few passwords
    
    def test_simulation_result_to_dict(self):
        """Test simulation result serialization."""
        import time
        
        config = CredentialPressureConfig(
            pattern=AttackPattern.DICTIONARY,
            requests_per_second=5.0,
            duration_seconds=30,
        )
        
        result = BruteForceSimulator.SimulationResult(
            config=config,
            start_time=time.time(),
            end_time=time.time() + 30,
            total_attempts=150,
        )
        
        data = result.to_dict()
        assert data["config"]["pattern"] == "dictionary"
        assert data["total_attempts"] == 150
    
    def test_detect_dictionary_pattern(self):
        """Test detection of dictionary attack pattern."""
        from core.breach import LoginAttempt
        import time
        
        simulator = BruteForceSimulator()
        
        config = CredentialPressureConfig(
            pattern=AttackPattern.DICTIONARY,
            requests_per_second=10.0,
            duration_seconds=10,
        )
        
        # Create attempts with common passwords
        result = BruteForceSimulator.SimulationResult(
            config=config,
            start_time=time.time(),
            end_time=time.time() + 10,
            total_attempts=20,
        )
        
        result.attempts = [
            LoginAttempt(
                timestamp=time.time(),
                username=f"user{i}",
                password=pwd,
                response_time_ms=50.0,
                attempt_number=i,
            )
            for i, pwd in enumerate([
                "password", "123456", "admin", "welcome",
                "password123", "12345678", "qwerty", "letmein",
            ] * 2 + ["unique1", "unique2", "unique3", "unique4"])
        ]
        
        is_dict = simulator._detect_dictionary_pattern(result)
        assert is_dict  # Should detect dictionary pattern
    
    def test_detect_spray_pattern(self):
        """Test detection of password spraying pattern."""
        from core.breach import LoginAttempt
        import time
        
        simulator = BruteForceSimulator()
        
        config = CredentialPressureConfig(
            pattern=AttackPattern.SPRAYING,
            requests_per_second=1.0,
            duration_seconds=60,
        )
        
        result = BruteForceSimulator.SimulationResult(
            config=config,
            start_time=time.time(),
            end_time=time.time() + 60,
            total_attempts=30,
        )
        
        # Spray pattern: same password used many times
        result.attempts = [
            LoginAttempt(
                timestamp=time.time(),
                username=f"user{i}",
                password="Password1",  # Same password
                response_time_ms=50.0,
                attempt_number=i,
            )
            for i in range(30)
        ]
        
        is_spray = simulator._detect_spray_pattern(result)
        assert is_spray  # Should detect spray pattern


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
