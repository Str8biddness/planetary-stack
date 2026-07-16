# control_plane/parameter_sweep.py
# Parameter sweep strategies for experiment optimization
# Implements grid search, random search, and bayesian optimization support

from typing import Dict, Any, List, Optional, Callable, Union
import random
import itertools
from dataclasses import dataclass
from enum import Enum
import uuid
from datetime import datetime

class SweepStrategy(Enum):
    GRID = "grid"
    RANDOM = "random"
    BAYESIAN = "bayesian"  # Placeholder for future implementation

@dataclass
class ParameterSpace:
    """Defines the search space for a parameter."""
    name: str
    type: str  # 'continuous', 'discrete', 'categorical'
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    choices: Optional[List[Any]] = None
    step: Optional[float] = None  # For discrete parameters

    def sample(self, strategy: SweepStrategy = SweepStrategy.RANDOM) -> Any:
        """Sample a value from this parameter space."""
        if self.type == 'categorical' and self.choices:
            return random.choice(self.choices)
        elif self.type == 'discrete' and self.choices:
            return random.choice(self.choices)
        elif self.type == 'continuous' and self.min_value is not None and self.max_value is not None:
            if strategy == SweepStrategy.GRID and self.step:
                steps = int((self.max_value - self.min_value) / self.step) + 1
                values = [self.min_value + i * self.step for i in range(steps)]
                return values
            return random.uniform(self.min_value, self.max_value)
        return None

    def get_grid_values(self) -> List[Any]:
        """Get all values for grid search."""
        if self.type == 'categorical' or self.type == 'discrete':
            return self.choices or []
        elif self.type == 'continuous' and self.min_value is not None and self.max_value is not None and self.step:
            steps = int((self.max_value - self.min_value) / self.step) + 1
            return [self.min_value + i * self.step for i in range(steps)]
        return [self.min_value] if self.min_value is not None else []

@dataclass
class Trial:
    """Represents a single trial in a parameter sweep."""
    id: str
    experiment_id: str
    parameters: Dict[str, Any]
    status: str  # 'pending', 'running', 'completed', 'failed', 'cancelled'
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    results: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, float]] = None
    error: Optional[str] = None

