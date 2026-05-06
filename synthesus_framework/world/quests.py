"""
Synthesus 2.0 — World Systems: Dynamic Quest Generator (Phase 11B)
"The world creates its own stories from its own problems"

A contradiction/tension detector that scans world state and spawns quests:
1. Scans economy for shortages, disrupted routes, price spikes
2. Scans NPC schedules for unmet needs, conflicts
3. Scans weather for dangerous conditions
4. Matches tensions to quest templates
5. Assigns quests to appropriate NPCs
6. Tracks quest state: available → active → completed/failed/expired
7. Rewards feed back into the economy

Design principles:
- Quests emerge from world state, not from a static list
- Every quest has a cause (a tension) and effect (resolves or worsens it)
- NPCs give quests because they NEED something, not because they're quest dispensers
- Multiple solutions per quest (player agency)
- Quest expiry: tensions can resolve themselves
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ──────────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────────

class QuestState(str, Enum):
    """Quest lifecycle states."""
    AVAILABLE = "available"       # Quest exists, no one has taken it
    OFFERED = "offered"           # NPC has offered it to a player
    ACTIVE = "active"             # Player accepted, in progress
    COMPLETED = "completed"       # Player finished it
    FAILED = "failed"             # Player failed or quest expired
    EXPIRED = "expired"           # Tension resolved before completion
    CANCELLED = "cancelled"       # Quest giver removed it


class QuestDifficulty(str, Enum):
    """Difficulty tiers."""
    TRIVIAL = "trivial"
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EPIC = "epic"


class TensionType(str, Enum):
    """Types of world tensions that generate quests."""
    RESOURCE_SHORTAGE = "resource_shortage"
    TRADE_DISRUPTION = "trade_disruption"
    PRICE_CRISIS = "price_crisis"
    NPC_CONFLICT = "npc_conflict"
    NPC_UNMET_NEED = "npc_unmet_need"
    WEATHER_DANGER = "weather_danger"
    PROSPERITY_DROP = "prosperity_drop"
    POPULATION_PRESSURE = "population_pressure"
    CRIME = "crime"
    EXPLORATION = "exploration"


@dataclass
class WorldTension:
    """A detected tension/contradiction in the world state."""
    tension_type: TensionType
    severity: float                     # 0-1, how urgent
    region: str
    description: str
    source_flags: Dict[str, Any] = field(default_factory=dict)
    detected_at: float = field(default_factory=time.time)
    resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.tension_type.value,
            "severity": round(self.severity, 3),
            "region": self.region,
            "description": self.description,
            "resolved": self.resolved,
        }


@dataclass
class QuestObjective:
    """A single objective within a quest."""
    description: str
    objective_type: str             # "fetch", "deliver", "kill", "talk", "escort", "investigate"
    target: str                     # What/who to interact with
    quantity: int = 1
    current: int = 0
    optional: bool = False

    @property
    def is_complete(self) -> bool:
        return self.current >= self.quantity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "type": self.objective_type,
            "target": self.target,
            "quantity": self.quantity,
            "current": self.current,
            "complete": self.is_complete,
            "optional": self.optional,
        }


@dataclass
class QuestReward:
    """Reward for completing a quest."""
    gold: int = 0
    items: List[str] = field(default_factory=list)
    reputation: Dict[str, int] = field(default_factory=dict)  # npc_id → rep change
    world_effects: Dict[str, Any] = field(default_factory=dict)  # flags to set on completion
    experience: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gold": self.gold,
            "items": self.items,
            "reputation": self.reputation,
            "experience": self.experience,
        }


@dataclass
class Quest:
    """A dynamically generated quest."""
    quest_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = ""
    description: str = ""
    state: QuestState = QuestState.AVAILABLE
    difficulty: QuestDifficulty = QuestDifficulty.MEDIUM
    quest_giver: Optional[str] = None          # NPC character_id
    region: str = ""
    tension: Optional[WorldTension] = None      # What caused this quest
    objectives: List[QuestObjective] = field(default_factory=list)
    reward: QuestReward = field(default_factory=QuestReward)
    prerequisites: List[str] = field(default_factory=list)  # Other quest IDs
    time_limit_ticks: Optional[int] = None      # None = no limit
    ticks_remaining: Optional[int] = None
    created_at: float = field(default_factory=time.time)
    tags: Set[str] = field(default_factory=set)

    @property
    def is_complete(self) -> bool:
        """All non-optional objectives done."""
        return all(
            obj.is_complete for obj in self.objectives if not obj.optional
        )

    @property
    def progress(self) -> float:
        """0-1 progress on required objectives."""
        required = [o for o in self.objectives if not o.optional]
        if not required:
            return 1.0
        done = sum(1 for o in required if o.is_complete)
        return done / len(required)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.quest_id,
            "title": self.title,
            "description": self.description,
            "state": self.state.value,
            "difficulty": self.difficulty.value,
            "quest_giver": self.quest_giver,
            "region": self.region,
            "objectives": [o.to_dict() for o in self.objectives],
            "reward": self.reward.to_dict(),
            "progress": round(self.progress, 2),
            "tension": self.tension.to_dict() if self.tension else None,
            "ticks_remaining": self.ticks_remaining,
            "tags": list(self.tags),
        }


# ──────────────────────────────────────────────────
# Quest Templates
# ──────────────────────────────────────────────────

@dataclass
class QuestTemplate:
    """A template for generating quests from tensions."""
    template_id: str
    tension_type: TensionType
    min_severity: float = 0.0          # Minimum severity to trigger
    title_template: str = ""           # f-string with {resource}, {region}, etc.
    description_template: str = ""
    difficulty: QuestDifficulty = QuestDifficulty.MEDIUM
    objective_templates: List[Dict[str, str]] = field(default_factory=list)
    reward_template: Dict[str, Any] = field(default_factory=dict)
    tags: Set[str] = field(default_factory=set)
    cooldown_ticks: int = 20           # Min ticks between spawns of this template
    _last_spawned: int = -999

    def can_spawn(self, tick: int) -> bool:
        return tick - self._last_spawned >= self.cooldown_ticks


# ──────────────────────────────────────────────────
# Built-in Templates
# ──────────────────────────────────────────────────

def _default_templates() -> List[QuestTemplate]:
    """Built-in quest templates for common tensions."""
    return [
        # Resource shortage → fetch quest
        QuestTemplate(
            template_id="fetch_scarce_resource",
            tension_type=TensionType.RESOURCE_SHORTAGE,
            min_severity=0.4,
            title_template="{resource} Shortage in {region}",
            description_template=(
                "The supply of {resource} in {region} has dropped critically. "
                "A local merchant needs someone to acquire more before prices "
                "spiral out of control."
            ),
            difficulty=QuestDifficulty.EASY,
            objective_templates=[
                {"type": "fetch", "target": "{resource}", "quantity": "10",
                 "description": "Acquire {resource} (10 units)"},
                {"type": "deliver", "target": "{quest_giver}", "quantity": "1",
                 "description": "Deliver to the merchant", "optional": "false"},
            ],
            reward_template={"gold": 50, "reputation": 10, "experience": 25},
            tags={"economy", "fetch", "merchant"},
            cooldown_ticks=15,
        ),

        # Trade disruption → clear route
        QuestTemplate(
            template_id="clear_trade_route",
            tension_type=TensionType.TRADE_DISRUPTION,
            min_severity=0.5,
            title_template="Road to {region} Blocked",
            description_template=(
                "The trade route to {region} has been disrupted. Caravans "
                "can't get through. Someone needs to investigate and clear "
                "the obstruction."
            ),
            difficulty=QuestDifficulty.MEDIUM,
            objective_templates=[
                {"type": "investigate", "target": "trade_route_{region}",
                 "quantity": "1",
                 "description": "Investigate the blocked trade route"},
                {"type": "kill", "target": "bandits", "quantity": "3",
                 "description": "Clear the bandits (optional)",
                 "optional": "true"},
            ],
            reward_template={"gold": 100, "reputation": 20, "experience": 50},
            tags={"combat", "trade", "exploration"},
            cooldown_ticks=25,
        ),

        # Price crisis → economic quest
        QuestTemplate(
            template_id="price_stabilization",
            tension_type=TensionType.PRICE_CRISIS,
            min_severity=0.6,
            title_template="Market Crisis: {resource}",
            description_template=(
                "{resource} prices in {region} have gone haywire. The local "
                "guild is looking for someone to help stabilize the market — "
                "either by finding alternative sources or negotiating with "
                "suppliers."
            ),
            difficulty=QuestDifficulty.HARD,
            objective_templates=[
                {"type": "talk", "target": "guild_master", "quantity": "1",
                 "description": "Speak with the guild master"},
                {"type": "fetch", "target": "{resource}", "quantity": "20",
                 "description": "Acquire a large shipment of {resource}"},
            ],
            reward_template={"gold": 200, "reputation": 30, "experience": 75},
            tags={"economy", "diplomacy"},
            cooldown_ticks=30,
        ),

        # Weather danger → rescue/escort
        QuestTemplate(
            template_id="weather_rescue",
            tension_type=TensionType.WEATHER_DANGER,
            min_severity=0.5,
            title_template="Storm Survivors in {region}",
            description_template=(
                "A severe storm has hit {region}. Travelers are stranded "
                "and need help getting to safety."
            ),
            difficulty=QuestDifficulty.MEDIUM,
            objective_templates=[
                {"type": "investigate", "target": "storm_area_{region}",
                 "quantity": "1",
                 "description": "Search the storm-damaged area"},
                {"type": "escort", "target": "survivors", "quantity": "3",
                 "description": "Escort survivors to safety"},
            ],
            reward_template={"gold": 75, "reputation": 25, "experience": 40},
            tags={"weather", "escort", "rescue"},
            cooldown_ticks=20,
        ),

        # NPC unmet need → personal quest
        QuestTemplate(
            template_id="npc_personal_need",
            tension_type=TensionType.NPC_UNMET_NEED,
            min_severity=0.3,
            title_template="A Favor for {quest_giver}",
            description_template=(
                "{quest_giver} needs help with a personal matter. They seem "
                "troubled and could use someone they trust."
            ),
            difficulty=QuestDifficulty.EASY,
            objective_templates=[
                {"type": "talk", "target": "{quest_giver}", "quantity": "1",
                 "description": "Listen to {quest_giver}'s problem"},
                {"type": "fetch", "target": "{resource}", "quantity": "5",
                 "description": "Find what they need"},
            ],
            reward_template={"gold": 25, "reputation": 15, "experience": 20},
            tags={"personal", "social"},
            cooldown_ticks=10,
        ),

        # Prosperity drop → investigation
        QuestTemplate(
            template_id="investigate_decline",
            tension_type=TensionType.PROSPERITY_DROP,
            min_severity=0.5,
            title_template="Troubled Times in {region}",
            description_template=(
                "{region} is struggling economically. The local leaders want "
                "someone to investigate the root cause and find a solution."
            ),
            difficulty=QuestDifficulty.HARD,
            objective_templates=[
                {"type": "investigate", "target": "{region}_economy",
                 "quantity": "1",
                 "description": "Investigate the economic decline"},
                {"type": "talk", "target": "merchants", "quantity": "3",
                 "description": "Speak with local merchants"},
                {"type": "talk", "target": "regional_leader", "quantity": "1",
                 "description": "Report findings to the regional leader"},
            ],
            reward_template={"gold": 150, "reputation": 35, "experience": 60},
            tags={"investigation", "diplomacy", "economy"},
            cooldown_ticks=40,
        ),

        # Exploration — triggered by low information
        QuestTemplate(
            template_id="explore_unknown",
            tension_type=TensionType.EXPLORATION,
            min_severity=0.2,
            title_template="Uncharted Territory Near {region}",
            description_template=(
                "Rumors of unexplored areas near {region} have caught the "
                "attention of locals. Someone brave enough to investigate "
                "could find valuable resources or danger."
            ),
            difficulty=QuestDifficulty.MEDIUM,
            objective_templates=[
                {"type": "investigate", "target": "unknown_area_{region}",
                 "quantity": "1",
                 "description": "Explore the unknown area"},
            ],
            reward_template={"gold": 80, "reputation": 10, "experience": 45},
            tags={"exploration", "discovery"},
            cooldown_ticks=35,
        ),
    ]


# ──────────────────────────────────────────────────
# Quest Generator
# ──────────────────────────────────────────────────

class QuestGenerator:
    """
    Scans world state for tensions and generates quests from templates.

    Workflow:
    1. detect_tensions(world_flags) → list of WorldTension
    2. generate_quests(tensions, available_npcs) → list of Quest
    3. tick() expires quests and checks if tensions resolved
    """

    def __init__(
        self,
        templates: Optional[List[QuestTemplate]] = None,
        max_active_quests: int = 20,
        max_quests_per_region: int = 5,
    ):
        self.templates = templates or _default_templates()
        self.max_active_quests = max_active_quests
        self.max_quests_per_region = max_quests_per_region

        self.active_quests: Dict[str, Quest] = {}
        self.completed_quests: List[Quest] = []
        self.failed_quests: List[Quest] = []
        self.tick_count: int = 0
        self._tension_history: List[WorldTension] = []

    # ------------------------------------------------------------------
    # Tension Detection
    # ------------------------------------------------------------------

    def detect_tensions(
        self, world_flags: Dict[str, Any]
    ) -> List[WorldTension]:
        """
        Scan world state flags for tensions/contradictions.

        Reads flags from economy, weather, NPC systems and identifies
        problems that could become quests.
        """
        tensions: List[WorldTension] = []

        for flag_name, flag_value in world_flags.items():
            # Economy: resource scarcity
            if "_scarcity" in flag_name and flag_value in (
                "critically_scarce", "scarce"
            ):
                parts = flag_name.split("_")
                # economy_{region}_{resource}_scarcity
                region = parts[1] if len(parts) > 2 else "unknown"
                resource = "_".join(parts[2:-1]) if len(parts) > 3 else "unknown"
                severity = 0.9 if flag_value == "critically_scarce" else 0.6
                tensions.append(WorldTension(
                    tension_type=TensionType.RESOURCE_SHORTAGE,
                    severity=severity,
                    region=region,
                    description=f"{resource} is {flag_value} in {region}",
                    source_flags={flag_name: flag_value},
                ))

            # Economy: trade disruption events
            elif flag_name.startswith("economy_event_trade_disruption_"):
                region = flag_name.replace(
                    "economy_event_trade_disruption_", ""
                )
                tensions.append(WorldTension(
                    tension_type=TensionType.TRADE_DISRUPTION,
                    severity=0.7,
                    region=region,
                    description=f"Trade routes disrupted in {region}",
                    source_flags={flag_name: flag_value},
                ))

            # Economy: prosperity drop
            elif "_prosperity" in flag_name:
                if isinstance(flag_value, (int, float)) and flag_value < 0.5:
                    region = flag_name.replace(
                        "economy_", ""
                    ).replace("_prosperity", "")
                    tensions.append(WorldTension(
                        tension_type=TensionType.PROSPERITY_DROP,
                        severity=max(0.0, 1.0 - flag_value * 2),
                        region=region,
                        description=f"{region} prosperity critically low ({flag_value:.2f})",
                        source_flags={flag_name: flag_value},
                    ))

            # Economy: price crisis (price > 3x base)
            elif "_price" in flag_name and isinstance(flag_value, (int, float)):
                # Check if we have a matching base price
                base_flag = flag_name.replace("_price", "_base_price")
                base = world_flags.get(base_flag)
                if base and isinstance(base, (int, float)) and base > 0:
                    if flag_value / base > 3.0:
                        parts = flag_name.split("_")
                        region = parts[1] if len(parts) > 2 else "unknown"
                        resource = "_".join(parts[2:-1]) if len(parts) > 3 else "unknown"
                        tensions.append(WorldTension(
                            tension_type=TensionType.PRICE_CRISIS,
                            severity=min(1.0, flag_value / base / 5.0),
                            region=region,
                            description=f"{resource} prices {flag_value/base:.1f}x normal in {region}",
                            source_flags={flag_name: flag_value},
                        ))

            # Weather: dangerous conditions
            elif flag_name.startswith("weather_") and flag_name.endswith("_danger"):
                if flag_value:
                    region = flag_name.replace("weather_", "").replace("_danger", "")
                    tensions.append(WorldTension(
                        tension_type=TensionType.WEATHER_DANGER,
                        severity=0.6,
                        region=region,
                        description=f"Dangerous weather conditions in {region}",
                        source_flags={flag_name: flag_value},
                    ))

            # Weather: severe conditions
            elif flag_name.startswith("weather_") and "_severity" in flag_name:
                if isinstance(flag_value, (int, float)) and flag_value > 0.7:
                    region = flag_name.replace("weather_", "").replace("_severity", "")
                    tensions.append(WorldTension(
                        tension_type=TensionType.WEATHER_DANGER,
                        severity=flag_value,
                        region=region,
                        description=f"Severe weather in {region} (severity {flag_value:.1f})",
                        source_flags={flag_name: flag_value},
                    ))

            # NPC: unmet needs
            elif flag_name.startswith("npc_") and "_need_" in flag_name:
                if flag_value == "unmet":
                    parts = flag_name.split("_")
                    npc_id = parts[1] if len(parts) > 2 else "unknown"
                    tensions.append(WorldTension(
                        tension_type=TensionType.NPC_UNMET_NEED,
                        severity=0.4,
                        region="unknown",
                        description=f"NPC {npc_id} has an unmet need",
                        source_flags={flag_name: flag_value},
                    ))

        self._tension_history.extend(tensions)
        return tensions

    # ------------------------------------------------------------------
    # Quest Generation
    # ------------------------------------------------------------------

    def generate_quests(
        self,
        tensions: List[WorldTension],
        available_npcs: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[Quest]:
        """
        Generate quests from detected tensions using templates.

        Args:
            tensions: List of detected world tensions
            available_npcs: Dict of {npc_id: {"region": str, "role": str, ...}}
                           Used to assign quest givers.

        Returns:
            List of newly created quests.
        """
        available_npcs = available_npcs or {}
        new_quests: List[Quest] = []

        # Count active quests per region
        region_counts: Dict[str, int] = {}
        for q in self.active_quests.values():
            if q.state in (QuestState.AVAILABLE, QuestState.OFFERED,
                           QuestState.ACTIVE):
                region_counts[q.region] = region_counts.get(q.region, 0) + 1

        total_active = len([
            q for q in self.active_quests.values()
            if q.state in (QuestState.AVAILABLE, QuestState.OFFERED,
                           QuestState.ACTIVE)
        ])

        for tension in tensions:
            if total_active >= self.max_active_quests:
                break

            region_count = region_counts.get(tension.region, 0)
            if region_count >= self.max_quests_per_region:
                continue

            # Find matching templates
            matching = [
                t for t in self.templates
                if (t.tension_type == tension.tension_type
                    and tension.severity >= t.min_severity
                    and t.can_spawn(self.tick_count))
            ]

            if not matching:
                continue

            # Pick best template (highest severity match)
            template = matching[0]

            # Find an appropriate quest giver
            quest_giver = self._find_quest_giver(
                tension, template, available_npcs
            )

            # Build the quest
            quest = self._instantiate_quest(
                template, tension, quest_giver
            )

            self.active_quests[quest.quest_id] = quest
            new_quests.append(quest)
            template._last_spawned = self.tick_count
            total_active += 1
            region_counts[tension.region] = region_count + 1

        return new_quests

    def _find_quest_giver(
        self,
        tension: WorldTension,
        template: QuestTemplate,
        available_npcs: Dict[str, Dict[str, Any]],
    ) -> Optional[str]:
        """Find the best NPC to give this quest."""
        candidates = []
        for npc_id, npc_info in available_npcs.items():
            # Prefer NPCs in the same region
            if npc_info.get("region") == tension.region:
                candidates.append((npc_id, 2))
            else:
                candidates.append((npc_id, 1))

            # Bonus for matching role
            role = npc_info.get("role", "").lower()
            if "merchant" in template.tags and "merchant" in role:
                candidates[-1] = (npc_id, candidates[-1][1] + 1)
            elif "combat" in template.tags and any(
                r in role for r in ("guard", "warrior", "soldier")
            ):
                candidates[-1] = (npc_id, candidates[-1][1] + 1)

        if not candidates:
            return None

        # Return highest scored
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    def _instantiate_quest(
        self,
        template: QuestTemplate,
        tension: WorldTension,
        quest_giver: Optional[str],
    ) -> Quest:
        """Create a concrete quest from a template and tension."""
        # Extract variables for template strings
        resource = "unknown"
        if tension.source_flags:
            # Try to extract resource name from flag keys
            for key in tension.source_flags:
                parts = key.split("_")
                if len(parts) > 3 and parts[-1] in (
                    "scarcity", "price"
                ):
                    resource = "_".join(parts[2:-1])
                    break

        vars_dict = {
            "resource": resource,
            "region": tension.region,
            "quest_giver": quest_giver or "a local",
        }

        title = template.title_template.format(**vars_dict)
        description = template.description_template.format(**vars_dict)

        # Build objectives
        objectives = []
        for obj_t in template.objective_templates:
            target = obj_t.get("target", "unknown").format(**vars_dict)
            desc = obj_t.get("description", "").format(**vars_dict)
            objectives.append(QuestObjective(
                description=desc,
                objective_type=obj_t.get("type", "fetch"),
                target=target,
                quantity=int(obj_t.get("quantity", "1")),
                optional=obj_t.get("optional", "false").lower() == "true",
            ))

        # Build reward (scale with severity)
        base_reward = template.reward_template
        severity_mult = 0.5 + tension.severity
        reward = QuestReward(
            gold=int(base_reward.get("gold", 0) * severity_mult),
            reputation={
                quest_giver: int(base_reward.get("reputation", 0))
            } if quest_giver else {},
            experience=int(base_reward.get("experience", 0) * severity_mult),
        )

        # Time limit scales inversely with severity
        time_limit = None
        if tension.severity > 0.7:
            time_limit = 30  # Urgent: 30 ticks
        elif tension.severity > 0.4:
            time_limit = 60  # Normal: 60 ticks

        return Quest(
            title=title,
            description=description,
            state=QuestState.AVAILABLE,
            difficulty=template.difficulty,
            quest_giver=quest_giver,
            region=tension.region,
            tension=tension,
            objectives=objectives,
            reward=reward,
            time_limit_ticks=time_limit,
            ticks_remaining=time_limit,
            tags=set(template.tags),
        )

    # ------------------------------------------------------------------
    # Quest Lifecycle
    # ------------------------------------------------------------------

    def offer_quest(self, quest_id: str) -> Optional[Dict[str, Any]]:
        """Mark a quest as offered to the player. Returns quest dict."""
        quest = self.active_quests.get(quest_id)
        if quest and quest.state == QuestState.AVAILABLE:
            quest.state = QuestState.OFFERED
            return quest.to_dict()
        return None

    def accept_quest(self, quest_id: str) -> Optional[Dict[str, Any]]:
        """Player accepts a quest."""
        quest = self.active_quests.get(quest_id)
        if quest and quest.state in (QuestState.AVAILABLE, QuestState.OFFERED):
            quest.state = QuestState.ACTIVE
            return quest.to_dict()
        return None

    def update_objective(
        self, quest_id: str, objective_index: int, progress: int = 1
    ) -> Optional[Dict[str, Any]]:
        """Update progress on a quest objective."""
        quest = self.active_quests.get(quest_id)
        if not quest or quest.state != QuestState.ACTIVE:
            return None
        if 0 <= objective_index < len(quest.objectives):
            obj = quest.objectives[objective_index]
            obj.current = min(obj.quantity, obj.current + progress)

            # Check if quest is now complete
            if quest.is_complete:
                quest.state = QuestState.COMPLETED
                self.completed_quests.append(quest)

            return quest.to_dict()
        return None

    def fail_quest(self, quest_id: str, reason: str = "") -> Optional[Dict[str, Any]]:
        """Fail a quest."""
        quest = self.active_quests.get(quest_id)
        if quest and quest.state == QuestState.ACTIVE:
            quest.state = QuestState.FAILED
            self.failed_quests.append(quest)
            return quest.to_dict()
        return None

    def complete_quest(self, quest_id: str) -> Optional[Dict[str, Any]]:
        """
        Mark quest complete and return rewards.
        Called when all objectives are met.
        """
        quest = self.active_quests.get(quest_id)
        if not quest:
            return None

        if quest.state == QuestState.ACTIVE and quest.is_complete:
            quest.state = QuestState.COMPLETED
            self.completed_quests.append(quest)
            return {
                "quest": quest.to_dict(),
                "reward": quest.reward.to_dict(),
                "world_effects": quest.reward.world_effects,
            }
        return None

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def tick(self, world_flags: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Advance quest system by one tick.

        - Decrements time limits
        - Expires timed-out quests
        - Checks if tensions resolved (auto-expire quests)
        - Returns summary
        """
        self.tick_count += 1
        expired = []
        failed = []

        for qid, quest in list(self.active_quests.items()):
            if quest.state not in (
                QuestState.AVAILABLE, QuestState.OFFERED, QuestState.ACTIVE
            ):
                continue

            # Time limit
            if quest.ticks_remaining is not None:
                quest.ticks_remaining -= 1
                if quest.ticks_remaining <= 0:
                    if quest.state == QuestState.ACTIVE:
                        quest.state = QuestState.FAILED
                        failed.append(quest)
                        self.failed_quests.append(quest)
                    else:
                        quest.state = QuestState.EXPIRED
                        expired.append(quest)

            # Check if tension resolved
            if quest.tension and world_flags:
                still_tense = False
                for flag_name, expected in quest.tension.source_flags.items():
                    if world_flags.get(flag_name) == expected:
                        still_tense = True
                        break
                if not still_tense and quest.state == QuestState.AVAILABLE:
                    quest.state = QuestState.EXPIRED
                    expired.append(quest)

        # Clean up completed/failed/expired from active
        for qid in list(self.active_quests.keys()):
            if self.active_quests[qid].state in (
                QuestState.COMPLETED, QuestState.FAILED,
                QuestState.EXPIRED, QuestState.CANCELLED,
            ):
                del self.active_quests[qid]

        return {
            "tick": self.tick_count,
            "active_quests": len(self.active_quests),
            "expired": [q.to_dict() for q in expired],
            "failed": [q.to_dict() for q in failed],
            "total_completed": len(self.completed_quests),
            "total_failed": len(self.failed_quests),
        }

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_available_quests(
        self, region: Optional[str] = None, npc_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get quests available for pickup, optionally filtered."""
        results = []
        for quest in self.active_quests.values():
            if quest.state not in (QuestState.AVAILABLE, QuestState.OFFERED):
                continue
            if region and quest.region != region:
                continue
            if npc_id and quest.quest_giver != npc_id:
                continue
            results.append(quest.to_dict())
        return results

    def get_active_quests(self) -> List[Dict[str, Any]]:
        """Get all quests the player is currently working on."""
        return [
            q.to_dict()
            for q in self.active_quests.values()
            if q.state == QuestState.ACTIVE
        ]

    def get_npc_quests(self, npc_id: str) -> List[Dict[str, Any]]:
        """Get all quests assigned to a specific NPC."""
        return [
            q.to_dict()
            for q in self.active_quests.values()
            if q.quest_giver == npc_id
            and q.state in (QuestState.AVAILABLE, QuestState.OFFERED)
        ]

    def get_quest_summary(self) -> Dict[str, Any]:
        """High-level summary of the quest system."""
        by_state: Dict[str, int] = {}
        for q in self.active_quests.values():
            by_state[q.state.value] = by_state.get(q.state.value, 0) + 1
        return {
            "active": by_state,
            "total_completed": len(self.completed_quests),
            "total_failed": len(self.failed_quests),
            "tensions_detected": len(self._tension_history),
            "templates_available": len(self.templates),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize quest system state."""
        return {
            "tick_count": self.tick_count,
            "active_quests": {
                k: v.to_dict() for k, v in self.active_quests.items()
            },
            "completed_count": len(self.completed_quests),
            "failed_count": len(self.failed_quests),
        }
