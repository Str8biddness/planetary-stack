"""
Synthesus 2.0 — World Simulation Coordinator (Phase 11F)
"One world, one clock, everything talks"

The master coordinator that:
1. Runs a single game clock (tick-based)
2. Ticks all 5 world systems in the correct order
3. Merges all world state flags into the WorldStateReactor
4. Feeds outputs from one system as inputs to others
5. Provides a single API for the game/server to call

Tick order (each tick):
  1. Weather → produces flags (visibility, danger, harvest impact)
  2. Economy → reads weather flags, produces pricing/scarcity flags
  3. NPC Scheduling → reads weather + economy flags, updates locations
  4. Quest Generator → reads ALL flags, detects tensions, spawns quests
  5. ML Swarm → assists all the above with predictions

This is the "puppet strings" that connect everything.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys
import os
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cognitive.world_state_reactor import WorldStateReactor

# Import world systems (graceful — coordinator works even if some are missing)
try:
    from world.economy import EconomyEngine
except ImportError:
    EconomyEngine = None  # type: ignore

try:
    from world.weather import WeatherEngine
except ImportError:
    WeatherEngine = None  # type: ignore

try:
    from world.scheduling import SchedulerManager
except ImportError:
    SchedulerManager = None  # type: ignore

try:
    from world.quests import QuestGenerator
except ImportError:
    QuestGenerator = None  # type: ignore

try:
    from world.ml_swarm import MLSwarmManager
except ImportError:
    MLSwarmManager = None  # type: ignore


class WorldSimulator:
    """
    The master world simulation coordinator.

    Runs the world clock and coordinates all systems.
    All systems communicate through the shared world state flag bus.
    """

    def __init__(
        self,
        economy: Optional[Any] = None,
        weather: Optional[Any] = None,
        scheduler: Optional[Any] = None,
        quest_gen: Optional[Any] = None,
        ml_swarm: Optional[Any] = None,
        seed: int = 42,
    ):
        # World systems (all optional — coordinator degrades gracefully)
        self.economy = economy
        self.weather = weather
        self.scheduler = scheduler
        self.quest_gen = quest_gen
        self.ml_swarm = ml_swarm

        # Shared world state (the flag bus)
        self._world_flags: Dict[str, Any] = {}

        # Clock
        self.tick_count: int = 0
        self.current_day: int = 0
        self.current_hour: int = 6      # Start at dawn

        # History
        self.tick_history: List[Dict[str, Any]] = []
        self._max_history: int = 100

    # ------------------------------------------------------------------
    # Main Loop
    # ------------------------------------------------------------------

    def tick(self) -> Dict[str, Any]:
        """
        Advance the entire world by one tick.

        Runs all systems in dependency order and merges their state flags.

        Returns a comprehensive summary.
        """
        self.tick_count += 1
        tick_start = time.time()

        # Advance clock
        self.current_hour = (self.current_hour + 1) % 24
        if self.current_hour == 0:
            self.current_day += 1

        summary: Dict[str, Any] = {
            "tick": self.tick_count,
            "day": self.current_day,
            "hour": self.current_hour,
            "systems": {},
        }

        # ── Step 1: Weather ──────────────────────────────────
        weather_result = {}
        if self.weather:
            weather_result = self.weather.tick(day=self.current_day)
            # Merge weather flags into world state
            if "flags" in weather_result:
                self._world_flags.update(weather_result["flags"])
            summary["systems"]["weather"] = {
                "transitions": weather_result.get("transitions", []),
                "season": weather_result.get("season", "unknown"),
            }

        # Publish to WorldStateReactor (so NPCs can react)
        self._publish_flags()

        # ── Step 2: Economy ──────────────────────────────────
        economy_result = {}
        if self.economy:
            # Weather affects economy: bad weather → reduced production
            self._apply_weather_to_economy()

            economy_result = self.economy.tick()
            # Merge economy flags
            if "flags" in economy_result:
                self._world_flags.update(economy_result["flags"])
            summary["systems"]["economy"] = {
                "events": economy_result.get("events", []),
                "trades": len(economy_result.get("trades", [])),
            }

        self._publish_flags()

        # ── Step 3: NPC Scheduling ───────────────────────────
        scheduler_result = {}
        if self.scheduler:
            scheduler_result = self.scheduler.tick(
                current_hour=self.current_hour,
                world_flags=self._world_flags,
            )
            # Merge NPC flags
            if "flags" in scheduler_result:
                self._world_flags.update(scheduler_result["flags"])
            summary["systems"]["scheduling"] = {
                "transitions": len(scheduler_result.get("transitions", [])),
                "npc_count": scheduler_result.get("npc_count", 0),
            }

        self._publish_flags()

        # ── Step 4: Quest Generation ─────────────────────────
        quest_result = {}
        if self.quest_gen:
            # Detect tensions from ALL accumulated flags
            tensions = self.quest_gen.detect_tensions(self._world_flags)

            # Generate quests from tensions (pass available NPCs)
            available_npcs = {}
            if self.scheduler:
                for npc_id, schedule in self.scheduler.npcs.items():
                    available_npcs[npc_id] = {
                        "region": schedule.current_location.split("_")[0]
                            if "_" in schedule.current_location
                            else "riverside",
                        "role": schedule.role,
                    }

            new_quests = self.quest_gen.generate_quests(
                tensions, available_npcs
            )

            # Tick quest timers
            quest_tick = self.quest_gen.tick(world_flags=self._world_flags)

            summary["systems"]["quests"] = {
                "tensions_detected": len(tensions),
                "new_quests": len(new_quests),
                "active_quests": quest_tick.get("active_quests", 0),
                "expired": len(quest_tick.get("expired", [])),
            }

        # ── Step 5: ML Swarm (advisory) ──────────────────────
        if self.ml_swarm and self.economy:
            # Use demand predictor for each region's resources
            for region_name, region in self.economy.regions.items():
                for res_name, resource in region.resources.items():
                    ratio = resource.supply_demand_ratio
                    scarcity = 1.0 - min(1.0, ratio)
                    supply_trend = -0.1 if ratio < 0.8 else (0.1 if ratio > 1.2 else 0.0)
                    demand_trend = 0.1 if resource.current_demand > resource.current_supply else -0.1
                    price_trend = 0.1 if resource.current_price > resource.base_price else -0.1
                    event_active = any(
                        e.resource_name == res_name and e.region == region_name
                        for e in self.economy.active_events
                        if e.is_active
                    )

                    prediction = self.ml_swarm.demand_predictor.predict(
                        supply_trend=supply_trend,
                        demand_trend=demand_trend,
                        price_trend=price_trend,
                        scarcity=scarcity,
                        event_active=event_active,
                    )

                    rn = region_name.lower().replace(" ", "_")
                    res_n = res_name.lower().replace(" ", "_")
                    self._world_flags[
                        f"ml_demand_{rn}_{res_n}"
                    ] = prediction["prediction"]

            summary["systems"]["ml_swarm"] = {"predictions_made": True}

        # Final flag publish
        self._publish_flags()

        # Timing
        tick_ms = (time.time() - tick_start) * 1000
        summary["tick_ms"] = round(tick_ms, 2)
        summary["total_flags"] = len(self._world_flags)

        # History
        self.tick_history.append(summary)
        if len(self.tick_history) > self._max_history:
            self.tick_history = self.tick_history[-self._max_history:]

        return summary

    def _publish_flags(self) -> None:
        """Push all world flags to the WorldStateReactor singleton."""
        for flag_name, flag_value in self._world_flags.items():
            WorldStateReactor.set_flag(
                flag_name, flag_value, set_by="world_simulator"
            )

    def _apply_weather_to_economy(self) -> None:
        """Use weather flags to modify economy behavior."""
        if not self.economy or not self.weather:
            return

        for region_name in self.economy.regions:
            rn = region_name.lower().replace(" ", "_")

            # Bad weather reduces production
            affects_harvest = self._world_flags.get(
                f"weather_{rn}_affects_harvest", False
            )
            if affects_harvest:
                region = self.economy.regions[region_name]
                for resource in region.resources.values():
                    if resource.category.value == "food":
                        resource.production_rate *= 0.95  # 5% reduction per tick

            # Bad weather disrupts trade
            affects_travel = self._world_flags.get(
                f"weather_{rn}_affects_travel", False
            )
            if affects_travel:
                for route in self.economy.trade_routes:
                    if route.source == region_name or route.destination == region_name:
                        route.cost_multiplier = min(3.0, route.cost_multiplier * 1.05)
            else:
                # Gradually restore trade costs
                for route in self.economy.trade_routes:
                    if route.source == region_name or route.destination == region_name:
                        route.cost_multiplier = max(1.0, route.cost_multiplier * 0.98)

    # ------------------------------------------------------------------
    # External API
    # ------------------------------------------------------------------

    def get_world_state(self) -> Dict[str, Any]:
        """Get full world state snapshot."""
        state: Dict[str, Any] = {
            "tick": self.tick_count,
            "day": self.current_day,
            "hour": self.current_hour,
            "flags": dict(self._world_flags),
        }

        if self.economy:
            state["economy"] = self.economy.to_dict()
        if self.weather:
            state["weather"] = self.weather.to_dict()
        if self.scheduler:
            state["scheduling"] = self.scheduler.to_dict()
        if self.quest_gen:
            state["quests"] = self.quest_gen.to_dict()

        return state

    def get_flags(self) -> Dict[str, Any]:
        """Get all current world state flags."""
        return dict(self._world_flags)

    def set_flag(self, name: str, value: Any) -> None:
        """Manually set a world flag (game director control)."""
        self._world_flags[name] = value
        WorldStateReactor.set_flag(name, value, set_by="manual")

    def get_region_summary(self, region_name: str) -> Dict[str, Any]:
        """Get a comprehensive summary for a specific region."""
        summary: Dict[str, Any] = {"region": region_name}

        if self.weather:
            weather = self.weather.get_weather(region_name)
            if weather:
                summary["weather"] = weather

        if self.economy:
            econ = self.economy.get_economic_summary(region_name)
            if econ:
                summary["economy"] = econ

        if self.scheduler:
            npcs_here = self.scheduler.get_npcs_at_location(region_name)
            summary["npcs_present"] = npcs_here

        if self.quest_gen:
            quests = self.quest_gen.get_available_quests(region=region_name)
            summary["available_quests"] = len(quests)

        return summary

    def save(self, path: str) -> None:
        """Save full world state to JSON."""
        state = self.get_world_state()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(state, f, indent=2, default=str)

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    @classmethod
    def create_fantasy_world(
        cls,
        seed: int = 42,
        with_economy: bool = True,
        with_weather: bool = True,
        with_scheduling: bool = True,
        with_quests: bool = True,
        with_ml: bool = True,
    ) -> "WorldSimulator":
        """
        Create a pre-configured fantasy world with all systems.
        Good for testing and as a starting template.
        """
        economy = None
        weather = None
        scheduler = None
        quest_gen = None
        ml_swarm = None

        if with_economy and EconomyEngine:
            economy = EconomyEngine.create_fantasy_economy(seed=seed)

        if with_weather and WeatherEngine:
            weather = WeatherEngine.create_fantasy_weather(seed=seed)

        if with_scheduling and SchedulerManager:
            scheduler = SchedulerManager.create_village(
                npc_ids=["garen", "haven", "lexis", "synth"]
            )

        if with_quests and QuestGenerator:
            quest_gen = QuestGenerator()

        if with_ml and MLSwarmManager:
            ml_swarm = MLSwarmManager()
            ml_swarm.train_all()

        return cls(
            economy=economy,
            weather=weather,
            scheduler=scheduler,
            quest_gen=quest_gen,
            ml_swarm=ml_swarm,
            seed=seed,
        )
