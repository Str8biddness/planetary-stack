"""
Synthesus 2.0 — World Systems: NPC Scheduling System (Phase 11C)
"Every NPC has a life, not just a spot on the map"

A needs-driven scheduling system where NPCs:
1. Have needs (sleep, food, social, work, leisure)
2. Follow daily routines based on their role/archetype
3. Move between locations on a clock
4. Interrupt routines when needs become urgent
5. React to world events by changing plans
6. Are interruptible by player interaction

Design principles:
- Needs decay over time → NPC seeks to fulfill them
- Routines are templates, not rails — needs override routine
- Location is always known (NPCs don't teleport)
- Integrates with WorldStateReactor for event-driven interrupts
- Lightweight: ~0.1ms per NPC per tick, ~1 KB RAM per NPC
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


# ──────────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────────

class Activity(str, Enum):
    """What an NPC can be doing."""
    SLEEPING = "sleeping"
    EATING = "eating"
    WORKING = "working"
    SOCIALIZING = "socializing"
    SHOPPING = "shopping"
    TRAVELING = "traveling"
    GUARDING = "guarding"
    CRAFTING = "crafting"
    PRAYING = "praying"
    RELAXING = "relaxing"
    TRAINING = "training"
    IDLE = "idle"
    FLEEING = "fleeing"
    SHELTERING = "sheltering"
    PATROLLING = "patrolling"


class NeedType(str, Enum):
    """Fundamental NPC needs (Maslow-lite)."""
    SLEEP = "sleep"
    FOOD = "food"
    SOCIAL = "social"
    WORK = "work"
    SAFETY = "safety"
    LEISURE = "leisure"


class TimeOfDay(str, Enum):
    """Coarse time periods for scheduling."""
    DAWN = "dawn"           # 5-7
    MORNING = "morning"     # 7-12
    AFTERNOON = "afternoon" # 12-17
    EVENING = "evening"     # 17-21
    NIGHT = "night"         # 21-5

    @classmethod
    def from_hour(cls, hour: int) -> "TimeOfDay":
        """Convert 0-23 hour to time of day."""
        if 5 <= hour < 7:
            return cls.DAWN
        elif 7 <= hour < 12:
            return cls.MORNING
        elif 12 <= hour < 17:
            return cls.AFTERNOON
        elif 17 <= hour < 21:
            return cls.EVENING
        else:
            return cls.NIGHT


@dataclass
class NeedState:
    """A single need with its current level."""
    need_type: NeedType
    level: float = 1.0            # 0 = desperate, 1 = fully satisfied
    decay_rate: float = 0.01      # How fast it drops per tick
    priority: float = 1.0         # Base priority weight
    fulfilling_activities: List[Activity] = field(default_factory=list)

    @property
    def urgency(self) -> float:
        """0 = fine, 1 = critical. Inverse of level, weighted by priority."""
        return (1.0 - self.level) * self.priority

    def decay(self) -> None:
        """Reduce need level by decay rate."""
        self.level = max(0.0, self.level - self.decay_rate)

    def fulfill(self, amount: float = 0.2) -> None:
        """Restore need by amount."""
        self.level = min(1.0, self.level + amount)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.need_type.value,
            "level": round(self.level, 3),
            "urgency": round(self.urgency, 3),
            "decay_rate": self.decay_rate,
        }


@dataclass
class Location:
    """A place in the world an NPC can be."""
    name: str
    region: str
    location_type: str              # "shop", "home", "tavern", "market", "gate", etc.
    activities_available: Set[Activity] = field(default_factory=set)
    capacity: int = 10              # Max NPCs at once
    current_occupants: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "region": self.region,
            "type": self.location_type,
            "activities": [a.value for a in self.activities_available],
            "capacity": self.capacity,
            "occupants": self.current_occupants,
        }


@dataclass
class ScheduleEntry:
    """A single block in an NPC's daily routine."""
    time_of_day: TimeOfDay
    activity: Activity
    location: str                   # Location name
    duration_ticks: int = 10        # How many ticks to spend here
    priority: float = 0.5           # How important this scheduled activity is
    interruptible: bool = True      # Can needs override this?

    def to_dict(self) -> Dict[str, Any]:
        return {
            "time": self.time_of_day.value,
            "activity": self.activity.value,
            "location": self.location,
            "duration": self.duration_ticks,
            "priority": self.priority,
        }


