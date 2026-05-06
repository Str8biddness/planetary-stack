import subprocess
import logging
import os
import json

logger = logging.getLogger(__name__)

class SecurityTools:
    """
    Tools for system and network security auditing, specialized for the Ghostkey persona.
    """
    def __init__(self):
        pass

    async def run_nmap(self, target: str, arguments: str = "-F") -> dict:
        """
        Executes an nmap scan on the specified target.
        """
        if not target:
            return {"status": "error", "error": "No target specified for nmap scan."}
        
        # Basic validation to prevent command injection
        # In a production environment, this should be much stricter
        clean_target = target.split()[0] # Only take the first word as target
        
        # Basic arguments validation
        safe_args = []
        if arguments:
            # Only allow a subset of safe arguments
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
            import signal
            os.kill(pid, signal.SIGKILL)
            return {"status": "success", "pid": pid, "action": "killed"}
        except Exception as e:
            logger.error(f"Failed to kill process {pid}: {e}")
            return {"status": "error", "error": str(e), "pid": pid}

    async def block_ip(self, ip: str) -> dict:
        """
        Attempts to block an IP address using iptables.
        """
        if not ip:
            return {"status": "error", "error": "No IP specified."}
        
        # Clean IP
        clean_ip = ip.split()[0]
        
        try:
            logger.info(f"Ghostkey defensive action: Blocking IP {clean_ip}")
            # Requires root usually
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
        """
        audit_results = {
            "os_info": os.uname() if hasattr(os, "uname") else "Unknown",
            "listening_ports": [],
            "running_processes": [],
            "disk_usage": []
        }
        
        try:
            # Check listening ports using netstat or ss
            cmd = ["ss", "-tunlp"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                audit_results["listening_ports"] = result.stdout
            
            # Check top processes
            cmd = ["ps", "-ef", "--sort=-%cpu"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                audit_results["running_processes"] = "\n".join(result.stdout.splitlines()[:20]) # Top 20
                
        except Exception as e:
            logger.error(f"System audit error: {e}")
            audit_results["error"] = str(e)
            
        return {
            "status": "success",
            "audit": audit_results
        }
