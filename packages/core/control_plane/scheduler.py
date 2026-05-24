# control_plane/scheduler.py

from typing import List, Dict, Any, Optional
import time
import uuid
from datetime import datetime, timedelta
from .parameter_sweep import ParameterSweep, SweepStrategy, Trial

class ExperimentScheduler:
    """
    Enhanced scheduler for emulation experiments with parameter sweep support.
    """

    def __init__(self, device_manager, synthesus_master, emulation_tool, history_store=None):
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.sweeps: Dict[str, ParameterSweep] = {}
        self.device_manager = device_manager
        self.synthesus_master = synthesus_master
        self.emulation_tool = emulation_tool
        self.history_store = history_store
        # Caps: max experiments per hour per device, max concurrent
        self.max_per_hour_per_device = 4
        self.max_concurrent = 2
        self.running_experiments = set()  # job_ids currently running

    def list_schedules(self) -> List[Dict[str, Any]]:
        return list(self.jobs.values())

    def create_or_update_schedule(self, device_id: str, profile: str, interval: str, enabled: bool) -> Dict[str, Any]:
        # Validate device is ai_vm_host
        devices = self.device_manager.list_devices()["devices"]
        device = next((d for d in devices if d["id"] == device_id and "ai_vm_host" in d.get("capabilities", [])), None)
        if not device:
            return {"error": "device_not_eligible"}
        # Validate profile
        if profile not in self.emulation_tool.PROFILES:
            return {"error": "invalid_profile"}
        # Validate interval
        valid_intervals = ["15m", "1h", "6h", "24h"]
        if interval not in valid_intervals:
            return {"error": "invalid_interval"}

        job_id = str(uuid.uuid4())
        now = datetime.now()
        next_run = self._calculate_next_run(now, interval)
        self.jobs[job_id] = {
            "id": job_id,
            "device_id": device_id,
            "profile": profile,
            "interval": interval,
            "enabled": enabled,
            "last_run_at": None,
            "next_run_at": next_run.isoformat(),
        }
        return {"job_id": job_id, "message": "schedule_created"}

    def delete_schedule(self, job_id: str) -> Dict[str, Any]:
        if job_id in self.jobs:
            del self.jobs[job_id]
            return {"message": "schedule_deleted"}
        return {"error": "schedule_not_found"}

    def create_parameter_sweep(
        self,
        experiment_id: str,
        strategy: str = "grid",
        max_trials: int = 100,
        parameters: Optional[Dict[str, Any]] = None,
        fixed_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a parameter sweep for an experiment."""
        try:
            sweep = ParameterSweep(
                strategy=SweepStrategy(strategy),
                max_trials=max_trials
            )

            # Add parameter spaces
            if parameters:
                from .parameter_sweep import ParameterSpace
                for name, config in parameters.items():
                    sweep.add_parameter(name, ParameterSpace(
                        name=name,
                        type=config.get('type', 'continuous'),
                        min_value=config.get('min'),
                        max_value=config.get('max'),
                        choices=config.get('choices'),
                        step=config.get('step')
                    ))

            if fixed_params:
                sweep.set_fixed_parameters(fixed_params)

            # Generate trials
            trials = sweep.generate_trials(experiment_id)
            self.sweeps[experiment_id] = sweep

            return {
                "experiment_id": experiment_id,
                "sweep_id": str(uuid.uuid4()),
                "strategy": strategy,
                "total_trials": len(trials),
                "message": "sweep_created"
            }
        except Exception as e:
            return {"error": str(e)}

    def get_sweep_status(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a parameter sweep."""
        if experiment_id not in self.sweeps:
            return None
        return self.sweeps[experiment_id].get_summary()

    def run_next_trial(self, experiment_id: str, device_id: str) -> Dict[str, Any]:
        """Run the next pending trial in a sweep."""
        if experiment_id not in self.sweeps:
            return {"error": "sweep_not_found"}

        sweep = self.sweeps[experiment_id]
        trial = sweep.get_next_trial()

        if not trial:
            return {"message": "no_pending_trials"}

        # Run the trial
        sweep.start_trial(trial.id)
        self.running_experiments.add(trial.id)

        try:
            # Execute experiment with trial parameters
            result = self._run_trial_experiment(device_id, trial)

            if result.get("error"):
                sweep.fail_trial(trial.id, result["error"])
                return {"error": result["error"], "trial_id": trial.id}

            # Record success
            metrics = result.get("metrics", {})
            sweep.complete_trial(trial.id, result, metrics)

            # Record to history store if available
            if self.history_store:
                self.history_store.record_experiment({
                    "experiment_id": experiment_id,
                    "trial_id": trial.id,
                    "parameters": trial.parameters,
                    "results": result,
                    "metrics": metrics,
                    "timestamp": datetime.now().isoformat()
                })

            return {
                "trial_id": trial.id,
                "status": "completed",
                "metrics": metrics
            }

        except Exception as e:
            sweep.fail_trial(trial.id, str(e))
            return {"error": str(e), "trial_id": trial.id}
        finally:
            self.running_experiments.discard(trial.id)

    def get_best_trial(self, experiment_id: str, metric_name: str, maximize: bool = True) -> Optional[Dict[str, Any]]:
        """Get the best trial from a sweep."""
        if experiment_id not in self.sweeps:
            return None

        trial = self.sweeps[experiment_id].get_best_trial(metric_name, maximize)
        if not trial:
            return None

        return {
            "trial_id": trial.id,
            "parameters": trial.parameters,
            "metrics": trial.metrics,
            "status": trial.status
        }

    def _run_trial_experiment(self, device_id: str, trial: Trial) -> Dict[str, Any]:
        """Run a single trial experiment."""
        # This would integrate with the actual emulation tool
        # For now, return a mock result
        return {
            "metrics": {
                "accuracy": 0.8 + 0.1 * (hash(str(trial.parameters)) % 100) / 100,
                "latency": 100 + 50 * (hash(str(trial.parameters)) % 100) / 100
            },
            "success": True
        }

    async def tick(self, now: Optional[datetime] = None):
        """Run due jobs and trials, respecting caps."""
        if now is None:
            now = datetime.now()

        # Run scheduled jobs
        await self._run_scheduled_jobs(now)

        # Run pending sweep trials
        await self._run_pending_trials(now)

    async def _run_scheduled_jobs(self, now: datetime):
        """Run scheduled jobs that are due."""
        due_jobs = [j for j in self.jobs.values() if j["enabled"] and datetime.fromisoformat(j["next_run_at"]) <= now and j["id"] not in self.running_experiments]

        # Sort by due time, take up to max_concurrent
        due_jobs.sort(key=lambda j: datetime.fromisoformat(j["next_run_at"]))
        to_run = due_jobs[:self.max_concurrent]

        for job in to_run:
            # Check per-device cap (last hour)
            device_id = job["device_id"]
            recent_runs = [j for j in self.jobs.values() if j["device_id"] == device_id and j.get("last_run_at") and (now - datetime.fromisoformat(j["last_run_at"])).seconds < 3600]
            if len(recent_runs) >= self.max_per_hour_per_device:
                print(f"Scheduler: Skipping job {job['id']} for {device_id} - per-device cap reached")
                continue

            self.running_experiments.add(job["id"])
            try:
                result = await self.synthesus_master.safe_emulation_experiment_on_device(job["device_id"], job["profile"])
                if "error" in result:
                    print(f"Scheduler: Job {job['id']} failed: {result['error']}")
                else:
                    print(f"Scheduler: Job {job['id']} completed")
            except Exception as e:
                print(f"Scheduler: Job {job['id']} exception: {e}")
            finally:
                self.running_experiments.remove(job["id"])
                job["last_run_at"] = now.isoformat()
                job["next_run_at"] = self._calculate_next_run(now, job["interval"]).isoformat()

    async def _run_pending_trials(self, now: datetime):
        """Run pending sweep trials if capacity allows."""
        available_slots = self.max_concurrent - len(self.running_experiments)
        if available_slots <= 0:
            return

        # Find sweeps with pending trials
        for experiment_id, sweep in self.sweeps.items():
            if available_slots <= 0:
                break

            trial = sweep.get_next_trial()
            if trial:
                # Find eligible device
                devices = self.device_manager.list_devices()["devices"]
                eligible = [d for d in devices if "ai_vm_host" in d.get("capabilities", [])]

                if eligible:
                    device_id = eligible[0]["id"]
                    # Run trial (async fire-and-forget pattern)
                    import asyncio
                    asyncio.create_task(self._run_trial_async(experiment_id, trial.id, device_id))
                    available_slots -= 1

    async def _run_trial_async(self, experiment_id: str, trial_id: str, device_id: str):
        """Async helper to run a trial."""
        sweep = self.sweeps.get(experiment_id)
        if not sweep:
            return

        trial = sweep.trials.get(trial_id)
        if not trial:
            return

        sweep.start_trial(trial_id)
        self.running_experiments.add(trial_id)

        try:
            result = self._run_trial_experiment(device_id, trial)

            if result.get("error"):
                sweep.fail_trial(trial_id, result["error"])
            else:
                sweep.complete_trial(trial_id, result, result.get("metrics", {}))

                if self.history_store:
                    self.history_store.record_experiment({
                        "experiment_id": experiment_id,
                        "trial_id": trial_id,
                        "parameters": trial.parameters,
                        "results": result,
                        "metrics": result.get("metrics", {}),
                        "timestamp": datetime.now().isoformat()
                    })
        except Exception as e:
            sweep.fail_trial(trial_id, str(e))
        finally:
            self.running_experiments.discard(trial_id)

    def _calculate_next_run(self, from_time: datetime, interval: str) -> datetime:
        if interval == "15m":
            return from_time + timedelta(minutes=15)
        elif interval == "1h":
            return from_time + timedelta(hours=1)
        elif interval == "6h":
            return from_time + timedelta(hours=6)
        elif interval == "24h":
            return from_time + timedelta(hours=24)
        return from_time
