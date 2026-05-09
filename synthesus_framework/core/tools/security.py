import subprocess
import logging
import os
import sys
import json
import platform

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"


class SecurityTools:
    """
    Tools for system and network security auditing, specialized for the Ghostkey persona.
    Cross-platform: supports both Linux and Windows.
    """
    def __init__(self):
        self.platform = platform.system()

    async def run_nmap(self, target: str, arguments: str = "-F") -> dict:
        """
        Executes an nmap scan on the specified target.
        """
        if not target:
            return {"status": "error", "error": "No target specified for nmap scan."}
        
        # Basic validation to prevent command injection
        clean_target = target.split()[0]  # Only take the first word as target
        
        # Basic arguments validation
        safe_args = []
        if arguments:
            allowed_args = ["-F", "-sV", "-p-", "-O", "-A"]
            for arg in arguments.split():
                if arg in allowed_args:
                    safe_args.append(arg)
        
        if not safe_args:
            safe_args = ["-F"]
            
        cmd = ["nmap"] + safe_args + [clean_target]
        
        try:
            logger.info(f"Executing security tool: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                return {
                    "status": "success",
                    "target": clean_target,
                    "output": result.stdout
                }
            else:
                return {
                    "status": "error",
                    "error": result.stderr,
                    "target": clean_target
                }
        except FileNotFoundError:
            return {"status": "error", "error": "nmap not found. Install it from https://nmap.org", "target": clean_target}
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "Scan timed out after 120 seconds.", "target": clean_target}
        except Exception as e:
            return {"status": "error", "error": str(e), "target": clean_target}

    async def kill_process(self, pid: int) -> dict:
        """
        Kills a process by PID. Requires appropriate permissions.
        """
        try:
            logger.info(f"Ghostkey defensive action: Killing process {pid}")
            if IS_WINDOWS:
                result = subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    return {"status": "success", "pid": pid, "action": "killed"}
                else:
                    return {"status": "error", "error": result.stderr.strip(), "pid": pid}
            else:
                import signal
                os.kill(pid, signal.SIGKILL)
                return {"status": "success", "pid": pid, "action": "killed"}
        except Exception as e:
            logger.error(f"Failed to kill process {pid}: {e}")
            return {"status": "error", "error": str(e), "pid": pid}

    async def block_ip(self, ip: str) -> dict:
        """
        Attempts to block an IP address using platform-native firewall.
        """
        if not ip:
            return {"status": "error", "error": "No IP specified."}
        
        clean_ip = ip.split()[0]
        
        try:
            logger.info(f"Ghostkey defensive action: Blocking IP {clean_ip}")
            if IS_WINDOWS:
                rule_name = f"Ghostkey_Block_{clean_ip.replace('.', '_')}"
                cmd = [
                    "netsh", "advfirewall", "firewall", "add", "rule",
                    f"name={rule_name}",
                    "dir=in", "action=block",
                    f"remoteip={clean_ip}",
                    "protocol=any"
                ]
            else:
                cmd = ["iptables", "-A", "INPUT", "-s", clean_ip, "-j", "DROP"]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return {"status": "success", "ip": clean_ip, "action": "blocked"}
            else:
                return {"status": "error", "error": result.stderr, "ip": clean_ip}
        except Exception as e:
            logger.error(f"Failed to block IP {clean_ip}: {e}")
            return {"status": "error", "error": str(e), "ip": clean_ip}

    async def system_audit(self) -> dict:
        """
        Performs a basic system security audit of the local host.
        Cross-platform: uses Windows or Linux commands as appropriate.
        """
        audit_results = {
            "os_info": {},
            "listening_ports": [],
            "running_processes": [],
            "disk_usage": [],
        }
        
        # OS Info
        audit_results["os_info"] = {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "hostname": platform.node(),
        }
        
        try:
            if IS_WINDOWS:
                # Listening ports via netstat
                result = subprocess.run(
                    ["netstat", "-an"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split("\n")
                    listening = [l.strip() for l in lines if "LISTENING" in l or "ESTABLISHED" in l]
                    audit_results["listening_ports"] = listening[:50]

                # Top processes via tasklist
                result = subprocess.run(
                    ["tasklist", "/FO", "CSV", "/NH"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split("\n")[:20]
                    processes = []
                    for line in lines:
                        parts = line.strip().strip('"').split('","')
                        if len(parts) >= 2:
                            processes.append({
                                "name": parts[0].strip('"'),
                                "pid": parts[1].strip('"') if len(parts) > 1 else "?",
                                "mem": parts[4].strip('"') if len(parts) > 4 else "?",
                            })
                    audit_results["running_processes"] = processes
            else:
                # Linux: listening ports via ss
                result = subprocess.run(
                    ["ss", "-tunlp"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split("\n")
                    ports = []
                    for line in lines[1:]:  # Skip header
                        parts = line.split()
                        if len(parts) >= 5:
                            ports.append({
                                "proto": parts[0],
                                "local_addr": parts[4],
                                "process": parts[-1] if len(parts) > 6 else "",
                            })
                    audit_results["listening_ports"] = ports[:50]

                # Linux: top processes
                result = subprocess.run(
                    ["ps", "-eo", "pid,comm,%cpu,%mem", "--sort=-%cpu"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split("\n")
                    processes = []
                    for line in lines[1:21]:  # Top 20
                        parts = line.split()
                        if len(parts) >= 4:
                            processes.append({
                                "pid": parts[0],
                                "name": parts[1],
                                "cpu": parts[2],
                                "mem": parts[3],
                            })
                    audit_results["running_processes"] = processes

        except Exception as e:
            logger.error(f"System audit error: {e}")
            audit_results["error"] = str(e)

        return {
            "status": "success",
            "audit": audit_results
        }

    async def get_system_info(self) -> dict:
        """Get cross-platform system information summary."""
        import shutil

        info = {
            "platform": platform.system(),
            "platform_release": platform.release(),
            "hostname": platform.node(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
        }

        # Disk usage
        try:
            usage = shutil.disk_usage("/")
            info["disk_total_gb"] = round(usage.total / (1024**3), 1)
            info["disk_used_gb"] = round(usage.used / (1024**3), 1)
            info["disk_free_gb"] = round(usage.free / (1024**3), 1)
            info["disk_percent_used"] = round((usage.used / usage.total) * 100, 1)
        except Exception:
            pass

        # CPU count
        info["cpu_count"] = os.cpu_count() or 0

        return info
