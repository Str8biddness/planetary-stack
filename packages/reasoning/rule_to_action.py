"""
PPBRS Rule-to-Action Mapping Module
Maps rules to actions with priority, conditions, and effect tracking.
"""
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json


class ActionType(Enum):
    """Types of actions that can be triggered by rules.
    
    Attributes:
        RESPONSE: Direct response action
        TRANSFORMATION: Transform input data
        ESCALATION: Escalate to higher-priority handler
        BROADCAST: Broadcast to multiple handlers
        CHAIN_REASONING: Trigger reasoning chain
        FALLBACK: Fallback action when no rules match
    """
    RESPONSE = "response"
    TRANSFORMATION = "transformation"
    ESCALATION = "escalation"
    BROADCAST = "broadcast"
    CHAIN_REASONING = "chain_reasoning"
    FALLBACK = "fallback"


@dataclass
class Action:
    """An executable action mapped from rule conditions.
    
    Attributes:
        action_id: Unique action identifier
        action_type: The ActionType enum value
        handler: Callable that executes the action
        params: Parameters passed to the handler
        priority: Execution priority (higher = first)
        tags: Classification tags for filtering
        description: Human-readable description
    """
    action_id: str
    action_type: ActionType
    handler: Callable[[Dict], Any]
    params: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    tags: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class Rule:
    """A condition-action rule for mapping contexts to actions.
    
    Attributes:
        rule_id: Unique rule identifier
        name: Human-readable rule name
        condition: Callable that returns True when rule should fire
        actions: List of Actions to execute when condition is met
        weight: Rule weight for scoring and prioritization
        active: Whether the rule is currently active
        priority: Rule priority for ordering
        tags: Classification tags
        metadata: Additional rule metadata
    """
    rule_id: str
    name: str
    condition: Callable[[Dict], bool]
    actions: List[Action]
    weight: float = 1.0
    active: bool = True
    priority: int = 0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MappingResult:
    """Result of executing a mapped action.
    
    Attributes:
        rule_id: ID of the rule that triggered this action
        action: The Action that was executed
        success: Whether execution succeeded
        output: The output from the action handler
        execution_time_ms: Time taken to execute in milliseconds
        error: Error message if execution failed
    """
    rule_id: str
    action: Action
    success: bool
    output: Any
    execution_time_ms: float
    error: Optional[str] = None


