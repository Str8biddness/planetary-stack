import logging
import re
# from core.tools.scraper import WebScraper # Moved to lazy lookup to avoid circularity

logger = logging.getLogger(__name__)

class AgentDispatcher:
    """
    Evaluates queries to determine if they need to be routed to external tools
    (like the WebScraper) instead of internal Cognitive Core / RAG alone.
    """
    def __init__(self):
        self.live_mode = False # Default to Sandbox (Safe)
        try:
            from core.tools.scraper import WebScraper
            self.scraper = WebScraper()
        except ImportError:
            self.scraper = None
        
        try:
            from core.tools.security import SecurityTools
            self.security = SecurityTools()
        except ImportError:
            self.security = None

        try:
            from core.emulation_tool import EmulationTool
            self.emulation = EmulationTool()
        except ImportError:
            self.emulation = None
        
        # Breach Red Team Tools
        try:
            from core.breach import BreachEngine, MemoryPatternMatcher, ExploitModeler, BruteForceSimulator
            self.breach_engine = BreachEngine(emulation_tool=self.emulation, live_mode=self.live_mode)
            self.memory_matcher = MemoryPatternMatcher()
            self.exploit_modeler = ExploitModeler()
            self.brute_simulator = BruteForceSimulator(emulation_tool=self.emulation)
        except ImportError as e:
            logger.warning(f"Breach module not available: {e}")
            self.breach_engine = None
            self.memory_matcher = None
            self.exploit_modeler = None
            self.brute_simulator = None
        
        # Simple URL regex pattern to detect if the user/character wants to fetch an explicit link
        self.url_pattern = re.compile(
            r'(https?://)?(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)'
        )

    async def evaluate_and_dispatch(self, query: str, character_id: str) -> dict | None:
        """
        Takes a raw query. If it requires a tool, executes the tool and returns the context.
        If no tool is needed, returns None so standard processing continues.
        """
        import json
        from pathlib import Path
        
        # Load character's allowed tools from bio.json
        allowed_tools = []
        if character_id:
            # Adjust path to find characters from both synthesus/ and projects/
            base_path = Path(__file__).parent.parent
            bio_path = base_path / "characters" / character_id / "bio.json"
            
            if bio_path.exists():
                try:
                    with open(bio_path, "r") as f:
                        bio = json.load(f)
                        allowed_tools = bio.get("allowed_tools", [])
                except Exception as e:
                    logger.error(f"Failed to load bio for {character_id}: {e}")
        
        query_lc = query.lower()

        # Feature 6: Environment Boundary Management
        if "enable live mode" in query_lc or "leave the sandbox" in query_lc:
            self.live_mode = True
            return {"tool": "system", "action": "config", "context": "ENVIRONMENT BOUNDARY BREACHED. Live Host access enabled. Operating in real VM environment."}
        
        if "enable sandbox mode" in query_lc or "enter the sandbox" in query_lc:
            self.live_mode = False
            return {"tool": "system", "action": "config", "context": "ENVIRONMENT BOUNDARY SECURED. Sandbox Mode active. All operations containerized."}

        # Feature 5: Emulation & Sandboxing
        emu_triggers = ["sandbox", "emulate", "virtual host", "spawn container"]
        if any(trigger in query_lc for trigger in emu_triggers) and self.emulation:
            # If in Live Mode, we don't spawn a container, we point to the host
            if self.live_mode:
                return {
                    "tool": "emulation",
                    "action": "attach",
                    "context": "Operating in Live Mode. Commands will execute directly on the virtual machine host.",
                    "raw_result": {"host_id": "localhost"}
                }
            
            if "emulation" not in allowed_tools and character_id not in ("master", "synth"):
                return {
                    "tool": "emulation",
                    "action": "create",
                    "context": "I am not authorized to spawn emulation sandboxes.",
                    "raw_result": {"status": "error", "error": "Unauthorized tool use."}
                }
            
            logger.info(f"[{character_id}] AgentDispatcher routing to EmulationTool.create_host")
            host_id = self.emulation.create_host({"image": "ubuntu:latest", "cpu": "0.5", "memory": "256m"})
            return {
                "tool": "emulation",
                "action": "create",
                "context": f"Emulation sandbox spawned successfully. Host ID: {host_id}. Environment isolated.",
                "raw_result": {"host_id": host_id}
            }

        # Feature 1: Explicit URL scraping
        url_match = self.url_pattern.search(query)
        fetch_triggers = ["fetch", "read", "scrape", "summarize", "look up", "what's on", "check"]
        needs_fetch = any(trigger in query_lc for trigger in fetch_triggers)
        
        if url_match and needs_fetch and self.scraper:
            if "scraper" not in allowed_tools and character_id not in ("master", "synth"):
                logger.info(f"[{character_id}] AgentDispatcher blocked scraper: 'scraper' not in allowed_tools.")
                return {
                    "tool": "scraper",
                    "action": "fetch",
                    "context": "I am not authorized to browse the web or scrape links.",
                    "raw_result": {"status": "error", "error": "Unauthorized tool use."}
                }
            
            url_to_fetch = url_match.group(0)
            logger.info(f"[{character_id}] AgentDispatcher routing to WebScraper for {url_to_fetch}")
            result = await self.scraper.fetch(url_to_fetch)
            
            if result["status"] == "success":
                return {
                    "tool": "scraper",
                    "action": "fetch",
                    "context": f"External Content from {result['url']}:\n\n{result['content']}",
                    "raw_result": result
                }
            else:
                return {
                    "tool": "scraper",
                    "action": "fetch",
                    "context": f"Failed to retrieve data from {url_to_fetch}.",
                    "raw_result": result
                }

        # Feature 2: Security Scans (nmap)
        scan_triggers = ["scan", "nmap", "audit network", "probe", "port scan"]
        if any(trigger in query_lc for trigger in scan_triggers) and self.security:
            if "nmap" not in allowed_tools and character_id not in ("master", "synth"):
                return {
                    "tool": "nmap",
                    "action": "scan",
                    "context": "I am not authorized to perform network scans.",
                    "raw_result": {"status": "error", "error": "Unauthorized tool use."}
                }
            
            # Extract target (IP or hostname)
            target = "127.0.0.1"
            # Try to find something that looks like an IP or hostname
            ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
            host_pattern = r'\b[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'
            
            m_ip = re.search(ip_pattern, query)
            m_host = re.search(host_pattern, query)
            
            if m_ip:
                target = m_ip.group(0)
            elif m_host:
                target = m_host.group(0)
            elif "localhost" in query_lc:
                target = "127.0.0.1"

            logger.info(f"[{character_id}] AgentDispatcher routing to SecurityTools.run_nmap for {target}")
            result = await self.security.run_nmap(target)
            
            if result["status"] == "success":
                return {
                    "tool": "nmap",
                    "action": "scan",
                    "context": f"Nmap Scan Results for {target}:\n\n{result['output']}",
                    "raw_result": result
                }
            else:
                return {
                    "tool": "nmap",
                    "action": "scan",
                    "context": f"Nmap scan failed for {target}. Error: {result.get('error')}",
                    "raw_result": result
                }

        # Feature 3: System Audit
        audit_triggers = ["audit system", "device audit", "system check", "security status"]
        if any(trigger in query_lc for trigger in audit_triggers) and self.security:
            if "analyzer" not in allowed_tools and character_id not in ("master", "synth"):
                return {
                    "tool": "analyzer",
                    "action": "audit",
                    "context": "I am not authorized to perform system audits.",
                    "raw_result": {"status": "error", "error": "Unauthorized tool use."}
                }
            
            logger.info(f"[{character_id}] AgentDispatcher routing to SecurityTools.system_audit")
            result = await self.security.system_audit()
            
            if result["status"] == "success":
                return {
                    "tool": "analyzer",
                    "action": "audit",
                    "context": f"System Audit Results:\n\n{json.dumps(result['audit'], indent=2)}",
                    "raw_result": result
                }
            else:
                return {
                    "tool": "analyzer",
                    "action": "audit",
                    "context": f"System audit failed. Error: {result.get('error')}",
                    "raw_result": result
                }

        # Feature 4: Active Defense (Kill/Block)
        if any(trigger in query_lc for trigger in ["kill process", "terminate pid", "stop pid"]) and self.security:
            if "defender" not in allowed_tools and character_id not in ("master", "synth"):
                return {
                    "tool": "defender",
                    "action": "kill",
                    "context": "I am not authorized to terminate processes.",
                    "raw_result": {"status": "error", "error": "Unauthorized tool use."}
                }
            
            # Extract PID
            pid_match = re.search(r'\b(\d+)\b', query)
            if pid_match:
                pid = int(pid_match.group(1))
                logger.info(f"[{character_id}] AgentDispatcher routing to SecurityTools.kill_process for PID {pid}")
                result = await self.security.kill_process(pid)
                return {
                    "tool": "defender",
                    "action": "kill",
                    "context": f"Process Termination Result: {json.dumps(result)}",
                    "raw_result": result
                }

        if any(trigger in query_lc for trigger in ["block ip", "deny ip", "blacklist ip"]) and self.security:
            if "defender" not in allowed_tools and character_id not in ("master", "synth"):
                return {
                    "tool": "defender",
                    "action": "block",
                    "context": "I am not authorized to block IP addresses.",
                    "raw_result": {"status": "error", "error": "Unauthorized tool use."}
                }
            
            # Extract IP
            ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
            m_ip = re.search(ip_pattern, query)
            if m_ip:
                target_ip = m_ip.group(0)
                logger.info(f"[{character_id}] AgentDispatcher routing to SecurityTools.block_ip for {target_ip}")
                result = await self.security.block_ip(target_ip)
                return {
                    "tool": "defender",
                    "action": "block",
                    "context": f"IP Blocking Result: {json.dumps(result)}",
                    "raw_result": result
                }
        
        # Feature 7: Breach Red Team - Attack Tree Generation
        attack_tree_triggers = ["model attack", "attack tree", "exploit path", "threat model"]
        if any(trigger in query_lc for trigger in attack_tree_triggers) and self.exploit_modeler:
            if "exploit_modeler" not in allowed_tools and character_id not in ("master", "breach"):
                return {
                    "tool": "exploit_modeler",
                    "action": "model",
                    "context": "I am not authorized to generate attack trees.",
                    "raw_result": {"status": "error", "error": "Unauthorized tool use."}
                }
            
            # Extract target and objective from query
            target = "sandbox"
            objective = "access"
            entry_point = "web interface"
            
            if "root" in query_lc or "privilege" in query_lc:
                objective = "root access"
            elif "data" in query_lc or "exfil" in query_lc:
                objective = "data exfiltration"
            elif "bypass" in query_lc:
                objective = "authentication bypass"
            
            logger.info(f"[{character_id}] AgentDispatcher routing to ExploitModeler for {target}/{objective}")
            
            tree = self.exploit_modeler.model_attack(
                target=target,
                objective=objective,
                entry_point=entry_point,
                discovered_vulns=None
            )
            
            summary = self.exploit_modeler.get_tree_summary(tree.id)
            
            return {
                "tool": "exploit_modeler",
                "action": "model",
                "context": f"Generated Attack Tree: {tree.name}\n\n"
                          f"Objective: {tree.objective}\n"
                          f"Critical Path Length: {summary['critical_path_length']} steps\n"
                          f"Total Paths: {summary['total_paths']}\n"
                          f"Estimated Success: {summary['estimated_success_probability']:.0%}\n"
                          f"Estimated Time: {summary['estimated_time_minutes']} minutes",
                "raw_result": tree.to_dict()
            }
        
        # Feature 8: Breach Red Team - Memory Scan
        memory_scan_triggers = ["scan memory", "memory analysis", "vulnerability scan", "check for vuln"]
        if any(trigger in query_lc for trigger in memory_scan_triggers) and self.memory_matcher:
            if "memory_scan" not in allowed_tools and character_id not in ("master", "breach"):
                return {
                    "tool": "memory_scan",
                    "action": "scan",
                    "context": "I am not authorized to scan memory for vulnerabilities.",
                    "raw_result": {"status": "error", "error": "Unauthorized tool use."}
                }
            
            host_id = "localhost" if self.live_mode else "sandbox"
            logger.info(f"[{character_id}] AgentDispatcher routing to MemoryPatternMatcher for {host_id}")
            
            # Simulate memory content scan
            sample_content = query_lc  # In practice, this would be actual memory dump
            matches = self.memory_matcher.scan_memory_dump(host_id, sample_content, "heap")
            report = self.memory_matcher.generate_report(matches)
            
            return {
                "tool": "memory_scan",
                "action": "scan",
                "context": f"Memory Scan Results for {host_id}:\n\n"
                          f"Summary: {report['summary']}\n"
                          f"By Severity: {json.dumps(report['by_severity'], indent=2)}\n"
                          f"By Type: {json.dumps(report['by_type'], indent=2)}",
                "raw_result": report
            }
        
        # Feature 9: Breach Red Team - Brute Force Simulation
        brute_triggers = ["brute force", "credential pressure", "auth test", "login flood"]
        if any(trigger in query_lc for trigger in brute_triggers) and self.brute_simulator:
            if "brute_sim" not in allowed_tools and character_id not in ("master", "breach"):
                return {
                    "tool": "brute_sim",
                    "action": "simulate",
                    "context": "I am not authorized to run brute-force simulations.",
                    "raw_result": {"status": "error", "error": "Unauthorized tool use."}
                }
            
            logger.info(f"[{character_id}] AgentDispatcher routing to BruteForceSimulator")
            
            from core.breach import CredentialPressureConfig, AttackPattern
            
            # Determine pattern from query
            pattern = AttackPattern.DICTIONARY
            if "spray" in query_lc:
                pattern = AttackPattern.SPRAYING
            elif "timing" in query_lc:
                pattern = AttackPattern.ADAPTIVE_TIMING
            elif "stuff" in query_lc:
                pattern = AttackPattern.CREDENTIAL_STUFFING
            
            config = CredentialPressureConfig(
                pattern=pattern,
                requests_per_second=5.0,
                duration_seconds=30,
            )
            
            # Note: This would be async in real implementation
            # For now, return configuration ready to execute
            return {
                "tool": "brute_sim",
                "action": "configure",
                "context": f"Brute-Force Simulation Configured:\n\n"
                          f"Pattern: {pattern.value}\n"
                          f"Rate: {config.requests_per_second} req/s\n"
                          f"Duration: {config.duration_seconds}s\n"
                          f"Jitter: {config.jitter_percent:.0%}\n\n"
                          f"Ready to execute against target endpoint.",
                "raw_result": {
                    "config": {
                        "pattern": pattern.value,
                        "rate": config.requests_per_second,
                        "duration": config.duration_seconds,
                    },
                    "status": "configured"
                }
            }
        
        # Feature 10: Breach Red Team - Crash Analysis (Abductive Engine)
        crash_triggers = ["analyze crash", "debug crash", "what caused", "why did it fail"]
        if any(trigger in query_lc for trigger in crash_triggers) and self.breach_engine:
            if "breach_analysis" not in allowed_tools and character_id not in ("master", "breach"):
                return {
                    "tool": "breach_analysis",
                    "action": "analyze",
                    "context": "I am not authorized to perform crash analysis.",
                    "raw_result": {"status": "error", "error": "Unauthorized tool use."}
                }
            
            logger.info(f"[{character_id}] AgentDispatcher routing to BreachEngine for crash analysis")
            
            # Parse crash type from query
            crash_type = "unknown"
            if "segfault" in query_lc or "segmentation" in query_lc:
                crash_type = "segfault"
            elif "heap" in query_lc:
                crash_type = "heap_error"
            elif "auth" in query_lc:
                crash_type = "auth_fail"
            
            # Simulate crash analysis
            vectors = self.breach_engine.analyze_crash({
                "type": crash_type,
                "logs": [],
                "component": "target_system"
            })
            
            vector_summary = "\n".join([
                f"- {v.name} ({v.severity.value}): {v.description[:100]}..."
                for v in vectors[:3]
            ])
            
            return {
                "tool": "breach_analysis",
                "action": "analyze",
                "context": f"Crash Analysis Results:\n\n"
                          f"Crash Type: {crash_type}\n"
                          f"Attack Vectors Identified: {len(vectors)}\n\n"
                          f"Likely Attack Vectors:\n{vector_summary}",
                "raw_result": [v.to_dict() for v in vectors]
            }
        
        return None
