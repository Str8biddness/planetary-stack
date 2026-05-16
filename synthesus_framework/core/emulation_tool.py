# emulation_tool.py

from typing import Any, Dict, Optional
import time
import random
import os
import subprocess
import json

class EmulationTool:
    """
    High-level interface for running emulation / simulation experiments.
    v2: Uses Docker for real sandboxed container experiments.
    """

    # Experiment profiles: container-safe emulation types
    PROFILES = {
        "cpu_stress_basic": {
            "description": "Moderate CPU load for short duration to test basic processing.",
            "duration": 30,
            "intensity": "moderate",
            "type": "cpu_stress",
            "metrics": ["cpu_usage", "memory_usage"],
        },
        "cpu_stress_heavy": {
            "description": "High CPU load within safe limits to simulate intensive computation.",
            "duration": 60,
            "intensity": "high",
            "type": "cpu_stress",
            "metrics": ["cpu_usage", "memory_usage"],
        },
        "io_stress_logwriter": {
            "description": "Disk I/O with log-like write patterns to test storage handling.",
            "duration": 45,
            "intensity": "moderate",
            "type": "io_stress",
            "metrics": ["disk_io", "cpu_usage"],
        },
        "net_sim_low_traffic": {
            "description": "Simulated low network load (loopback only) for traffic testing.",
            "duration": 20,
            "intensity": "low",
            "type": "net_sim",
            "metrics": ["cpu_usage", "memory_usage"],  # Note: real net metrics limited in isolated container
            "category": "sysops"
        },
        "gm_combat_burst": {
            "description": "Short, spiky CPU load and minor IO over ~30s to mimic combat rounds.",
            "duration": 30,
            "intensity": "high_burst",
            "type": "cpu_stress",
            "metrics": ["cpu_usage", "disk_io"],
            "category": "gm"
        },
        "gm_npc_swarm": {
            "description": "Many small concurrent tasks (threads/processes) over ~45s to simulate multiple NPCs acting at once; moderate CPU and IO.",
            "duration": 45,
            "intensity": "moderate",
            "type": "multi_task",
            "metrics": ["cpu_usage", "disk_io"],
            "category": "gm"
        },
        "gm_world_tick": {
            "description": "Low, steady background activity over ~60s to mimic world ticks; low CPU, some IO.",
            "duration": 60,
            "intensity": "low",
            "type": "background",
            "metrics": ["cpu_usage", "disk_io"],
            "category": "gm"
        },
    }
    def __init__(self):
        # In-memory registry for virtual hosts (now backed by Docker containers)
        self.hosts: Dict[str, Dict[str, Any]] = {}
        self.docker_available = self._check_docker()

    def _check_docker(self) -> bool:
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def create_host(self, config: Dict[str, Any]) -> str:
        """
        Create a Docker container as 'virtual host' and return an ID.
        """
        if not self.docker_available:
            # Fallback to simulation
            return self._simulate_create_host(config)

        host_id = f"emu_host_{len(self.hosts) + 1}"
        container_name = f"synthesus_{host_id}"

        # Default config: Ubuntu-based for experiments
        image = config.get("image", "ubuntu:latest")
        cpu_limit = config.get("cpu", "1")
        memory_limit = config.get("memory", "512m")

        try:
            # Create and start container
            cmd = [
                "docker", "run", "-d", "--name", container_name,
                "--cpus", cpu_limit, "--memory", memory_limit,
                "--network", "none",  # Isolated for safety
                image, "sleep", "infinity"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            container_id = result.stdout.strip()

            # Store metadata
            self.hosts[host_id] = {
                "id": host_id,
                "container_id": container_id,
                "container_name": container_name,
                "config": config,
                "created_at": time.time(),
                "experiments": [],
            }
            return host_id
        except subprocess.CalledProcessError as e:
            return f"error: {e.stderr}"

    def describe_host(self, host_id: str) -> Dict[str, Any]:
        """
        Return metadata about the host.
        """
        host = self.hosts.get(host_id)
        if not host:
            return {"error": "unknown_host"}

        if self.docker_available:
            try:
                cmd = ["docker", "inspect", host["container_name"]]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                inspect_data = json.loads(result.stdout)[0]
                host["status"] = inspect_data["State"]["Status"]
                host["cpu_usage"] = inspect_data["State"]["CpuStats"]  # Simplified
                return host
            except subprocess.CalledProcessError:
                return {"error": "docker_inspect_failed"}
        else:
            return host

    def run_experiment(self, host_id: str, experiment: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run an experiment on the Docker container.
        """
        host = self.hosts.get(host_id)
        if not host:
            return {"error": "unknown_host"}

        if not self.docker_available:
            return self._simulate_run_experiment(host_id, experiment)

        container_name = host["container_name"]
        exp_type = experiment.get("type", "cpu_stress")
        duration = experiment.get("duration", 10)

        try:
            # Install stress-ng if needed and run experiment
            if exp_type == "cpu_stress":
                cmd = ["docker", "exec", container_name, "bash", "-c", f"apt-get update && apt-get install -y stress-ng && stress-ng --cpu 2 --timeout {duration}s"]
            elif exp_type == "io_stress":
                cmd = ["docker", "exec", container_name, "bash", "-c", f"apt-get update && apt-get install -y stress-ng && stress-ng --io 2 --timeout {duration}s"]
            else:
                cmd = ["docker", "exec", container_name, "bash", "-c", f"apt-get update && apt-get install -y stress-ng && stress-ng --vm 1 --timeout {duration}s"]

            subprocess.run(cmd, capture_output=True, check=True)

            # Collect metrics (simplified: use docker stats)
            stats_cmd = ["docker", "stats", "--no-stream", container_name]
            stats_result = subprocess.run(stats_cmd, capture_output=True, text=True, check=True)
            # Parse stats (basic parse)
            lines = stats_result.stdout.split('\n')
            if len(lines) > 1:
                data = lines[1].split()
                cpu = data[2].replace('%', '') if '%' in data[2] else '0'
                mem = data[3].replace('%', '') if '%' in data[3] else '0'
                metrics = {
                    "cpu_usage": float(cpu) / 100.0,
                    "memory_usage": float(mem) / 100.0,
                    "disk_io": random.uniform(0.1, 0.5),  # Placeholder, docker stats doesn't give disk easily
                }
            else:
                metrics = {"cpu_usage": 0.5, "memory_usage": 0.5, "disk_io": 0.2}

            result = {
                "host_id": host_id,
                "experiment": experiment,
                "duration": duration,
                "metrics": metrics,
                "timestamp": time.time(),
            }
            host["experiments"].append(result)
            return result
        except subprocess.CalledProcessError as e:
            return {"error": f"experiment_failed: {e.stderr}"}

    def destroy_host(self, host_id: str) -> Dict[str, Any]:
        """
        Stop and remove the Docker container.
        """
        host = self.hosts.get(host_id)
        if not host:
            return {"error": "unknown_host"}

        if self.docker_available:
            container_name = host["container_name"]
            try:
                subprocess.run(["docker", "stop", container_name], capture_output=True, check=True)
                subprocess.run(["docker", "rm", container_name], capture_output=True, check=True)
            except subprocess.CalledProcessError as e:
                return {"error": f"destroy_failed: {e.stderr}"}

        del self.hosts[host_id]
        return {"status": "deleted", "host_id": host_id}

    def _simulate_create_host(self, config: Dict[str, Any]) -> str:
        """Fallback simulation."""
        host_id = f"emu_host_{len(self.hosts) + 1}"
        self.hosts[host_id] = {
            "id": host_id,
            "config": config,
            "created_at": time.time(),
            "experiments": [],
        }
        return host_id

    def _simulate_run_experiment(self, host_id: str, experiment: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback simulation."""
        host = self.hosts.get(host_id)
        if not host:
            return {"error": "unknown_host"}

        exp_type = experiment.get("type", "cpu_stress")
        duration = experiment.get("duration", 5)

        if exp_type == "cpu_stress":
            metrics = {
                "cpu_usage": random.uniform(0.7, 0.95),
                "memory_usage": random.uniform(0.4, 0.8),
                "disk_io": random.uniform(0.1, 0.3),
            }
        elif exp_type == "io_stress":
            metrics = {
                "cpu_usage": random.uniform(0.3, 0.6),
                "memory_usage": random.uniform(0.3, 0.7),
                "disk_io": random.uniform(0.7, 0.95),
            }
        else:
            metrics = {
                "cpu_usage": random.uniform(0.2, 0.8),
                "memory_usage": random.uniform(0.2, 0.8),
                "disk_io": random.uniform(0.2, 0.8),
            }

        result = {
            "host_id": host_id,
            "experiment": experiment,
            "duration": duration,
            "metrics": metrics,
            "timestamp": time.time(),
        }
        host["experiments"].append(result)
        return result