# ──────────────────────────────────────────────────
# NPC Schedule (the brain of one NPC's daily life)
# ──────────────────────────────────────────────────

class NPCSchedule:
    """
    One NPC's scheduling brain.

    Combines a routine template with real-time need satisfaction.
    The planner picks the best action each tick by weighing:
    - Scheduled activity for this time of day
    - Most urgent unmet need
    - World state overrides (danger → flee, weather → shelter)
    """

    def __init__(
        self,
        npc_id: str,
        role: str = "villager",
        home_location: str = "home",
        work_location: str = "market",
        routine: Optional[List[ScheduleEntry]] = None,
        needs: Optional[Dict[NeedType, NeedState]] = None,
    ):
        self.npc_id = npc_id
        self.role = role
        self.home_location = home_location
        self.work_location = work_location

        # Current state
        self.current_location: str = home_location
        self.current_activity: Activity = Activity.IDLE
        self.activity_ticks_remaining: int = 0
        self.is_interrupted: bool = False
        self.interrupt_reason: str = ""

        # Routine
        self.routine = routine or self._default_routine()

        # Needs
        self.needs = needs or self._default_needs()

        # Stats
        self.tick_count: int = 0
        self.activity_log: List[Dict[str, Any]] = []  # Last N activities

    def _default_needs(self) -> Dict[NeedType, NeedState]:
        """Default needs for a standard NPC."""
        return {
            NeedType.SLEEP: NeedState(
                NeedType.SLEEP, level=1.0, decay_rate=0.008, priority=1.5,
                fulfilling_activities=[Activity.SLEEPING],
            ),
            NeedType.FOOD: NeedState(
                NeedType.FOOD, level=1.0, decay_rate=0.012, priority=1.3,
                fulfilling_activities=[Activity.EATING],
            ),
            NeedType.SOCIAL: NeedState(
                NeedType.SOCIAL, level=1.0, decay_rate=0.005, priority=0.8,
                fulfilling_activities=[Activity.SOCIALIZING],
            ),
            NeedType.WORK: NeedState(
                NeedType.WORK, level=0.5, decay_rate=0.003, priority=1.0,
                fulfilling_activities=[Activity.WORKING, Activity.CRAFTING,
                                       Activity.GUARDING],
            ),
            NeedType.SAFETY: NeedState(
                NeedType.SAFETY, level=1.0, decay_rate=0.0, priority=2.0,
                fulfilling_activities=[Activity.FLEEING, Activity.SHELTERING],
            ),
            NeedType.LEISURE: NeedState(
                NeedType.LEISURE, level=0.8, decay_rate=0.004, priority=0.5,
                fulfilling_activities=[Activity.RELAXING, Activity.SOCIALIZING],
            ),
        }

    def _default_routine(self) -> List[ScheduleEntry]:
        """Default daily routine."""
        return [
            ScheduleEntry(TimeOfDay.DAWN, Activity.SLEEPING,
                          self.home_location, duration_ticks=5),
            ScheduleEntry(TimeOfDay.MORNING, Activity.EATING,
                          self.home_location, duration_ticks=3),
            ScheduleEntry(TimeOfDay.MORNING, Activity.WORKING,
                          self.work_location, duration_ticks=15),
            ScheduleEntry(TimeOfDay.AFTERNOON, Activity.WORKING,
                          self.work_location, duration_ticks=15),
            ScheduleEntry(TimeOfDay.EVENING, Activity.EATING,
                          "tavern", duration_ticks=5),
            ScheduleEntry(TimeOfDay.EVENING, Activity.SOCIALIZING,
                          "tavern", duration_ticks=8),
            ScheduleEntry(TimeOfDay.NIGHT, Activity.SLEEPING,
                          self.home_location, duration_ticks=20),
        ]

    # ------------------------------------------------------------------
    # Core Tick
    # ------------------------------------------------------------------

    def tick(
        self,
        current_hour: int = 12,
        world_flags: Optional[Dict[str, Any]] = None,
        locations: Optional[Dict[str, Location]] = None,
    ) -> Dict[str, Any]:
        """
        Advance the NPC's schedule by one tick.

        Args:
            current_hour: 0-23 game hour
            world_flags: Global world state flags
            locations: Available locations in the world

        Returns:
            Dict with current state, activity, location, and any transitions.
        """
        self.tick_count += 1
        world_flags = world_flags or {}
        transition = None

        # Step 1: Decay all needs
        for need in self.needs.values():
            need.decay()

        # Step 2: Check for world state overrides (highest priority)
        override = self._check_world_overrides(world_flags)
        if override:
            if override != (self.current_activity, self.current_location):
                transition = self._transition_to(
                    override[0], override[1], reason="world_event"
                )
            # Fulfill safety need while sheltering/fleeing
            if self.needs.get(NeedType.SAFETY):
                self.needs[NeedType.SAFETY].level = min(
                    1.0, self.needs[NeedType.SAFETY].level + 0.05
                )
        # Step 3: Check for urgent needs (override routine)
        elif self._has_urgent_need():
            need_action = self._plan_need_fulfillment(locations)
            if need_action and need_action != (
                self.current_activity, self.current_location
            ):
                transition = self._transition_to(
                    need_action[0], need_action[1], reason="urgent_need"
                )
        # Step 4: Follow routine if nothing urgent
        elif self.activity_ticks_remaining <= 0:
            time_of_day = TimeOfDay.from_hour(current_hour)
            scheduled = self._get_scheduled_activity(time_of_day)
            if scheduled and scheduled != (
                self.current_activity, self.current_location
            ):
                transition = self._transition_to(
                    scheduled[0], scheduled[1], reason="routine"
                )

        # Step 5: Fulfill needs based on current activity
        self._fulfill_needs_from_activity()

        # Step 6: Decrement activity timer
        if self.activity_ticks_remaining > 0:
            self.activity_ticks_remaining -= 1

        return {
            "npc_id": self.npc_id,
            "tick": self.tick_count,
            "location": self.current_location,
            "activity": self.current_activity.value,
            "activity_ticks_remaining": self.activity_ticks_remaining,
            "needs": {k.value: v.to_dict() for k, v in self.needs.items()},
            "transition": transition,
            "most_urgent_need": self._most_urgent_need(),
        }

    def _check_world_overrides(
        self, world_flags: Dict[str, Any]
    ) -> Optional[Tuple[Activity, str]]:
        """Check if world state forces an activity change."""
        # Danger in NPC's region → flee or shelter
        region = self.current_location.split("_")[0] if "_" in self.current_location else "unknown"

        # Check for combat/danger
        if world_flags.get(f"combat_active_{region}"):
            if self.role in ("guard", "soldier", "warrior"):
                return (Activity.GUARDING, self.work_location)
            else:
                return (Activity.FLEEING, self.home_location)

        # Severe weather → shelter
        for key, val in world_flags.items():
            if key.startswith("weather_") and key.endswith("_danger"):
                if val and region in key:
                    return (Activity.SHELTERING, self.home_location)

        # Curfew
        if world_flags.get(f"curfew_{region}"):
            return (Activity.SLEEPING, self.home_location)

        return None

    def _has_urgent_need(self, threshold: float = 0.7) -> bool:
        """Check if any need is urgent enough to override routine."""
        return any(n.urgency > threshold for n in self.needs.values())

    def _most_urgent_need(self) -> Optional[str]:
        """Get the most urgent need type."""
        if not self.needs:
            return None
        most = max(self.needs.values(), key=lambda n: n.urgency)
        if most.urgency > 0.3:
            return most.need_type.value
        return None

    def _plan_need_fulfillment(
        self, locations: Optional[Dict[str, Location]] = None
    ) -> Optional[Tuple[Activity, str]]:
        """Pick the best activity and location to fulfill the most urgent need."""
        if not self.needs:
            return None

        most_urgent = max(self.needs.values(), key=lambda n: n.urgency)
        if not most_urgent.fulfilling_activities:
            return None

        best_activity = most_urgent.fulfilling_activities[0]

        # Find a location that supports this activity
        if locations:
            for loc_name, loc in locations.items():
                if (best_activity in loc.activities_available and
                        loc.current_occupants < loc.capacity):
                    return (best_activity, loc_name)

        # Fallback: common sense locations
        activity_locations = {
            Activity.SLEEPING: self.home_location,
            Activity.EATING: "tavern",
            Activity.SOCIALIZING: "tavern",
            Activity.WORKING: self.work_location,
            Activity.RELAXING: "park",
            Activity.FLEEING: self.home_location,
            Activity.SHELTERING: self.home_location,
        }
        location = activity_locations.get(best_activity, self.home_location)
        return (best_activity, location)

    def _get_scheduled_activity(
        self, time_of_day: TimeOfDay
    ) -> Optional[Tuple[Activity, str]]:
        """Get the scheduled activity for this time of day."""
        for entry in self.routine:
            if entry.time_of_day == time_of_day:
                return (entry.activity, entry.location)
        return None

    def _transition_to(
        self,
        activity: Activity,
        location: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Change the NPC's current activity and location."""
        old_activity = self.current_activity
        old_location = self.current_location

        self.current_activity = activity
        self.current_location = location
        self.is_interrupted = reason in ("world_event", "urgent_need")
        self.interrupt_reason = reason if self.is_interrupted else ""

        # Set duration based on activity
        durations = {
            Activity.SLEEPING: 20,
            Activity.EATING: 5,
            Activity.WORKING: 15,
            Activity.SOCIALIZING: 8,
            Activity.RELAXING: 10,
            Activity.GUARDING: 12,
            Activity.CRAFTING: 12,
            Activity.PATROLLING: 10,
            Activity.FLEEING: 3,
            Activity.SHELTERING: 15,
            Activity.SHOPPING: 5,
            Activity.TRAINING: 10,
            Activity.PRAYING: 5,
            Activity.IDLE: 5,
            Activity.TRAVELING: 3,
        }
        self.activity_ticks_remaining = durations.get(activity, 5)

        transition = {
            "from_activity": old_activity.value,
            "from_location": old_location,
            "to_activity": activity.value,
            "to_location": location,
            "reason": reason,
        }

        # Log it
        self.activity_log.append({
            "tick": self.tick_count,
            **transition,
        })
        # Keep only last 50
        if len(self.activity_log) > 50:
            self.activity_log = self.activity_log[-50:]

        return transition

    def _fulfill_needs_from_activity(self) -> None:
        """Current activity fulfills associated needs."""
        for need in self.needs.values():
            if self.current_activity in need.fulfilling_activities:
                need.fulfill(amount=0.05)

    # ------------------------------------------------------------------
    # External API
    # ------------------------------------------------------------------

    def interrupt(self, activity: Activity, location: str, reason: str) -> Dict[str, Any]:
        """Force-interrupt the NPC (player interaction, quest, etc.)."""
        return self._transition_to(activity, location, reason=reason)

    def get_state(self) -> Dict[str, Any]:
        """Full NPC schedule state."""
        return {
            "npc_id": self.npc_id,
            "role": self.role,
            "location": self.current_location,
            "activity": self.current_activity.value,
            "is_interrupted": self.is_interrupted,
            "needs": {k.value: v.to_dict() for k, v in self.needs.items()},
            "most_urgent_need": self._most_urgent_need(),
            "routine_entries": len(self.routine),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for save/load."""
        return {
            "npc_id": self.npc_id,
            "role": self.role,
            "current_location": self.current_location,
            "current_activity": self.current_activity.value,
            "activity_ticks_remaining": self.activity_ticks_remaining,
            "needs": {k.value: v.to_dict() for k, v in self.needs.items()},
            "tick_count": self.tick_count,
        }


# ──────────────────────────────────────────────────
# Scheduler Manager (coordinates all NPCs)
# ──────────────────────────────────────────────────

class SchedulerManager:
    """
    Coordinates all NPC schedules in the world.

    Provides:
    - Bulk tick for all NPCs
    - Location tracking (who's where)
    - NPC lookup by location
    - World state integration
    """

    def __init__(self):
        self.npcs: Dict[str, NPCSchedule] = {}
        self.locations: Dict[str, Location] = {}
        self.tick_count: int = 0
        self.current_hour: int = 12

    def register_npc(self, schedule: NPCSchedule) -> None:
        """Add an NPC to the scheduler."""
        self.npcs[schedule.npc_id] = schedule

    def register_location(self, location: Location) -> None:
        """Add a location to the world."""
        self.locations[location.name] = location

    def tick(
        self,
        current_hour: int = 12,
        world_flags: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Advance all NPCs by one tick.

        Returns summary with per-NPC states and location occupancy.
        """
        self.tick_count += 1
        self.current_hour = current_hour
        world_flags = world_flags or {}

        npc_states = {}
        transitions = []

        # Reset location occupancy
        for loc in self.locations.values():
            loc.current_occupants = 0

        # Tick each NPC
        for npc_id, schedule in self.npcs.items():
            state = schedule.tick(
                current_hour=current_hour,
                world_flags=world_flags,
                locations=self.locations,
            )
            npc_states[npc_id] = state
            if state.get("transition"):
                transitions.append(state["transition"])

        # Update location occupancy
        for schedule in self.npcs.values():
            loc = self.locations.get(schedule.current_location)
            if loc:
                loc.current_occupants += 1

        # Compute world flags for NPC locations
        npc_flags = self._compute_npc_flags()

        return {
            "tick": self.tick_count,
            "hour": current_hour,
            "time_of_day": TimeOfDay.from_hour(current_hour).value,
            "npc_count": len(self.npcs),
            "transitions": transitions,
            "flags": npc_flags,
            "locations": {
                name: {
                    "occupants": loc.current_occupants,
                    "capacity": loc.capacity,
                }
                for name, loc in self.locations.items()
            },
        }

    def _compute_npc_flags(self) -> Dict[str, Any]:
        """Compute world state flags from NPC states."""
        flags: Dict[str, Any] = {}
        for npc_id, schedule in self.npcs.items():
            prefix = f"npc_{npc_id}"
            flags[f"{prefix}_location"] = schedule.current_location
            flags[f"{prefix}_activity"] = schedule.current_activity.value

            # Publish unmet needs
            for need in schedule.needs.values():
                if need.urgency > 0.7:
                    flags[f"{prefix}_need_{need.need_type.value}"] = "unmet"

        return flags

    def get_npcs_at_location(self, location_name: str) -> List[str]:
        """Get all NPC IDs at a specific location."""
        return [
            npc_id
            for npc_id, schedule in self.npcs.items()
            if schedule.current_location == location_name
        ]

    def get_npc_state(self, npc_id: str) -> Optional[Dict[str, Any]]:
        """Get a single NPC's full state."""
        schedule = self.npcs.get(npc_id)
        return schedule.get_state() if schedule else None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize full scheduler state."""
        return {
            "tick_count": self.tick_count,
            "current_hour": self.current_hour,
            "npcs": {k: v.to_dict() for k, v in self.npcs.items()},
            "locations": {k: v.to_dict() for k, v in self.locations.items()},
        }

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    @classmethod
    def create_village(cls, npc_ids: Optional[List[str]] = None) -> "SchedulerManager":
        """Create a pre-configured village with locations and NPCs."""
        mgr = cls()

        # Locations
        for loc in [
            Location("market", "riverside", "market",
                     {Activity.WORKING, Activity.SHOPPING, Activity.SOCIALIZING}),
            Location("tavern", "riverside", "tavern",
                     {Activity.EATING, Activity.SOCIALIZING, Activity.RELAXING}),
            Location("smithy", "riverside", "workshop",
                     {Activity.WORKING, Activity.CRAFTING}),
            Location("barracks", "riverside", "military",
                     {Activity.GUARDING, Activity.TRAINING, Activity.SLEEPING}),
            Location("temple", "riverside", "temple",
                     {Activity.PRAYING, Activity.SOCIALIZING}),
            Location("park", "riverside", "outdoor",
                     {Activity.RELAXING, Activity.SOCIALIZING}),
        ]:
            mgr.register_location(loc)

        # Default NPCs
        default_npcs = npc_ids or ["merchant_01", "guard_01", "innkeeper_01"]
        role_map = {
            "merchant": ("villager", "home", "market"),
            "guard": ("guard", "barracks", "barracks"),
            "innkeeper": ("innkeeper", "tavern", "tavern"),
            "smith": ("smith", "home", "smithy"),
            "priest": ("priest", "temple", "temple"),
        }

        for npc_id in default_npcs:
            # Guess role from ID
            role = "villager"
            home = "home"
            work = "market"
            for key, (r, h, w) in role_map.items():
                if key in npc_id.lower():
                    role, home, work = r, h, w
                    break

            # Add home location if not exists
            home_loc_name = f"{npc_id}_home"
            if home == "home":
                mgr.register_location(Location(
                    home_loc_name, "riverside", "home",
                    {Activity.SLEEPING, Activity.EATING, Activity.RELAXING},
                    capacity=2,
                ))
                home = home_loc_name

            schedule = NPCSchedule(
                npc_id=npc_id,
                role=role,
                home_location=home,
                work_location=work,
            )
            mgr.register_npc(schedule)

        return mgr
