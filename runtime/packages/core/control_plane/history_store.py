# control_plane/history_store.py

import json
import os
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

class HistoryStore:
    """
    Enhanced JSONL-based history store for experiments, rollouts, and clusters.
    Supports metrics aggregation, querying, and data retention policies.
    """

    def __init__(self, path: str, retention_days: int = 30):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days

    def _append_record(self, record: Dict[str, Any]):
        """Append a record to the JSONL file."""
        try:
            # Add timestamp if not present
            if 'timestamp' not in record:
                record['timestamp'] = datetime.now().isoformat()

            with open(self.path, 'a') as f:
                json.dump(record, f)
                f.write('\n')
        except Exception as e:
            print(f"Warning: Failed to record to history store: {e}")

    def record_experiment(self, experiment_record: Dict[str, Any]):
        """Record an experiment run."""
        record = {"type": "experiment", **experiment_record}
        self._append_record(record)

    def list_recent_experiments(self, limit: int) -> List[Dict[str, Any]]:
        """List the most recent experiment records."""
        try:
            with open(self.path, 'r') as f:
                lines = f.readlines()
            experiments = [json.loads(line) for line in lines if json.loads(line).get("type") == "experiment"]
            return experiments[-limit:]  # Last N
        except Exception as e:
            print(f"Warning: Failed to read experiments from history store: {e}")
            return []

    def record_rollouts(self, experiment_id: str, rollouts: List[Dict[str, Any]]):
        """Record rollouts for an experiment."""
        record = {"type": "rollouts", "experiment_id": experiment_id, "rollouts": rollouts}
        self._append_record(record)

    def record_clusters(self, cluster_summary: Dict[str, Any]):
        """Record a clustering summary."""
        record = {"type": "clusters", **cluster_summary}
        self._append_record(record)

    def get_last_cluster_summary(self) -> Optional[Dict[str, Any]]:
        """Get the last recorded cluster summary."""
        try:
            with open(self.path, 'r') as f:
                lines = f.readlines()
            clusters = [json.loads(line) for line in lines if json.loads(line).get("type") == "clusters"]
            return clusters[-1] if clusters else None
        except Exception as e:
            print(f"Warning: Failed to read cluster summary from history store: {e}")
            return None

    # === Metrics Aggregation ===

    def query_records(
        self,
        record_type: Optional[str] = None,
        experiment_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        filter_fn: Optional[Callable[[Dict[str, Any]], bool]] = None
    ) -> List[Dict[str, Any]]:
        """Query records with filtering."""
        try:
            with open(self.path, 'r') as f:
                lines = f.readlines()

            records = []
            for line in lines:
                try:
                    record = json.loads(line)

                    # Apply filters
                    if record_type and record.get("type") != record_type:
                        continue
                    if experiment_id and record.get("experiment_id") != experiment_id:
                        continue

                    # Time range filter
                    if start_time or end_time:
                        record_time = None
                        if 'timestamp' in record:
                            try:
                                record_time = datetime.fromisoformat(record['timestamp'])
                            except:
                                pass
                        if record_time:
                            if start_time and record_time < start_time:
                                continue
                            if end_time and record_time > end_time:
                                continue

                    # Custom filter
                    if filter_fn and not filter_fn(record):
                        continue

                    records.append(record)
                except json.JSONDecodeError:
                    continue

            return records
        except Exception as e:
            print(f"Warning: Failed to query history store: {e}")
            return []

    def aggregate_metrics(
        self,
        metric_path: str,
        aggregation: str = 'mean',
        record_type: Optional[str] = 'experiment',
        experiment_id: Optional[str] = None,
        time_window_hours: Optional[int] = None
    ) -> Optional[float]:
        """
        Aggregate a metric across records.

        Args:
            metric_path: Dot-separated path to metric (e.g., 'results.accuracy')
            aggregation: 'mean', 'sum', 'min', 'max', 'count', 'std'
            record_type: Filter by record type
            experiment_id: Filter by experiment
            time_window_hours: Only consider records from last N hours
        """
        start_time = None
        if time_window_hours:
            start_time = datetime.now() - timedelta(hours=time_window_hours)

        records = self.query_records(
            record_type=record_type,
            experiment_id=experiment_id,
            start_time=start_time
        )

        # Extract metric values
        values = []
        for record in records:
            value = self._get_nested_value(record, metric_path)
            if value is not None and isinstance(value, (int, float)):
                values.append(value)

        if not values:
            return None

        if aggregation == 'mean':
            return sum(values) / len(values)
        elif aggregation == 'sum':
            return sum(values)
        elif aggregation == 'min':
            return min(values)
        elif aggregation == 'max':
            return max(values)
        elif aggregation == 'count':
            return len(values)
        elif aggregation == 'std':
            mean = sum(values) / len(values)
            variance = sum((x - mean) ** 2 for x in values) / len(values)
            return variance ** 0.5

        return None

    def get_metric_time_series(
        self,
        metric_path: str,
        record_type: Optional[str] = 'experiment',
        experiment_id: Optional[str] = None,
        time_window_hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get a time series of a metric."""
        start_time = datetime.now() - timedelta(hours=time_window_hours)

        records = self.query_records(
            record_type=record_type,
            experiment_id=experiment_id,
            start_time=start_time
        )

        time_series = []
        for record in records:
            value = self._get_nested_value(record, metric_path)
            timestamp = record.get('timestamp')
            if value is not None and timestamp:
                time_series.append({
                    'timestamp': timestamp,
                    'value': value,
                    'record_id': record.get('id') or record.get('experiment_id')
                })

        return sorted(time_series, key=lambda x: x['timestamp'])

    def compare_experiments(
        self,
        experiment_ids: List[str],
        metric_paths: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Compare metrics across multiple experiments."""
        comparison = {}

        for exp_id in experiment_ids:
            exp_data = {'experiment_id': exp_id, 'metrics': {}}

            for metric_path in metric_paths:
                value = self.aggregate_metrics(
                    metric_path=metric_path,
                    aggregation='mean',
                    experiment_id=exp_id
                )
                exp_data['metrics'][metric_path] = value

            comparison[exp_id] = exp_data

        return comparison

    def get_experiment_summary(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """Get a comprehensive summary of an experiment."""
        records = self.query_records(experiment_id=experiment_id)

        if not records:
            return None

        experiment_record = None
        rollouts = []
        clusters = []

        for record in records:
            if record.get('type') == 'experiment':
                experiment_record = record
            elif record.get('type') == 'rollouts':
                rollouts.extend(record.get('rollouts', []))
            elif record.get('type') == 'clusters':
                clusters.append(record)

        if not experiment_record:
            return None

        return {
            'experiment_id': experiment_id,
            'experiment': experiment_record,
            'rollout_count': len(rollouts),
            'cluster_count': len(clusters),
            'latest_cluster': clusters[-1] if clusters else None,
            'records': len(records),
        }

    # === Data Retention ===

    def apply_retention_policy(self):
        """Remove records older than retention_days."""
        if self.retention_days <= 0:
            return

        cutoff_time = datetime.now() - timedelta(days=self.retention_days)

        try:
            with open(self.path, 'r') as f:
                lines = f.readlines()

            kept_lines = []
            for line in lines:
                try:
                    record = json.loads(line)
                    record_time = None
                    if 'timestamp' in record:
                        try:
                            record_time = datetime.fromisoformat(record['timestamp'])
                        except:
                            pass

                    # Keep if no timestamp or timestamp is after cutoff
                    if record_time is None or record_time >= cutoff_time:
                        kept_lines.append(line)
                except json.JSONDecodeError:
                    # Keep malformed lines to be safe
                    kept_lines.append(line)

            # Rewrite file with only kept records
            with open(self.path, 'w') as f:
                f.writelines(kept_lines)

        except Exception as e:
            print(f"Warning: Failed to apply retention policy: {e}")

    def export_to_json(self, output_path: str, record_type: Optional[str] = None):
        """Export records to a JSON file."""
        records = self.query_records(record_type=record_type)

        try:
            with open(output_path, 'w') as f:
                json.dump(records, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to export history: {e}")

    # === Utility Methods ===

    def _get_nested_value(self, obj: Dict[str, Any], path: str) -> Any:
        """Get a nested value using dot notation."""
        keys = path.split('.')
        value = obj
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        return value

    def get_stats(self) -> Dict[str, Any]:
        """Get store statistics."""
        try:
            with open(self.path, 'r') as f:
                lines = f.readlines()

            total_records = len(lines)
            type_counts = defaultdict(int)
            experiment_ids = set()

            for line in lines:
                try:
                    record = json.loads(line)
                    type_counts[record.get('type', 'unknown')] += 1
                    if 'experiment_id' in record:
                        experiment_ids.add(record['experiment_id'])
                except:
                    type_counts['malformed'] += 1

            return {
                'total_records': total_records,
                'type_breakdown': dict(type_counts),
                'unique_experiments': len(experiment_ids),
                'file_size_bytes': os.path.getsize(self.path) if self.path.exists() else 0,
                'retention_days': self.retention_days,
            }
        except Exception as e:
            return {'error': str(e)}

