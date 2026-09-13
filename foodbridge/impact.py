"""Impact accounting — turns every rescue into three provable numbers.

Conversion factors are standard, published figures so the impact claims are honest and
reproducible rather than invented:

* Meals:  Feeding America uses ~1.2 lbs of food == 1 meal.
* CO2:    EPA / WRI figures put avoided emissions from diverting food waste from landfill
          at roughly ~2.5 lbs CO2-equivalent per lb of food (methane avoidance + embodied
          emissions). We use a deliberately conservative factor.
* Money:  the donor-stated fair value of the food kept out of the dumpster.
"""

from __future__ import annotations

from dataclasses import dataclass

LBS_PER_MEAL = 1.2
CO2_LBS_PER_LB_FOOD = 2.5  # conservative CO2e avoided per lb of food rescued


@dataclass
class Impact:
    meals: int = 0
    money_usd: float = 0.0
    co2_lbs: float = 0.0
    lbs: float = 0.0

    def add(self, weight_lbs: float, value_usd: float) -> "Impact":
        self.lbs += weight_lbs
        self.meals += int(round(weight_lbs / LBS_PER_MEAL))
        self.money_usd += value_usd
        self.co2_lbs += weight_lbs * CO2_LBS_PER_LB_FOOD
        return self

    def scoreboard(self) -> str:
        return (
            f"{self.meals} meals delivered  |  "
            f"${self.money_usd:,.0f} saved  |  "
            f"{self.co2_lbs:,.0f} lbs CO2 prevented"
        )
