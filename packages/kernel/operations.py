# accelerators/operations.py

import asyncio
import time
from typing import Dict, Any, List
from .registry import AcceleratorRegistry

async def run_parallel_rollouts(prompt_template: str, variations: List[Dict[str, Any]], max_tokens: int, temperature: float, criteria: Dict[str, Any] = {"prefer_local_gpu": True}) -> Dict[str, Any]:
    """
    Run parallel rollouts using acceleration layer.
    """
    registry = AcceleratorRegistry()
    accelerator = registry.get_best_accelerator(criteria)
    if not accelerator:
        # Fallback to sequential local (placeholder)
        rollouts = []
        for i, variation in enumerate(variations):
            prompt = prompt_template.format(**variation)
            request = {"prompt": prompt, "max_tokens": max_tokens, "temperature": temperature}
            start_time = time.time()
            # Placeholder local inference
            response = f"Local response to: {prompt[:50]}..."
            latency_ms = (time.time() - start_time) * 1000
            rollouts.append({
                "variation_id": i,
                "text": response,
                "latency_ms": round(latency_ms, 2),
            })
        return {
            "rollouts": rollouts,
            "average_latency": sum(r["latency_ms"] for r in rollouts) / len(rollouts) if rollouts else 0,
        }

    # Parallel execution with accelerator
    async def run_one(variation: Dict[str, Any], vid: int):
        prompt = prompt_template.format(**variation)
        request = {"prompt": prompt, "max_tokens": max_tokens, "temperature": temperature}
        start_time = time.time()
        result = accelerator.run_inference(request)
        if "error" in result:
            # Fallback to local on error
            response = f"Fallback response to: {prompt[:50]}..."
        else:
            response = result.get("response", "")
        latency_ms = (time.time() - start_time) * 1000
        return {
            "variation_id": vid,
            "text": response,
            "latency_ms": round(latency_ms, 2),
        }

    tasks = [run_one(var, i) for i, var in enumerate(variations)]
    rollouts = await asyncio.gather(*tasks)
    latencies = [r["latency_ms"] for r in rollouts]
    return {
        "rollouts": rollouts,
        "average_latency": sum(latencies) / len(latencies) if latencies else 0,
    }

async def cluster_experiment_history(experiments: List[Dict[str, Any]], criteria: Dict[str, Any]) -> Dict[str, Any]:
    """
    Cluster experiment history using acceleration layer.
    """
    registry = AcceleratorRegistry()
    accelerator = registry.get_best_accelerator(criteria)
    if not accelerator:
        # Local simple clustering: hard-coded rules based on dominant metric
        clusters = {
            "CPU-bound": {"description": "High CPU usage experiments", "experiments": []},
            "IO-bound": {"description": "High disk/network IO experiments", "experiments": []},
            "Balanced": {"description": "Balanced resource usage", "experiments": []},
        }
        for exp in experiments:
            cpu = exp.get("metrics", {}).get("cpu_usage", 0)
            io = exp.get("metrics", {}).get("disk_io", 0) + exp.get("metrics", {}).get("net_io", 0)
            if cpu > 80:
                clusters["CPU-bound"]["experiments"].append(exp["id"])
            elif io > 50:
                clusters["IO-bound"]["experiments"].append(exp["id"])
            else:
                clusters["Balanced"]["experiments"].append(exp["id"])
        return {
            "clusters": clusters,
            "num_experiments": len(experiments),
            "num_clusters": len(clusters),
            "accelerator_used": "cpu_local",
        }

    # Remote clustering via accelerator
    summaries = []
    for exp in experiments:
        summary = f"Experiment {exp['id']}: host={exp.get('host', 'unknown')}, profile={exp.get('profile', 'unknown')}, cpu={exp.get('metrics', {}).get('cpu_usage', 0)}%, mem={exp.get('metrics', {}).get('mem_usage', 0)}%, disk_io={exp.get('metrics', {}).get('disk_io', 0)}, net_io={exp.get('metrics', {}).get('net_io', 0)}, timestamp={exp.get('timestamp', 'unknown')}."
        summaries.append(summary)

    prompt = f"Group these {len(experiments)} experiments into 3-5 clusters based on behavior patterns. Output JSON with clusters: {{'cluster_name': {{'description': 'short desc', 'experiments': [ids]}}}}. Experiments: {'. '.join(summaries)}"
    request = {"prompt": prompt, "max_tokens": 500, "temperature": 0.5}
    result = accelerator.run_inference(request)
    response_text = result.get("response", "")
    # Parse JSON (simple, assume well-formed)
    try:
        import json
        clusters = json.loads(response_text)
    except:
        clusters = {"error": {"description": "Failed to parse clustering response", "experiments": [e["id"] for e in experiments]}}

    return {
        "clusters": clusters,
        "num_experiments": len(experiments),
        "num_clusters": len(clusters),
        "accelerator_used": accelerator.describe()["type"],
    }