class RuleToActionMapper:
    """
    Maps patterns/rules to actions with priority-based execution.
    """
    
    def __init__(self, default_priority: int = 0):
        """Initializes the RuleToActionMapper.

        Args:
            default_priority: The default priority to assign to rules if not specified.
        """
        self.rules: Dict[str, Rule] = {}
        self.default_priority = default_priority
        self.execution_history: List[MappingResult] = []
        self._action_registry: Dict[str, Action] = {}
        self._tag_index: Dict[str, set] = {}
        self._untagged_rules: set = set()
        self._trigger_key_index: Dict[str, set] = {}
        self._trigger_value_index: Dict[tuple, set] = {}
        self._trigger_value_key_rules: Dict[str, set] = {}
        self._untriggered_rules: set = set()
        
    def register_rule(self, rule: Rule) -> None:
        """Registers a Rule object with the mapper.

        Args:
            rule: The Rule instance to register.
        """
        previous = self.rules.get(rule.rule_id)
        if previous:
            self._remove_from_indexes(previous)

        self.rules[rule.rule_id] = rule
        self._add_to_indexes(rule)

    def _add_to_indexes(self, rule: Rule) -> None:
        if rule.tags:
            for tag in rule.tags:
                self._tag_index.setdefault(tag, set()).add(rule.rule_id)
        else:
            self._untagged_rules.add(rule.rule_id)

        trigger_values = rule.metadata.get("trigger_values", {})
        trigger_keys = set(rule.metadata.get("trigger_keys", [])) | set(trigger_values.keys())
        if trigger_keys:
            for key in trigger_keys:
                self._trigger_key_index.setdefault(key, set()).add(rule.rule_id)
            for key, value in trigger_values.items():
                self._trigger_value_index.setdefault((key, self._index_value(value)), set()).add(rule.rule_id)
                self._trigger_value_key_rules.setdefault(key, set()).add(rule.rule_id)
        else:
            self._untriggered_rules.add(rule.rule_id)

    def _remove_from_indexes(self, rule: Rule) -> None:
        self._untagged_rules.discard(rule.rule_id)
        self._untriggered_rules.discard(rule.rule_id)
        for tag in rule.tags:
            rule_ids = self._tag_index.get(tag)
            if rule_ids:
                rule_ids.discard(rule.rule_id)
                if not rule_ids:
                    del self._tag_index[tag]
        trigger_values = rule.metadata.get("trigger_values", {})
        trigger_keys = set(rule.metadata.get("trigger_keys", [])) | set(trigger_values.keys())
        for key in trigger_keys:
            rule_ids = self._trigger_key_index.get(key)
            if rule_ids:
                rule_ids.discard(rule.rule_id)
                if not rule_ids:
                    del self._trigger_key_index[key]
        for key, value in trigger_values.items():
            index_key = (key, self._index_value(value))
            rule_ids = self._trigger_value_index.get(index_key)
            if rule_ids:
                rule_ids.discard(rule.rule_id)
                if not rule_ids:
                    del self._trigger_value_index[index_key]
            scoped_ids = self._trigger_value_key_rules.get(key)
            if scoped_ids:
                scoped_ids.discard(rule.rule_id)
                if not scoped_ids:
                    del self._trigger_value_key_rules[key]

    def _index_value(self, value: Any) -> str:
        if value is None or isinstance(value, (str, int, float, bool)):
            return f"{type(value).__name__}:{value!r}"
        return json.dumps(value, sort_keys=True, default=str)

    def _candidate_rules(self, context: Dict[str, Any]) -> List[Rule]:
        context_tags = set(context.get('tags', []))
        tag_filtered = None
        if context_tags:
            tag_filtered = set(self._untagged_rules)
            for tag in context_tags:
                tag_filtered.update(self._tag_index.get(tag, set()))

        trigger_filtered = None
        for key, value in context.items():
            if key == 'tags':
                continue
            exact_ids = self._trigger_value_index.get((key, self._index_value(value)), set())
            key_ids = self._trigger_key_index.get(key, set())
            if exact_ids or key_ids:
                if trigger_filtered is None:
                    trigger_filtered = set(self._untriggered_rules)
                trigger_filtered.update(exact_ids)
                trigger_filtered.update(key_ids - self._trigger_value_key_rules.get(key, set()))

        candidate_ids = None
        for filtered in (tag_filtered, trigger_filtered):
            if filtered is None:
                continue
            candidate_ids = set(filtered) if candidate_ids is None else candidate_ids & filtered

        if candidate_ids is None:
            return list(self.rules.values())

        return [rule for rule_id, rule in self.rules.items() if rule_id in candidate_ids]
        
    def add_rule(self, rule_id: str, name: str,
                condition: Callable[[Dict], bool],
                actions: List[Action],
                weight: float = 1.0,
                priority: int = 0,
                tags: Optional[List[str]] = None,
                metadata: Optional[Dict[str, Any]] = None) -> None:
        """Constructs and registers a new rule.

        Args:
            rule_id: Unique identifier for the rule.
            name: Human-readable name of the rule.
            condition: Callable that evaluates if the rule should trigger.
            actions: List of actions associated with this rule.
            weight: Relative importance of the rule. Defaults to 1.0.
            priority: Rule priority for ordering. Defaults to 0.
            tags: Optional classification tags for the rule.
        """
        rule = Rule(
            rule_id=rule_id,
            name=name,
            condition=condition,
            actions=actions,
            weight=weight,
            priority=priority,
            tags=tags or [],
            metadata=metadata or {}
        )
        self.register_rule(rule)
    
    def register_action(self, action: Action) -> None:
        """Registers an action in the global registry for potential reuse.

        Args:
            action: The Action instance to register.
        """
        self._action_registry[action.action_id] = action
    
    def evaluate_rules(self, context: Dict[str, Any]) -> List[tuple]:
        """Evaluates all registered rules against a given context.

        Args:
            context: A dictionary containing the current execution state and metadata.

        Returns:
            A list of (Rule, score) tuples, sorted by priority and score descending.
        """
        results = []
        
        for rule in self._candidate_rules(context):
            if not rule.active:
                continue
            
            try:
                condition_met = rule.condition(context)
                if condition_met:
                    score = self._calculate_rule_score(rule, context)
                    results.append((rule, score))
            except Exception as e:
                print(f"Rule evaluation error for {rule.rule_id}: {e}")
        
        results.sort(key=lambda x: (x[0].priority, x[1]), reverse=True)
        return results
    
    def _calculate_rule_score(self, rule: Rule, context: Dict) -> float:
        """Calculates the match score for a rule based on weights and context tags.

        Args:
            rule: The Rule to score.
            context: The current context dictionary.

        Returns:
            The calculated score as a float.
        """
        base_score = 1.0
        tag_matches = 0
        
        context_tags = set(context.get('tags', []))
        rule_tags = set(rule.tags)
        
        if context_tags and rule_tags:
            tag_matches = len(context_tags & rule_tags) / len(rule_tags)
        
        return base_score * rule.weight * (1 + tag_matches)

    def _max_rule_score(self, rule: Rule, context: Dict) -> float:
        if context.get('tags') and rule.tags:
            return rule.weight * 2
        return rule.weight

    def evaluate_top_rule(self, context: Dict[str, Any]) -> Optional[tuple]:
        """Evaluates candidate rules only until the best single rule is known."""
        candidates = sorted(
            self._candidate_rules(context),
            key=lambda rule: (rule.priority, self._max_rule_score(rule, context)),
            reverse=True,
        )
        best = None
        best_score = float("-inf")

        for rule in candidates:
            if not rule.active:
                continue

            if best is not None:
                if rule.priority < best[0].priority:
                    break
                if rule.priority == best[0].priority and best_score >= self._max_rule_score(rule, context):
                    break

            try:
                condition_met = rule.condition(context)
                if condition_met:
                    score = self._calculate_rule_score(rule, context)
                    if best is None or (rule.priority, score) > (best[0].priority, best_score):
                        best = (rule, score)
                        best_score = score
            except Exception as e:
                print(f"Rule evaluation error for {rule.rule_id}: {e}")

        return best
    
    def execute_action(self, action: Action, context: Dict) -> MappingResult:
        """Executes a single action and records the result.

        Args:
            action: The Action instance to execute.
            context: The context to pass to the action handler.

        Returns:
            A MappingResult object containing the outcome and timing info.
        """
        import time
        start = time.time()
        
        try:
            output = action.handler(context, **action.params)
            success = True
            error = None
        except Exception as e:
            output = None
            success = False
            error = str(e)
        
        execution_time = (time.time() - start) * 1000
        
        result = MappingResult(
            rule_id=context.get('current_rule', 'unknown'),
            action=action,
            success=success,
            output=output,
            execution_time_ms=execution_time,
            error=error
        )
        
        self.execution_history.append(result)
        return result
    
    def map_to_action(self, context: Dict[str, Any]) -> Optional[MappingResult]:
        """Identifies and executes the single best matching action for a context.

        Args:
            context: The context dictionary to evaluate.

        Returns:
            The MappingResult of the executed action, or None if no rules matched.
        """
        best_match = self.evaluate_top_rule(context)

        if not best_match:
            return None
        
        best_rule, _ = best_match
        context['current_rule'] = best_rule.rule_id
        
        if best_rule.actions:
            best_action = max(best_rule.actions, key=lambda a: a.priority)
            return self.execute_action(best_action, context)
        
        return None
    
    def get_action_sequence(self, context: Dict[str, Any], max_actions: int = 3) -> List[MappingResult]:
        """Evaluates rules and executes a sequence of high-priority actions.

        Args:
            context: The context dictionary to evaluate.
            max_actions: Maximum number of rules to execute. Defaults to 3.

        Returns:
            A list of MappingResult objects for the executed sequence.
        """
        evaluated = self.evaluate_rules(context)
        results = []
        
        for rule, score in evaluated[:max_actions]:
            context['current_rule'] = rule.rule_id
            for action in sorted(rule.actions, key=lambda a: a.priority, reverse=True):
                result = self.execute_action(action, context)
                results.append(result)
                if not result.success:
                    break
        
        return results
    
    def apply_fallback(self, context: Dict[str, Any], 
                      fallback_action: Action) -> MappingResult:
        """Executes a specified fallback action when no rules match.

        Args:
            context: The current context dictionary.
            fallback_action: The Action to execute as a fallback.

        Returns:
            The MappingResult of the fallback action.
        """
        fallback_action.action_type = ActionType.FALLBACK
        context['current_rule'] = 'fallback'
        return self.execute_action(fallback_action, context)
    
    def export_rules(self, path: str) -> bool:
        """Exports the definitions of all registered rules to a JSON file.

        Args:
            path: The file path where rules should be saved.

        Returns:
            True if export succeeded, False otherwise.
        """
        try:
            data = []
            for rule in self.rules.values():
                data.append({
                    'rule_id': rule.rule_id,
                    'name': rule.name,
                    'weight': rule.weight,
                    'active': rule.active,
                    'tags': rule.tags,
                    'metadata': rule.metadata
                })
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"Error exporting rules: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """Generates performance and success statistics for action executions.

        Returns:
            A dictionary containing execution counts, success rates, and average timing.
        """
        if not self.execution_history:
            return {'total_executions': 0}
        
        total = len(self.execution_history)
        successes = sum(1 for r in self.execution_history if r.success)
        avg_time = sum(r.execution_time_ms for r in self.execution_history) / total
        
        return {
            'total_executions': total,
            'success_rate': successes / total,
            'avg_execution_time_ms': avg_time,
            'failure_count': total - successes
        }


class ActionSequenceBuilder:
    """
    Build action sequences with dependencies and conditions.
    """
    
    def __init__(self):
        """Initializes the ActionSequenceBuilder."""
        self.sequences: Dict[str, List[str]] = {}
        self.dependencies: Dict[str, List[str]] = {}
        
    def add_sequence(self, sequence_id: str, action_ids: List[str]) -> None:
        """Defines a named sequence of action IDs.

        Args:
            sequence_id: Unique name for the sequence.
            action_ids: Ordered list of action identifiers in the sequence.
        """
        self.sequences[sequence_id] = action_ids
        
    def add_dependency(self, action_id: str, depends_on: List[str]) -> None:
        """Specifies that an action depends on other actions completing first.

        Args:
            action_id: The ID of the dependent action.
            depends_on: List of action IDs that must be satisfied first.
        """
        self.dependencies[action_id] = depends_on
        
    def get_executable_sequence(self, sequence_id: str, 
                                 satisfied: Optional[Dict[str, bool]] = None) -> List[str]:
        """Calculates an executable order for a sequence, respecting dependencies.

        Args:
            sequence_id: The sequence identifier to resolve.
            satisfied: Optional dictionary tracking which actions are already complete.

        Returns:
            An ordered list of action IDs that can be executed.
        """
        satisfied = satisfied or {}
        sequence = self.sequences.get(sequence_id, [])
        
        executable = []
        remaining = list(sequence)
        
        while remaining:
            for action in list(remaining):
                deps = self.dependencies.get(action, [])
                if all(satisfied.get(d, False) for d in deps):
                    executable.append(action)
                    remaining.remove(action)
                    satisfied[action] = True
        
        return executable
