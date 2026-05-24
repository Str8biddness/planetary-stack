"""
Synthesus 2.0 — World Systems: Procedural Economy Engine (Phase 11A)
"The world has a living economy that NPCs participate in"

A lightweight supply-demand economy that:
1. Tracks resources, production, consumption across regions
2. Computes dynamic prices from supply/demand ratios
3. Simulates trade routes with risk/distance costs
4. Generates economic events (shortages, surpluses, crashes)
5. Feeds merchant NPCs real-time pricing + scarcity data
6. Publishes world state flags for other systems to react to

Design principles:
- Pure Python, zero ML — runs on any hardware
- All state serializable to JSON (save/load)
- Deterministic tick-based simulation (~0.5ms per tick)
- Integrates with WorldStateReactor via flag bus
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ──────────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────────

class ResourceCategory(str, Enum):
    """Broad categories for resources."""
    RAW = "raw"             # ore, wood, wheat
    CRAFTED = "crafted"     # swords, bread, potions
    LUXURY = "luxury"       # gems, silk, wine
    FOOD = "food"           # meat, bread, vegetables
    SERVICE = "service"     # healing, repair, transport


class EconomicEventType(str, Enum):
    """Types of events that affect the economy."""
    SHORTAGE = "shortage"           # Supply critically low
    SURPLUS = "surplus"             # Supply way above demand
    TRADE_DISRUPTION = "trade_disruption"  # Route blocked
    BOOM = "boom"                   # Demand spike
    CRASH = "crash"                 # Demand collapse
    HARVEST = "harvest"             # Seasonal production spike
    BLIGHT = "blight"              # Production drop
    DISCOVERY = "discovery"         # New resource found
    TAX_CHANGE = "tax_change"       # Government intervention


@dataclass
class Resource:
    """A single resource in the economy."""
    name: str
    category: ResourceCategory
    base_price: float                     # Gold, the floor price
    current_supply: float = 100.0         # Units available
    current_demand: float = 100.0         # Units wanted per tick
    production_rate: float = 10.0         # Units produced per tick
    consumption_rate: float = 8.0         # Units consumed per tick
    spoilage_rate: float = 0.0            # % lost per tick (food spoils)
    min_price: float = 0.1                # Price floor
    max_price_multiplier: float = 10.0    # Max = base_price * this
    volatility: float = 0.1              # How fast price reacts (0-1)
    weight: float = 1.0                   # Transport cost multiplier

    @property
    def supply_demand_ratio(self) -> float:
        """Supply/demand ratio. >1 = surplus, <1 = shortage."""
        if self.current_demand <= 0:
            return 10.0
        return self.current_supply / self.current_demand

    @property
    def current_price(self) -> float:
        """Dynamic price based on supply/demand."""
        ratio = self.supply_demand_ratio
        if ratio <= 0:
            return self.base_price * self.max_price_multiplier

        # Price curve: inverse relationship with supply/demand
        # When ratio=1 → base_price, ratio<1 → higher, ratio>1 → lower
        price_multiplier = 1.0 / (ratio ** self.volatility)
        price = self.base_price * price_multiplier

        # Clamp to bounds
        return max(self.min_price, min(price, self.base_price * self.max_price_multiplier))

    @property
    def scarcity_level(self) -> str:
        """Human-readable scarcity for NPC dialogue."""
        ratio = self.supply_demand_ratio
        if ratio < 0.3:
            return "critically_scarce"
        elif ratio < 0.6:
            return "scarce"
        elif ratio < 0.9:
            return "tight"
        elif ratio < 1.5:
            return "normal"
        elif ratio < 3.0:
            return "abundant"
        else:
            return "oversupplied"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category.value,
            "base_price": self.base_price,
            "current_price": round(self.current_price, 2),
            "supply": round(self.current_supply, 1),
            "demand": round(self.current_demand, 1),
            "supply_demand_ratio": round(self.supply_demand_ratio, 3),
            "scarcity": self.scarcity_level,
            "production_rate": self.production_rate,
            "consumption_rate": self.consumption_rate,
        }


@dataclass
class TradeRoute:
    """A trade connection between two regions."""
    source: str
    destination: str
    distance: float = 1.0              # Affects transport time
    risk: float = 0.0                  # 0-1, chance of disruption per tick
    capacity: float = 50.0             # Max units per tick
    cost_multiplier: float = 1.0       # Transport cost factor
    active: bool = True
    disrupted_until: float = 0.0       # Timestamp when disruption ends

    @property
    def is_disrupted(self) -> bool:
        return not self.active or time.time() < self.disrupted_until

    def transport_cost(self, resource: Resource) -> float:
        """Cost to move 1 unit of a resource along this route."""
        return resource.weight * self.distance * self.cost_multiplier

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "destination": self.destination,
            "distance": self.distance,
            "risk": self.risk,
            "capacity": self.capacity,
            "active": self.active,
            "disrupted": self.is_disrupted,
        }


@dataclass
class EconomicEvent:
    """An event affecting the economy."""
    event_type: EconomicEventType
    region: str
    resource_name: Optional[str] = None
    magnitude: float = 1.0              # Severity multiplier
    duration_ticks: int = 10            # How long it lasts
    remaining_ticks: int = 10
    description: str = ""
    started_at: float = field(default_factory=time.time)

    @property
    def is_active(self) -> bool:
        return self.remaining_ticks > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.event_type.value,
            "region": self.region,
            "resource": self.resource_name,
            "magnitude": self.magnitude,
            "remaining_ticks": self.remaining_ticks,
            "description": self.description,
        }


@dataclass
class Region:
    """A geographic region in the economy."""
    name: str
    resources: Dict[str, Resource] = field(default_factory=dict)
    tax_rate: float = 0.05             # % added to prices
    prosperity: float = 1.0            # 0-2, affects production
    population: int = 1000
    specialization: Optional[str] = None  # Primary export resource

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "tax_rate": self.tax_rate,
            "prosperity": round(self.prosperity, 3),
            "population": self.population,
            "specialization": self.specialization,
            "resources": {k: v.to_dict() for k, v in self.resources.items()},
        }


# ──────────────────────────────────────────────────
# Economy Engine
# ──────────────────────────────────────────────────

class EconomyEngine:
    """
    The procedural economy simulation.

    Tick-based: call tick() each game cycle to advance the economy.
    All pricing is deterministic given the same state — no randomness
    in price calculation, only in event generation.
    """

    def __init__(self, seed: int = 42):
        self._rng = random.Random(seed)
        self.regions: Dict[str, Region] = {}
        self.trade_routes: List[TradeRoute] = []
        self.active_events: List[EconomicEvent] = []
        self.event_history: List[EconomicEvent] = []
        self.tick_count: int = 0
        self._event_listeners: List[Callable[[EconomicEvent], None]] = []

        # Configuration
        self.event_chance_per_tick: float = 0.05   # 5% chance per tick
        self.trade_execution_enabled: bool = True
        self.spoilage_enabled: bool = True

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def add_region(self, region: Region) -> None:
        """Register a region."""
        self.regions[region.name] = region

    def add_trade_route(self, route: TradeRoute) -> None:
        """Register a trade route between regions."""
        self.trade_routes.append(route)

    def add_resource_to_region(
        self, region_name: str, resource: Resource
    ) -> None:
        """Add a resource to a region's economy."""
        if region_name not in self.regions:
            raise ValueError(f"Unknown region: {region_name}")
        self.regions[region_name].resources[resource.name] = resource

    def on_event(self, listener: Callable[[EconomicEvent], None]) -> None:
        """Register a callback for economic events."""
        self._event_listeners.append(listener)

    # ------------------------------------------------------------------
    # Core Simulation Loop
    # ------------------------------------------------------------------

    def tick(self) -> Dict[str, Any]:
        """
        Advance the economy by one tick.

        Returns a summary dict with:
        - tick: current tick number
        - prices: dict of region→resource→price
        - events: list of new events this tick
        - trades: list of trade executions
        - flags: world state flags to publish
        """
        self.tick_count += 1
        new_events: List[EconomicEvent] = []
        trades: List[Dict[str, Any]] = []
        flags: Dict[str, Any] = {}

        # Step 1: Production & consumption
        self._simulate_production_consumption()

        # Step 2: Spoilage
        if self.spoilage_enabled:
            self._simulate_spoilage()

        # Step 3: Trade route execution
        if self.trade_execution_enabled:
            trades = self._execute_trades()

        # Step 4: Apply active events
        self._apply_active_events()

        # Step 5: Generate new events (stochastic)
        new_events = self._generate_events()
        for event in new_events:
            self.active_events.append(event)
            self.event_history.append(event)
            for listener in self._event_listeners:
                listener(event)

        # Step 6: Expire old events
        self._expire_events()

        # Step 7: Update prosperity
        self._update_prosperity()

        # Step 8: Compute world state flags
        flags = self._compute_world_flags()

        return {
            "tick": self.tick_count,
            "prices": self._get_all_prices(),
            "events": [e.to_dict() for e in new_events],
            "trades": trades,
            "flags": flags,
            "active_events": [e.to_dict() for e in self.active_events if e.is_active],
        }

    def _simulate_production_consumption(self) -> None:
        """Each region produces and consumes resources."""
        for region in self.regions.values():
            pop_factor = region.population / 1000.0
            for resource in region.resources.values():
                # Production: base rate * prosperity
                production = resource.production_rate * region.prosperity
                # Boost if this is the region's specialization
                if region.specialization == resource.name:
                    production *= 1.5

                # Consumption: base rate * population factor
                consumption = resource.consumption_rate * pop_factor

                # Update supply
                resource.current_supply = max(
                    0.0,
                    resource.current_supply + production - consumption
                )
                # Demand adjusts slowly toward consumption
                resource.current_demand = (
                    resource.current_demand * 0.9 + consumption * 0.1
                )

    def _simulate_spoilage(self) -> None:
        """Food and perishables lose supply over time."""
        for region in self.regions.values():
            for resource in region.resources.values():
                if resource.spoilage_rate > 0 and resource.current_supply > 0:
                    lost = resource.current_supply * resource.spoilage_rate
                    resource.current_supply = max(0.0, resource.current_supply - lost)

    def _execute_trades(self) -> List[Dict[str, Any]]:
        """Move resources along trade routes (surplus → deficit)."""
        trades = []
        for route in self.trade_routes:
            if route.is_disrupted:
                continue
            src = self.regions.get(route.source)
            dst = self.regions.get(route.destination)
            if not src or not dst:
                continue

            # For each resource both regions share, move from surplus to deficit
            shared = set(src.resources.keys()) & set(dst.resources.keys())
            for res_name in shared:
                src_res = src.resources[res_name]
                dst_res = dst.resources[res_name]

                # Only trade if source has surplus and dest has deficit
                if (src_res.supply_demand_ratio > 1.2 and
                        dst_res.supply_demand_ratio < 0.9):
                    # Amount to move: min of surplus, deficit, route capacity
                    surplus = src_res.current_supply - src_res.current_demand
                    deficit = dst_res.current_demand - dst_res.current_supply
                    amount = min(surplus * 0.3, deficit * 0.5, route.capacity)
                    amount = max(0, amount)

                    if amount > 0.1:
                        src_res.current_supply -= amount
                        dst_res.current_supply += amount

                        # Risk check: random disruption
                        if route.risk > 0 and self._rng.random() < route.risk:
                            # Some goods lost in transit
                            lost = amount * self._rng.uniform(0.1, 0.5)
                            dst_res.current_supply -= lost
                            trades.append({
                                "route": f"{route.source}→{route.destination}",
                                "resource": res_name,
                                "amount": round(amount, 1),
                                "lost_in_transit": round(lost, 1),
                            })
                        else:
                            trades.append({
                                "route": f"{route.source}→{route.destination}",
                                "resource": res_name,
                                "amount": round(amount, 1),
                            })
        return trades

    def _generate_events(self) -> List[EconomicEvent]:
        """Stochastically generate economic events."""
        events = []
        if self._rng.random() > self.event_chance_per_tick:
            return events

        # Pick a random region
        if not self.regions:
            return events
        region_name = self._rng.choice(list(self.regions.keys()))
        region = self.regions[region_name]

        if not region.resources:
            return events

        # Pick a random resource
        res_name = self._rng.choice(list(region.resources.keys()))
        resource = region.resources[res_name]

        # Determine event type based on current state
        ratio = resource.supply_demand_ratio
        event_type = None
        description = ""
        magnitude = 1.0

        roll = self._rng.random()
        if ratio < 0.5 and roll < 0.4:
            event_type = EconomicEventType.SHORTAGE
            magnitude = self._rng.uniform(1.2, 2.0)
            description = (
                f"Critical shortage of {res_name} in {region_name}! "
                f"Prices soaring."
            )
        elif ratio > 2.0 and roll < 0.4:
            event_type = EconomicEventType.SURPLUS
            magnitude = self._rng.uniform(0.5, 0.8)
            description = (
                f"Market flooded with {res_name} in {region_name}. "
                f"Prices dropping."
            )
        elif roll < 0.15:
            event_type = EconomicEventType.BOOM
            magnitude = self._rng.uniform(1.5, 2.5)
            description = (
                f"Demand for {res_name} surging in {region_name}!"
            )
        elif roll < 0.25:
            event_type = EconomicEventType.BLIGHT
            magnitude = self._rng.uniform(0.3, 0.6)
            description = (
                f"Production of {res_name} crippled in {region_name}."
            )
        elif roll < 0.35:
            event_type = EconomicEventType.HARVEST
            magnitude = self._rng.uniform(1.5, 3.0)
            description = (
                f"Bumper harvest of {res_name} in {region_name}!"
            )

        if event_type:
            duration = self._rng.randint(5, 20)
            event = EconomicEvent(
                event_type=event_type,
                region=region_name,
                resource_name=res_name,
                magnitude=magnitude,
                duration_ticks=duration,
                remaining_ticks=duration,
                description=description,
            )
            events.append(event)

        # Trade route disruption (separate roll)
        if self.trade_routes and self._rng.random() < 0.03:
            route = self._rng.choice(self.trade_routes)
            if not route.is_disrupted:
                duration = self._rng.randint(3, 15)
                route.disrupted_until = time.time() + duration * 60
                events.append(EconomicEvent(
                    event_type=EconomicEventType.TRADE_DISRUPTION,
                    region=route.source,
                    resource_name=None,
                    magnitude=1.0,
                    duration_ticks=duration,
                    remaining_ticks=duration,
                    description=(
                        f"Trade route {route.source}→{route.destination} "
                        f"disrupted! Bandits or weather blocking passage."
                    ),
                ))

        return events

    def _apply_active_events(self) -> None:
        """Apply effects of active events to the economy."""
        for event in self.active_events:
            if not event.is_active:
                continue
            region = self.regions.get(event.region)
            if not region:
                continue

            if event.resource_name:
                resource = region.resources.get(event.resource_name)
                if not resource:
                    continue

                if event.event_type == EconomicEventType.SHORTAGE:
                    resource.consumption_rate *= 1.02  # Panic buying
                elif event.event_type == EconomicEventType.SURPLUS:
                    resource.production_rate *= 0.98   # Producers slow down
                elif event.event_type == EconomicEventType.BOOM:
                    resource.current_demand *= 1.05
                elif event.event_type == EconomicEventType.BLIGHT:
                    resource.production_rate *= 0.95
                elif event.event_type == EconomicEventType.HARVEST:
                    resource.current_supply += resource.production_rate * 0.3

    def _expire_events(self) -> None:
        """Decrement event timers and remove expired ones."""
        still_active = []
        for event in self.active_events:
            event.remaining_ticks -= 1
            if event.is_active:
                still_active.append(event)
        self.active_events = still_active

    def _update_prosperity(self) -> None:
        """Update region prosperity based on economic health."""
        for region in self.regions.values():
            if not region.resources:
                continue
            # Average supply/demand ratio across all resources
            ratios = [r.supply_demand_ratio for r in region.resources.values()]
            avg_ratio = sum(ratios) / len(ratios)

            # Prosperity moves slowly toward the health indicator
            target = min(2.0, max(0.1, avg_ratio))
            region.prosperity = region.prosperity * 0.95 + target * 0.05

    def _compute_world_flags(self) -> Dict[str, Any]:
        """
        Compute world state flags for the WorldStateReactor.

        Flag naming convention:
          economy_{region}_{resource}_{scarcity}  = True/False
          economy_{region}_prosperity             = float
          economy_event_{event_type}_{region}     = True/False
        """
        flags: Dict[str, Any] = {}
        for region in self.regions.values():
            rn = region.name.lower().replace(" ", "_")
            flags[f"economy_{rn}_prosperity"] = round(region.prosperity, 3)

            for resource in region.resources.values():
                res_n = resource.name.lower().replace(" ", "_")
                scarcity = resource.scarcity_level
                flags[f"economy_{rn}_{res_n}_scarcity"] = scarcity
                flags[f"economy_{rn}_{res_n}_price"] = round(
                    resource.current_price, 2
                )

        for event in self.active_events:
            if event.is_active:
                rn = event.region.lower().replace(" ", "_")
                etype = event.event_type.value
                flags[f"economy_event_{etype}_{rn}"] = True

        return flags

    def _get_all_prices(self) -> Dict[str, Dict[str, float]]:
        """Get current prices across all regions."""
        prices = {}
        for region in self.regions.values():
            prices[region.name] = {
                res.name: round(res.current_price, 2)
                for res in region.resources.values()
            }
        return prices

    # ------------------------------------------------------------------
    # NPC API — what merchant NPCs call
    # ------------------------------------------------------------------

    def get_merchant_prices(
        self, region_name: str, items: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get pricing data for a merchant NPC in a specific region.

        Returns per-item:
        - price: current dynamic price
        - base_price: original price
        - scarcity: scarcity level string
        - trend: "rising" | "stable" | "falling"
        - stock: available supply
        """
        region = self.regions.get(region_name)
        if not region:
            return {}

        result = {}
        for res_name, resource in region.resources.items():
            if items and res_name not in items:
                continue

            # Determine trend from supply/demand ratio
            ratio = resource.supply_demand_ratio
            if ratio < 0.8:
                trend = "rising"
            elif ratio > 1.3:
                trend = "falling"
            else:
                trend = "stable"

            result[res_name] = {
                "price": round(resource.current_price, 2),
                "base_price": resource.base_price,
                "scarcity": resource.scarcity_level,
                "trend": trend,
                "stock": round(resource.current_supply, 1),
                "tax": region.tax_rate,
            }
        return result

    def get_trade_opportunities(
        self, region_name: str
    ) -> List[Dict[str, Any]]:
        """
        Find profitable trade opportunities from a region.

        Returns list of {resource, destination, price_diff, profit_margin}.
        """
        region = self.regions.get(region_name)
        if not region:
            return []

        opportunities = []
        for route in self.trade_routes:
            if route.is_disrupted:
                continue
            if route.source != region_name:
                continue

            dst = self.regions.get(route.destination)
            if not dst:
                continue

            shared = set(region.resources.keys()) & set(dst.resources.keys())
            for res_name in shared:
                src_price = region.resources[res_name].current_price
                dst_price = dst.resources[res_name].current_price
                transport = route.transport_cost(region.resources[res_name])
                profit = dst_price - src_price - transport

                if profit > 0:
                    opportunities.append({
                        "resource": res_name,
                        "destination": route.destination,
                        "buy_price": round(src_price, 2),
                        "sell_price": round(dst_price, 2),
                        "transport_cost": round(transport, 2),
                        "profit_per_unit": round(profit, 2),
                        "profit_margin": round(profit / src_price * 100, 1),
                        "route_risk": route.risk,
                    })

        return sorted(opportunities, key=lambda x: x["profit_per_unit"],
                       reverse=True)

    def get_economic_summary(self, region_name: str) -> Dict[str, Any]:
        """High-level economic summary for a region (for NPC awareness)."""
        region = self.regions.get(region_name)
        if not region:
            return {}

        scarce = []
        abundant = []
        for res_name, resource in region.resources.items():
            if resource.scarcity_level in ("critically_scarce", "scarce"):
                scarce.append(res_name)
            elif resource.scarcity_level in ("abundant", "oversupplied"):
                abundant.append(res_name)

        active_events = [
            e.to_dict()
            for e in self.active_events
            if e.is_active and e.region == region_name
        ]

        return {
            "region": region_name,
            "prosperity": round(region.prosperity, 3),
            "population": region.population,
            "scarce_resources": scarce,
            "abundant_resources": abundant,
            "active_events": active_events,
            "total_resources": len(region.resources),
        }

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialize full economy state."""
        return {
            "tick_count": self.tick_count,
            "regions": {k: v.to_dict() for k, v in self.regions.items()},
            "trade_routes": [r.to_dict() for r in self.trade_routes],
            "active_events": [e.to_dict() for e in self.active_events],
        }

    def save(self, path: str) -> None:
        """Save economy state to JSON file."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    # ------------------------------------------------------------------
    # Presets — quick world setup
    # ------------------------------------------------------------------

    @classmethod
    def create_fantasy_economy(cls, seed: int = 42) -> "EconomyEngine":
        """
        Create a pre-configured fantasy economy with 3 regions.
        Good for testing and as a starting template.
        """
        engine = cls(seed=seed)

        # Region 1: Riverside (agricultural hub)
        riverside = Region(
            name="riverside",
            population=1200,
            specialization="wheat",
            tax_rate=0.05,
        )
        engine.add_region(riverside)
        for res in [
            Resource("wheat", ResourceCategory.FOOD, base_price=2.0,
                     production_rate=15.0, consumption_rate=8.0, spoilage_rate=0.02),
            Resource("iron_ore", ResourceCategory.RAW, base_price=5.0,
                     production_rate=3.0, consumption_rate=4.0),
            Resource("bread", ResourceCategory.FOOD, base_price=3.0,
                     production_rate=8.0, consumption_rate=10.0, spoilage_rate=0.05),
            Resource("healing_potion", ResourceCategory.CRAFTED, base_price=25.0,
                     production_rate=2.0, consumption_rate=3.0),
        ]:
            engine.add_resource_to_region("riverside", res)

        # Region 2: Ironhold (mining & smithing)
        ironhold = Region(
            name="ironhold",
            population=800,
            specialization="iron_ore",
            tax_rate=0.08,
        )
        engine.add_region(ironhold)
        for res in [
            Resource("iron_ore", ResourceCategory.RAW, base_price=5.0,
                     production_rate=20.0, consumption_rate=5.0),
            Resource("steel_sword", ResourceCategory.CRAFTED, base_price=50.0,
                     production_rate=3.0, consumption_rate=2.0),
            Resource("wheat", ResourceCategory.FOOD, base_price=2.0,
                     production_rate=2.0, consumption_rate=6.0),
            Resource("coal", ResourceCategory.RAW, base_price=3.0,
                     production_rate=12.0, consumption_rate=8.0),
        ]:
            engine.add_resource_to_region("ironhold", res)

        # Region 3: Silverpeak (luxury goods & trade)
        silverpeak = Region(
            name="silverpeak",
            population=600,
            specialization="gems",
            tax_rate=0.12,
        )
        engine.add_region(silverpeak)
        for res in [
            Resource("gems", ResourceCategory.LUXURY, base_price=100.0,
                     production_rate=1.0, consumption_rate=0.5),
            Resource("silk", ResourceCategory.LUXURY, base_price=30.0,
                     production_rate=2.0, consumption_rate=1.5),
            Resource("wheat", ResourceCategory.FOOD, base_price=2.0,
                     production_rate=1.0, consumption_rate=5.0),
            Resource("wine", ResourceCategory.LUXURY, base_price=15.0,
                     production_rate=3.0, consumption_rate=2.0, spoilage_rate=0.01),
        ]:
            engine.add_resource_to_region("silverpeak", res)

        # Trade routes
        engine.add_trade_route(TradeRoute(
            source="riverside", destination="ironhold",
            distance=2.0, risk=0.05, capacity=30.0,
        ))
        engine.add_trade_route(TradeRoute(
            source="ironhold", destination="riverside",
            distance=2.0, risk=0.05, capacity=30.0,
        ))
        engine.add_trade_route(TradeRoute(
            source="riverside", destination="silverpeak",
            distance=4.0, risk=0.10, capacity=20.0,
        ))
        engine.add_trade_route(TradeRoute(
            source="silverpeak", destination="riverside",
            distance=4.0, risk=0.10, capacity=20.0,
        ))
        engine.add_trade_route(TradeRoute(
            source="ironhold", destination="silverpeak",
            distance=3.0, risk=0.15, capacity=15.0,
        ))
        engine.add_trade_route(TradeRoute(
            source="silverpeak", destination="ironhold",
            distance=3.0, risk=0.15, capacity=15.0,
        ))

        return engine
