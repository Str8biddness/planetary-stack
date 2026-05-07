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

        # Feature 5: Emulation & Sandboxing
        emu_triggers = ["sandbox", "emulate", "virtual host", "spawn container"]
        if any(trigger in query_lc for trigger in emu_triggers) and self.emulation:
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
        
        return None
