"""
Synthesus 2.0 — World Systems: Procedural Weather Generation (Phase 11E)
"Weather is a mechanic, not just a shader"

A procedural weather system that:
1. Simulates weather patterns per region based on biome + season
2. Transitions smoothly between conditions (Markov chain)
3. Generates extreme events (storms, droughts, blizzards)
4. Integrates with narrative tension (bad weather during dramatic moments)
5. Affects economy (harvest, trade routes, spoilage)
6. Affects NPCs (shelter, mood, activity changes)
7. Publishes world state flags for all other systems

Design principles:
- Deterministic given seed (reproducible worlds)
- Biome-aware: desert weather ≠ forest weather ≠ mountain weather
- Season-aware: 4 seasons affect weather probability distributions
- Narrative hooks: game director can request "dramatic weather" for tension
- Lightweight: ~0.2ms per tick per region, zero GPU
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


# ──────────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────────

class WeatherCondition(str, Enum):
    """Core weather states."""
    CLEAR = "clear"
    PARTLY_CLOUDY = "partly_cloudy"
    CLOUDY = "cloudy"
    OVERCAST = "overcast"
    LIGHT_RAIN = "light_rain"
    HEAVY_RAIN = "heavy_rain"
    THUNDERSTORM = "thunderstorm"
    LIGHT_SNOW = "light_snow"
    HEAVY_SNOW = "heavy_snow"
    BLIZZARD = "blizzard"
    FOG = "fog"
    HAIL = "hail"
    SANDSTORM = "sandstorm"
    DROUGHT = "drought"
    HEAT_WAVE = "heat_wave"
    WIND = "wind"
    TORNADO = "tornado"


class Biome(str, Enum):
    """Region biome types."""
    TEMPERATE = "temperate"
    DESERT = "desert"
    ARCTIC = "arctic"
    TROPICAL = "tropical"
    MOUNTAIN = "mountain"
    COASTAL = "coastal"
    FOREST = "forest"
    SWAMP = "swamp"


class Season(str, Enum):
    """Game seasons."""
    SPRING = "spring"
    SUMMER = "summer"
    AUTUMN = "autumn"
    WINTER = "winter"

    @classmethod
    def from_day(cls, day: int) -> "Season":
        """Get season from day-of-year (1-360, 90 days per season)."""
        d = day % 360
        if d < 90:
            return cls.SPRING
        elif d < 180:
            return cls.SUMMER
        elif d < 270:
            return cls.AUTUMN
        else:
            return cls.WINTER


@dataclass
class WeatherState:
    """Current weather in a region."""
    condition: WeatherCondition = WeatherCondition.CLEAR
    temperature: float = 20.0        # Celsius
    humidity: float = 0.5            # 0-1
    wind_speed: float = 5.0          # km/h
    visibility: float = 1.0          # 0-1 (1 = perfect)
    precipitation: float = 0.0      # 0-1 intensity
    danger_level: float = 0.0       # 0-1 (how dangerous)
    duration_ticks: int = 10         # How many ticks this condition lasts
    ticks_remaining: int = 10

    @property
    def is_dangerous(self) -> bool:
        return self.danger_level > 0.5

    @property
    def affects_travel(self) -> bool:
        return self.visibility < 0.5 or self.danger_level > 0.3

    @property
    def affects_harvest(self) -> bool:
        return self.condition in (
            WeatherCondition.HEAVY_RAIN, WeatherCondition.THUNDERSTORM,
            WeatherCondition.HAIL, WeatherCondition.DROUGHT,
            WeatherCondition.HEAT_WAVE, WeatherCondition.HEAVY_SNOW,
            WeatherCondition.BLIZZARD, WeatherCondition.TORNADO,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "condition": self.condition.value,
            "temperature": round(self.temperature, 1),
            "humidity": round(self.humidity, 2),
            "wind_speed": round(self.wind_speed, 1),
            "visibility": round(self.visibility, 2),
            "precipitation": round(self.precipitation, 2),
            "danger_level": round(self.danger_level, 2),
            "is_dangerous": self.is_dangerous,
            "affects_travel": self.affects_travel,
            "affects_harvest": self.affects_harvest,
            "ticks_remaining": self.ticks_remaining,
        }


# ──────────────────────────────────────────────────
# Transition Matrices (Markov Chains)
# ──────────────────────────────────────────────────

def _temperate_transitions() -> Dict[WeatherCondition, Dict[WeatherCondition, float]]:
    """Transition probabilities for temperate biome."""
    return {
        WeatherCondition.CLEAR: {
            WeatherCondition.CLEAR: 0.50,
            WeatherCondition.PARTLY_CLOUDY: 0.30,
            WeatherCondition.FOG: 0.05,
            WeatherCondition.WIND: 0.10,
            WeatherCondition.CLOUDY: 0.05,
        },
        WeatherCondition.PARTLY_CLOUDY: {
            WeatherCondition.CLEAR: 0.25,
            WeatherCondition.PARTLY_CLOUDY: 0.30,
            WeatherCondition.CLOUDY: 0.25,
            WeatherCondition.LIGHT_RAIN: 0.10,
            WeatherCondition.WIND: 0.10,
        },
        WeatherCondition.CLOUDY: {
            WeatherCondition.PARTLY_CLOUDY: 0.15,
            WeatherCondition.CLOUDY: 0.25,
            WeatherCondition.OVERCAST: 0.25,
            WeatherCondition.LIGHT_RAIN: 0.20,
            WeatherCondition.FOG: 0.10,
            WeatherCondition.WIND: 0.05,
        },
        WeatherCondition.OVERCAST: {
            WeatherCondition.CLOUDY: 0.20,
            WeatherCondition.OVERCAST: 0.20,
            WeatherCondition.LIGHT_RAIN: 0.30,
            WeatherCondition.HEAVY_RAIN: 0.15,
            WeatherCondition.FOG: 0.10,
            WeatherCondition.THUNDERSTORM: 0.05,
        },
        WeatherCondition.LIGHT_RAIN: {
            WeatherCondition.CLOUDY: 0.20,
            WeatherCondition.LIGHT_RAIN: 0.30,
            WeatherCondition.HEAVY_RAIN: 0.20,
            WeatherCondition.OVERCAST: 0.15,
            WeatherCondition.PARTLY_CLOUDY: 0.10,
            WeatherCondition.THUNDERSTORM: 0.05,
        },
        WeatherCondition.HEAVY_RAIN: {
            WeatherCondition.LIGHT_RAIN: 0.30,
            WeatherCondition.HEAVY_RAIN: 0.20,
            WeatherCondition.THUNDERSTORM: 0.20,
            WeatherCondition.OVERCAST: 0.15,
            WeatherCondition.CLOUDY: 0.10,
            WeatherCondition.HAIL: 0.05,
        },
        WeatherCondition.THUNDERSTORM: {
            WeatherCondition.HEAVY_RAIN: 0.35,
            WeatherCondition.THUNDERSTORM: 0.15,
            WeatherCondition.LIGHT_RAIN: 0.20,
            WeatherCondition.OVERCAST: 0.15,
            WeatherCondition.CLOUDY: 0.10,
            WeatherCondition.TORNADO: 0.02,
            WeatherCondition.HAIL: 0.03,
        },
        WeatherCondition.FOG: {
            WeatherCondition.CLEAR: 0.20,
            WeatherCondition.PARTLY_CLOUDY: 0.30,
            WeatherCondition.FOG: 0.25,
            WeatherCondition.CLOUDY: 0.15,
            WeatherCondition.LIGHT_RAIN: 0.10,
        },
        WeatherCondition.WIND: {
            WeatherCondition.CLEAR: 0.25,
            WeatherCondition.PARTLY_CLOUDY: 0.25,
            WeatherCondition.WIND: 0.20,
            WeatherCondition.CLOUDY: 0.20,
            WeatherCondition.LIGHT_RAIN: 0.10,
        },
        WeatherCondition.HAIL: {
            WeatherCondition.HEAVY_RAIN: 0.40,
            WeatherCondition.THUNDERSTORM: 0.20,
            WeatherCondition.OVERCAST: 0.25,
            WeatherCondition.LIGHT_RAIN: 0.15,
        },
        WeatherCondition.TORNADO: {
            WeatherCondition.HEAVY_RAIN: 0.40,
            WeatherCondition.THUNDERSTORM: 0.30,
            WeatherCondition.OVERCAST: 0.20,
            WeatherCondition.CLEAR: 0.10,
        },
    }


def _desert_transitions() -> Dict[WeatherCondition, Dict[WeatherCondition, float]]:
    """Transition probabilities for desert biome."""
    return {
        WeatherCondition.CLEAR: {
            WeatherCondition.CLEAR: 0.60,
            WeatherCondition.HEAT_WAVE: 0.15,
            WeatherCondition.WIND: 0.10,
            WeatherCondition.PARTLY_CLOUDY: 0.10,
            WeatherCondition.SANDSTORM: 0.05,
        },
        WeatherCondition.HEAT_WAVE: {
            WeatherCondition.CLEAR: 0.30,
            WeatherCondition.HEAT_WAVE: 0.40,
            WeatherCondition.DROUGHT: 0.15,
            WeatherCondition.WIND: 0.10,
            WeatherCondition.SANDSTORM: 0.05,
        },
        WeatherCondition.DROUGHT: {
            WeatherCondition.CLEAR: 0.20,
            WeatherCondition.HEAT_WAVE: 0.30,
            WeatherCondition.DROUGHT: 0.40,
            WeatherCondition.WIND: 0.10,
        },
        WeatherCondition.SANDSTORM: {
            WeatherCondition.CLEAR: 0.20,
            WeatherCondition.WIND: 0.30,
            WeatherCondition.SANDSTORM: 0.25,
            WeatherCondition.PARTLY_CLOUDY: 0.15,
            WeatherCondition.HEAT_WAVE: 0.10,
        },
        WeatherCondition.WIND: {
            WeatherCondition.CLEAR: 0.30,
            WeatherCondition.WIND: 0.25,
            WeatherCondition.SANDSTORM: 0.20,
            WeatherCondition.HEAT_WAVE: 0.15,
            WeatherCondition.PARTLY_CLOUDY: 0.10,
        },
        WeatherCondition.PARTLY_CLOUDY: {
            WeatherCondition.CLEAR: 0.40,
            WeatherCondition.PARTLY_CLOUDY: 0.30,
            WeatherCondition.LIGHT_RAIN: 0.10,
            WeatherCondition.WIND: 0.15,
            WeatherCondition.HEAT_WAVE: 0.05,
        },
        WeatherCondition.LIGHT_RAIN: {
            WeatherCondition.CLEAR: 0.40,
            WeatherCondition.PARTLY_CLOUDY: 0.35,
            WeatherCondition.LIGHT_RAIN: 0.15,
            WeatherCondition.HEAVY_RAIN: 0.05,
            WeatherCondition.WIND: 0.05,
        },
    }


def _arctic_transitions() -> Dict[WeatherCondition, Dict[WeatherCondition, float]]:
    """Transition probabilities for arctic biome."""
    return {
        WeatherCondition.CLEAR: {
            WeatherCondition.CLEAR: 0.30,
            WeatherCondition.PARTLY_CLOUDY: 0.20,
            WeatherCondition.WIND: 0.20,
            WeatherCondition.LIGHT_SNOW: 0.15,
            WeatherCondition.FOG: 0.10,
            WeatherCondition.CLOUDY: 0.05,
        },
        WeatherCondition.LIGHT_SNOW: {
            WeatherCondition.LIGHT_SNOW: 0.30,
            WeatherCondition.HEAVY_SNOW: 0.25,
            WeatherCondition.CLOUDY: 0.15,
            WeatherCondition.CLEAR: 0.10,
            WeatherCondition.WIND: 0.10,
            WeatherCondition.BLIZZARD: 0.10,
        },
        WeatherCondition.HEAVY_SNOW: {
            WeatherCondition.LIGHT_SNOW: 0.25,
            WeatherCondition.HEAVY_SNOW: 0.25,
            WeatherCondition.BLIZZARD: 0.20,
            WeatherCondition.OVERCAST: 0.15,
            WeatherCondition.WIND: 0.10,
            WeatherCondition.CLOUDY: 0.05,
        },
        WeatherCondition.BLIZZARD: {
            WeatherCondition.HEAVY_SNOW: 0.35,
            WeatherCondition.BLIZZARD: 0.20,
            WeatherCondition.LIGHT_SNOW: 0.20,
            WeatherCondition.OVERCAST: 0.15,
            WeatherCondition.WIND: 0.10,
        },
        WeatherCondition.WIND: {
            WeatherCondition.CLEAR: 0.15,
            WeatherCondition.WIND: 0.25,
            WeatherCondition.LIGHT_SNOW: 0.25,
            WeatherCondition.BLIZZARD: 0.15,
            WeatherCondition.PARTLY_CLOUDY: 0.10,
            WeatherCondition.HEAVY_SNOW: 0.10,
        },
        WeatherCondition.FOG: {
            WeatherCondition.CLEAR: 0.20,
            WeatherCondition.FOG: 0.25,
            WeatherCondition.LIGHT_SNOW: 0.20,
            WeatherCondition.CLOUDY: 0.20,
            WeatherCondition.PARTLY_CLOUDY: 0.15,
        },
        WeatherCondition.PARTLY_CLOUDY: {
            WeatherCondition.CLEAR: 0.25,
            WeatherCondition.CLOUDY: 0.25,
            WeatherCondition.LIGHT_SNOW: 0.20,
            WeatherCondition.WIND: 0.15,
            WeatherCondition.PARTLY_CLOUDY: 0.15,
        },
        WeatherCondition.CLOUDY: {
            WeatherCondition.OVERCAST: 0.25,
            WeatherCondition.LIGHT_SNOW: 0.25,
            WeatherCondition.PARTLY_CLOUDY: 0.20,
            WeatherCondition.CLOUDY: 0.15,
            WeatherCondition.FOG: 0.10,
            WeatherCondition.WIND: 0.05,
        },
        WeatherCondition.OVERCAST: {
            WeatherCondition.CLOUDY: 0.20,
            WeatherCondition.LIGHT_SNOW: 0.25,
            WeatherCondition.HEAVY_SNOW: 0.20,
            WeatherCondition.OVERCAST: 0.20,
            WeatherCondition.WIND: 0.10,
            WeatherCondition.FOG: 0.05,
        },
    }


# Map biome → transition table
_BIOME_TRANSITIONS = {
    Biome.TEMPERATE: _temperate_transitions,
    Biome.FOREST: _temperate_transitions,     # Forest ≈ temperate
    Biome.COASTAL: _temperate_transitions,    # Coastal ≈ temperate + more rain
    Biome.SWAMP: _temperate_transitions,      # Swamp ≈ temperate + more fog
    Biome.DESERT: _desert_transitions,
    Biome.ARCTIC: _arctic_transitions,
    Biome.MOUNTAIN: _arctic_transitions,      # Mountain ≈ arctic
    Biome.TROPICAL: _temperate_transitions,   # Tropical ≈ temperate + more rain
}


# ──────────────────────────────────────────────────
# Weather Properties (per condition)
# ──────────────────────────────────────────────────

_WEATHER_PROPERTIES: Dict[WeatherCondition, Dict[str, Any]] = {
    WeatherCondition.CLEAR: {
        "humidity": 0.3, "wind": 5, "visibility": 1.0,
        "precip": 0.0, "danger": 0.0, "temp_mod": 0,
        "duration_range": (8, 20),
    },
    WeatherCondition.PARTLY_CLOUDY: {
        "humidity": 0.4, "wind": 8, "visibility": 0.9,
        "precip": 0.0, "danger": 0.0, "temp_mod": -1,
        "duration_range": (6, 15),
    },
    WeatherCondition.CLOUDY: {
        "humidity": 0.5, "wind": 10, "visibility": 0.8,
        "precip": 0.0, "danger": 0.0, "temp_mod": -2,
        "duration_range": (5, 12),
    },
    WeatherCondition.OVERCAST: {
        "humidity": 0.6, "wind": 12, "visibility": 0.7,
        "precip": 0.05, "danger": 0.0, "temp_mod": -3,
        "duration_range": (4, 10),
    },
    WeatherCondition.LIGHT_RAIN: {
        "humidity": 0.7, "wind": 15, "visibility": 0.6,
        "precip": 0.3, "danger": 0.1, "temp_mod": -4,
        "duration_range": (3, 8),
    },
    WeatherCondition.HEAVY_RAIN: {
        "humidity": 0.9, "wind": 25, "visibility": 0.3,
        "precip": 0.7, "danger": 0.3, "temp_mod": -5,
        "duration_range": (2, 6),
    },
    WeatherCondition.THUNDERSTORM: {
        "humidity": 0.95, "wind": 40, "visibility": 0.2,
        "precip": 0.85, "danger": 0.6, "temp_mod": -6,
        "duration_range": (1, 4),
    },
    WeatherCondition.LIGHT_SNOW: {
        "humidity": 0.6, "wind": 12, "visibility": 0.6,
        "precip": 0.3, "danger": 0.15, "temp_mod": -10,
        "duration_range": (3, 8),
    },
    WeatherCondition.HEAVY_SNOW: {
        "humidity": 0.7, "wind": 20, "visibility": 0.3,
        "precip": 0.6, "danger": 0.4, "temp_mod": -15,
        "duration_range": (2, 6),
    },
    WeatherCondition.BLIZZARD: {
        "humidity": 0.8, "wind": 60, "visibility": 0.05,
        "precip": 0.9, "danger": 0.8, "temp_mod": -20,
        "duration_range": (1, 4),
    },
    WeatherCondition.FOG: {
        "humidity": 0.85, "wind": 3, "visibility": 0.15,
        "precip": 0.0, "danger": 0.2, "temp_mod": -2,
        "duration_range": (3, 10),
    },
    WeatherCondition.HAIL: {
        "humidity": 0.8, "wind": 30, "visibility": 0.4,
        "precip": 0.5, "danger": 0.5, "temp_mod": -5,
        "duration_range": (1, 3),
    },
    WeatherCondition.SANDSTORM: {
        "humidity": 0.1, "wind": 50, "visibility": 0.05,
        "precip": 0.0, "danger": 0.7, "temp_mod": 5,
        "duration_range": (2, 6),
    },
    WeatherCondition.DROUGHT: {
        "humidity": 0.1, "wind": 5, "visibility": 0.9,
        "precip": 0.0, "danger": 0.3, "temp_mod": 8,
        "duration_range": (15, 40),
    },
    WeatherCondition.HEAT_WAVE: {
        "humidity": 0.2, "wind": 5, "visibility": 0.85,
        "precip": 0.0, "danger": 0.4, "temp_mod": 12,
        "duration_range": (5, 15),
    },
    WeatherCondition.WIND: {
        "humidity": 0.3, "wind": 35, "visibility": 0.7,
        "precip": 0.0, "danger": 0.15, "temp_mod": -2,
        "duration_range": (3, 8),
    },
    WeatherCondition.TORNADO: {
        "humidity": 0.85, "wind": 100, "visibility": 0.1,
        "precip": 0.6, "danger": 1.0, "temp_mod": -3,
        "duration_range": (1, 2),
    },
}

# Base temperatures by biome and season
_BASE_TEMPS: Dict[Biome, Dict[Season, float]] = {
    Biome.TEMPERATE: {Season.SPRING: 15, Season.SUMMER: 25, Season.AUTUMN: 12, Season.WINTER: 2},
    Biome.DESERT: {Season.SPRING: 30, Season.SUMMER: 42, Season.AUTUMN: 28, Season.WINTER: 18},
    Biome.ARCTIC: {Season.SPRING: -5, Season.SUMMER: 5, Season.AUTUMN: -8, Season.WINTER: -25},
    Biome.TROPICAL: {Season.SPRING: 28, Season.SUMMER: 32, Season.AUTUMN: 27, Season.WINTER: 25},
    Biome.MOUNTAIN: {Season.SPRING: 5, Season.SUMMER: 15, Season.AUTUMN: 3, Season.WINTER: -10},
    Biome.COASTAL: {Season.SPRING: 14, Season.SUMMER: 22, Season.AUTUMN: 15, Season.WINTER: 8},
    Biome.FOREST: {Season.SPRING: 13, Season.SUMMER: 22, Season.AUTUMN: 10, Season.WINTER: 0},
    Biome.SWAMP: {Season.SPRING: 18, Season.SUMMER: 28, Season.AUTUMN: 16, Season.WINTER: 8},
}


# ──────────────────────────────────────────────────
# Region Weather Controller
# ──────────────────────────────────────────────────

@dataclass
class RegionWeather:
    """Tracks weather for a single region."""
    region: str
    biome: Biome
    current: WeatherState = field(default_factory=WeatherState)
    history: List[WeatherCondition] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region": self.region,
            "biome": self.biome.value,
            "current": self.current.to_dict(),
            "recent_history": [c.value for c in self.history[-10:]],
        }


# ──────────────────────────────────────────────────
# Weather Engine
# ──────────────────────────────────────────────────

class WeatherEngine:
    """
    Procedural weather simulation across all regions.

    Tick-based: call tick() each game cycle to advance weather.
    Weather transitions follow biome-specific Markov chains.
    Narrative tension can bias toward dramatic conditions.
    """

    def __init__(self, seed: int = 42):
        self._rng = random.Random(seed)
        self.regions: Dict[str, RegionWeather] = {}
        self.current_day: int = 0
        self.tick_count: int = 0
        self.narrative_tension: float = 0.0  # 0-1, game director can set this

    def add_region(self, name: str, biome: Biome) -> None:
        """Register a region with its biome."""
        self.regions[name] = RegionWeather(
            region=name,
            biome=biome,
            current=self._create_initial_weather(biome),
        )

    def _create_initial_weather(self, biome: Biome) -> WeatherState:
        """Create starting weather based on biome."""
        season = Season.from_day(self.current_day)
        base_temp = _BASE_TEMPS.get(biome, _BASE_TEMPS[Biome.TEMPERATE])[season]
        return WeatherState(
            condition=WeatherCondition.CLEAR,
            temperature=base_temp,
            humidity=0.4,
            wind_speed=8.0,
            visibility=1.0,
            precipitation=0.0,
            danger_level=0.0,
            duration_ticks=10,
            ticks_remaining=10,
        )

    # ------------------------------------------------------------------
    # Core Simulation
    # ------------------------------------------------------------------

    def tick(self, day: Optional[int] = None) -> Dict[str, Any]:
        """
        Advance weather by one tick.

        Args:
            day: Current game day (for season calculation). If None, auto-increments.

        Returns:
            Summary with per-region weather and world state flags.
        """
        self.tick_count += 1
        if day is not None:
            self.current_day = day

        season = Season.from_day(self.current_day)
        transitions = []
        flags: Dict[str, Any] = {}

        for region_name, region in self.regions.items():
            # Decrement current weather timer
            region.current.ticks_remaining -= 1

            # Transition if weather expired
            if region.current.ticks_remaining <= 0:
                old_condition = region.current.condition
                new_condition = self._pick_next_condition(
                    region.biome, region.current.condition, season
                )
                region.current = self._create_weather_state(
                    new_condition, region.biome, season
                )
                region.history.append(new_condition)
                if len(region.history) > 100:
                    region.history = region.history[-100:]

                transitions.append({
                    "region": region_name,
                    "from": old_condition.value,
                    "to": new_condition.value,
                })

            # Compute flags for this region
            rn = region_name.lower().replace(" ", "_")
            flags[f"weather_{rn}_condition"] = region.current.condition.value
            flags[f"weather_{rn}_temperature"] = round(region.current.temperature, 1)
            flags[f"weather_{rn}_danger"] = region.current.is_dangerous
            flags[f"weather_{rn}_severity"] = round(region.current.danger_level, 2)
            flags[f"weather_{rn}_visibility"] = round(region.current.visibility, 2)
            flags[f"weather_{rn}_affects_travel"] = region.current.affects_travel
            flags[f"weather_{rn}_affects_harvest"] = region.current.affects_harvest

        return {
            "tick": self.tick_count,
            "day": self.current_day,
            "season": season.value,
            "transitions": transitions,
            "flags": flags,
            "regions": {
                name: r.current.to_dict() for name, r in self.regions.items()
            },
        }

    def _pick_next_condition(
        self,
        biome: Biome,
        current: WeatherCondition,
        season: Season,
    ) -> WeatherCondition:
        """
        Pick the next weather condition using the Markov chain,
        biased by season and narrative tension.
        """
        # Get transition table
        get_transitions = _BIOME_TRANSITIONS.get(biome, _temperate_transitions)
        transitions = get_transitions()

        probs = transitions.get(current)
        if not probs:
            # Fallback: go to clear
            return WeatherCondition.CLEAR

        conditions = list(probs.keys())
        weights = list(probs.values())

        # Season bias
        weights = self._apply_season_bias(conditions, weights, biome, season)

        # Narrative tension bias: increase probability of dramatic weather
        if self.narrative_tension > 0.3:
            weights = self._apply_tension_bias(conditions, weights)

        # Normalize
        total = sum(weights)
        if total <= 0:
            return WeatherCondition.CLEAR
        weights = [w / total for w in weights]

        # Weighted random pick
        roll = self._rng.random()
        cumulative = 0.0
        for cond, weight in zip(conditions, weights):
            cumulative += weight
            if roll <= cumulative:
                return cond

        return conditions[-1]

    def _apply_season_bias(
        self,
        conditions: List[WeatherCondition],
        weights: List[float],
        biome: Biome,
        season: Season,
    ) -> List[float]:
        """Bias transitions based on season."""
        biased = list(weights)
        for i, cond in enumerate(conditions):
            # Winter: more snow/cold
            if season == Season.WINTER:
                if cond in (WeatherCondition.LIGHT_SNOW, WeatherCondition.HEAVY_SNOW,
                            WeatherCondition.BLIZZARD):
                    biased[i] *= 2.0
                elif cond in (WeatherCondition.CLEAR, WeatherCondition.HEAT_WAVE):
                    biased[i] *= 0.5

            # Summer: more heat, less snow
            elif season == Season.SUMMER:
                if cond in (WeatherCondition.HEAT_WAVE, WeatherCondition.DROUGHT):
                    biased[i] *= 2.0
                elif cond in (WeatherCondition.LIGHT_SNOW, WeatherCondition.HEAVY_SNOW,
                              WeatherCondition.BLIZZARD):
                    biased[i] *= 0.1

            # Spring: more rain
            elif season == Season.SPRING:
                if cond in (WeatherCondition.LIGHT_RAIN, WeatherCondition.HEAVY_RAIN):
                    biased[i] *= 1.5

            # Autumn: more fog and wind
            elif season == Season.AUTUMN:
                if cond in (WeatherCondition.FOG, WeatherCondition.WIND):
                    biased[i] *= 1.5

        return biased

    def _apply_tension_bias(
        self,
        conditions: List[WeatherCondition],
        weights: List[float],
    ) -> List[float]:
        """Bias toward dramatic weather when narrative tension is high."""
        dramatic = {
            WeatherCondition.THUNDERSTORM, WeatherCondition.HEAVY_RAIN,
            WeatherCondition.BLIZZARD, WeatherCondition.HEAVY_SNOW,
            WeatherCondition.TORNADO, WeatherCondition.SANDSTORM,
            WeatherCondition.HAIL,
        }
        biased = list(weights)
        tension = self.narrative_tension
        for i, cond in enumerate(conditions):
            if cond in dramatic:
                biased[i] *= (1.0 + tension * 2.0)
            elif cond in (WeatherCondition.CLEAR, WeatherCondition.PARTLY_CLOUDY):
                biased[i] *= max(0.2, 1.0 - tension)
        return biased

    def _create_weather_state(
        self,
        condition: WeatherCondition,
        biome: Biome,
        season: Season,
    ) -> WeatherState:
        """Create a weather state with appropriate properties."""
        props = _WEATHER_PROPERTIES.get(condition, _WEATHER_PROPERTIES[WeatherCondition.CLEAR])
        base_temp = _BASE_TEMPS.get(biome, _BASE_TEMPS[Biome.TEMPERATE])[season]
        temp_mod = props["temp_mod"]

        # Add some randomness
        temp_jitter = self._rng.uniform(-2.0, 2.0)
        wind_jitter = self._rng.uniform(-3.0, 3.0)
        dur_min, dur_max = props["duration_range"]
        duration = self._rng.randint(dur_min, dur_max)

        return WeatherState(
            condition=condition,
            temperature=base_temp + temp_mod + temp_jitter,
            humidity=props["humidity"] + self._rng.uniform(-0.05, 0.05),
            wind_speed=max(0, props["wind"] + wind_jitter),
            visibility=max(0.01, min(1.0, props["visibility"] + self._rng.uniform(-0.05, 0.05))),
            precipitation=props["precip"],
            danger_level=props["danger"],
            duration_ticks=duration,
            ticks_remaining=duration,
        )

    # ------------------------------------------------------------------
    # External API
    # ------------------------------------------------------------------

    def set_narrative_tension(self, tension: float) -> None:
        """Set narrative tension (0-1) to bias weather toward drama."""
        self.narrative_tension = max(0.0, min(1.0, tension))

    def force_weather(
        self, region_name: str, condition: WeatherCondition, duration: int = 10
    ) -> Optional[Dict[str, Any]]:
        """Force a specific weather condition in a region (game director override)."""
        region = self.regions.get(region_name)
        if not region:
            return None

        season = Season.from_day(self.current_day)
        region.current = self._create_weather_state(condition, region.biome, season)
        region.current.duration_ticks = duration
        region.current.ticks_remaining = duration
        region.history.append(condition)

        return region.current.to_dict()

    def get_weather(self, region_name: str) -> Optional[Dict[str, Any]]:
        """Get current weather for a region."""
        region = self.regions.get(region_name)
        return region.to_dict() if region else None

    def get_all_weather(self) -> Dict[str, Dict[str, Any]]:
        """Get weather for all regions."""
        return {name: r.to_dict() for name, r in self.regions.items()}

    def get_forecast(self, region_name: str, ticks_ahead: int = 5) -> List[str]:
        """
        Simple forecast: predict likely conditions for next N ticks.
        Uses the Markov chain to project forward.
        """
        region = self.regions.get(region_name)
        if not region:
            return []

        season = Season.from_day(self.current_day)
        forecast = []
        current = region.current.condition

        for _ in range(ticks_ahead):
            next_cond = self._pick_next_condition(
                region.biome, current, season
            )
            forecast.append(next_cond.value)
            current = next_cond

        return forecast

    def to_dict(self) -> Dict[str, Any]:
        """Serialize full weather state."""
        return {
            "tick_count": self.tick_count,
            "current_day": self.current_day,
            "season": Season.from_day(self.current_day).value,
            "narrative_tension": self.narrative_tension,
            "regions": {name: r.to_dict() for name, r in self.regions.items()},
        }

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    @classmethod
    def create_fantasy_weather(cls, seed: int = 42) -> "WeatherEngine":
        """Create pre-configured weather for a fantasy world."""
        engine = cls(seed=seed)
        engine.add_region("riverside", Biome.TEMPERATE)
        engine.add_region("ironhold", Biome.MOUNTAIN)
        engine.add_region("silverpeak", Biome.FOREST)
        return engine