class ParameterSweep:
    """
    Manages parameter sweeps for experiment optimization.
    Supports grid search, random search, and bayesian optimization.
    """

    def __init__(self, strategy: SweepStrategy = SweepStrategy.GRID, max_trials: int = 100):
        self.strategy = strategy
        self.max_trials = max_trials
        self.parameter_spaces: Dict[str, ParameterSpace] = {}
        self.trials: Dict[str, Trial] = {}
        self.experiment_id: Optional[str] = None
        self.fixed_params: Dict[str, Any] = {}

    def add_parameter(self, name: str, param_space: ParameterSpace):
        """Add a parameter to the sweep."""
        self.parameter_spaces[name] = param_space

    def set_fixed_parameters(self, params: Dict[str, Any]):
        """Set fixed parameters that don't vary across trials."""
        self.fixed_params = params

    def generate_trials(self, experiment_id: str) -> List[Trial]:
        """Generate all trials for the sweep."""
        self.experiment_id = experiment_id

        if self.strategy == SweepStrategy.GRID:
            return self._generate_grid_trials(experiment_id)
        elif self.strategy == SweepStrategy.RANDOM:
            return self._generate_random_trials(experiment_id)
        else:
            raise NotImplementedError(f"Strategy {self.strategy} not yet implemented")

    def _generate_grid_trials(self, experiment_id: str) -> List[Trial]:
        """Generate trials for grid search."""
        # Get all parameter combinations
        param_names = list(self.parameter_spaces.keys())
        param_values = [self.parameter_spaces[name].get_grid_values() for name in param_names]

        trials = []
        for combination in itertools.product(*param_values):
            params = dict(zip(param_names, combination))
            params.update(self.fixed_params)

            trial = Trial(
                id=str(uuid.uuid4()),
                experiment_id=experiment_id,
                parameters=params,
                status='pending',
                created_at=datetime.now()
            )
            trials.append(trial)
            self.trials[trial.id] = trial

        return trials[:self.max_trials]

    def _generate_random_trials(self, experiment_id: str) -> List[Trial]:
        """Generate trials for random search."""
        trials = []
        for _ in range(self.max_trials):
            params = {}
            for name, space in self.parameter_spaces.items():
                params[name] = space.sample(SweepStrategy.RANDOM)
            params.update(self.fixed_params)

            trial = Trial(
                id=str(uuid.uuid4()),
                experiment_id=experiment_id,
                parameters=params,
                status='pending',
                created_at=datetime.now()
            )
            trials.append(trial)
            self.trials[trial.id] = trial

        return trials

    def get_next_trial(self) -> Optional[Trial]:
        """Get the next pending trial to run."""
        for trial in self.trials.values():
            if trial.status == 'pending':
                return trial
        return None

    def start_trial(self, trial_id: str):
        """Mark a trial as running."""
        if trial_id in self.trials:
            self.trials[trial_id].status = 'running'
            self.trials[trial_id].started_at = datetime.now()

    def complete_trial(self, trial_id: str, results: Dict[str, Any], metrics: Dict[str, float]):
        """Mark a trial as completed with results."""
        if trial_id in self.trials:
            trial = self.trials[trial_id]
            trial.status = 'completed'
            trial.completed_at = datetime.now()
            trial.results = results
            trial.metrics = metrics

    def fail_trial(self, trial_id: str, error: str):
        """Mark a trial as failed."""
        if trial_id in self.trials:
            self.trials[trial_id].status = 'failed'
            self.trials[trial_id].completed_at = datetime.now()
            self.trials[trial_id].error = error

    def get_best_trial(self, metric_name: str, maximize: bool = True) -> Optional[Trial]:
        """Get the best trial based on a metric."""
        completed_trials = [t for t in self.trials.values() if t.status == 'completed' and t.metrics and metric_name in t.metrics]

        if not completed_trials:
            return None

        if maximize:
            return max(completed_trials, key=lambda t: t.metrics[metric_name])
        else:
            return min(completed_trials, key=lambda t: t.metrics[metric_name])

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the sweep."""
        statuses = {}
        for trial in self.trials.values():
            statuses[trial.status] = statuses.get(trial.status, 0) + 1

        return {
            'experiment_id': self.experiment_id,
            'strategy': self.strategy.value,
            'total_trials': len(self.trials),
            'statuses': statuses,
            'completed': statuses.get('completed', 0),
            'failed': statuses.get('failed', 0),
            'pending': statuses.get('pending', 0),
            'running': statuses.get('running', 0),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the sweep to a dictionary."""
        return {
            'strategy': self.strategy.value,
            'max_trials': self.max_trials,
            'parameter_spaces': {
                name: {
                    'name': space.name,
                    'type': space.type,
                    'min_value': space.min_value,
                    'max_value': space.max_value,
                    'choices': space.choices,
                    'step': space.step,
                }
                for name, space in self.parameter_spaces.items()
            },
            'fixed_params': self.fixed_params,
            'trials': {
                trial_id: {
                    'id': trial.id,
                    'experiment_id': trial.experiment_id,
                    'parameters': trial.parameters,
                    'status': trial.status,
                    'created_at': trial.created_at.isoformat(),
                    'started_at': trial.started_at.isoformat() if trial.started_at else None,
                    'completed_at': trial.completed_at.isoformat() if trial.completed_at else None,
                    'results': trial.results,
                    'metrics': trial.metrics,
                    'error': trial.error,
                }
                for trial_id, trial in self.trials.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ParameterSweep':
        """Deserialize a sweep from a dictionary."""
        sweep = cls(
            strategy=SweepStrategy(data['strategy']),
            max_trials=data['max_trials']
        )

        # Restore parameter spaces
        for name, space_data in data.get('parameter_spaces', {}).items():
            sweep.parameter_spaces[name] = ParameterSpace(
                name=space_data['name'],
                type=space_data['type'],
                min_value=space_data.get('min_value'),
                max_value=space_data.get('max_value'),
                choices=space_data.get('choices'),
                step=space_data.get('step'),
            )

        sweep.fixed_params = data.get('fixed_params', {})

        # Restore trials
        for trial_id, trial_data in data.get('trials', {}).items():
            trial = Trial(
                id=trial_data['id'],
                experiment_id=trial_data['experiment_id'],
                parameters=trial_data['parameters'],
                status=trial_data['status'],
                created_at=datetime.fromisoformat(trial_data['created_at']),
                started_at=datetime.fromisoformat(trial_data['started_at']) if trial_data['started_at'] else None,
                completed_at=datetime.fromisoformat(trial_data['completed_at']) if trial_data['completed_at'] else None,
                results=trial_data.get('results'),
                metrics=trial_data.get('metrics'),
                error=trial_data.get('error'),
            )
            sweep.trials[trial_id] = trial

        return sweep
