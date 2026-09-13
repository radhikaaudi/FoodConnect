"""Donor receipts + liability reassurance.

Attacks the #1 real reason businesses don't donate surplus food: fear of liability and no
incentive. FoodBridge reassures the donor they are protected under the federal Bill Emerson
Good Samaritan Food Donation Act (good-faith donations) and issues a tax-deduction receipt —
turning a one-off giver into a repeat donor and *growing* the supply of rescuable food.
"""

from __future__ import annotations

from .models import Donation

GOOD_SAMARITAN_NOTE = (
    "Under the federal Bill Emerson Good Samaritan Food Donation Act, donors acting in good "
    "faith are protected from civil and criminal liability for donated food."
)


def generate_donor_receipt(d: Donation, recipient_name: str, minute: int) -> str:
    return (
        "\n    ----------------- FoodBridge Donation Receipt -----------------\n"
        f"    Donor:        {d.donor_name}\n"
        f"    Donation ID:  {d.id}\n"
        f"    Item:         {d.item}\n"
        f"    Weight:       {d.weight_lbs:.0f} lbs\n"
        f"    Fair value:   ${d.value_usd:,.2f}  (tax-deductible)\n"
        f"    Delivered to: {recipient_name}\n"
        f"    Time (min):   {minute}\n"
        f"    Protection:   {GOOD_SAMARITAN_NOTE}\n"
        "    ---------------------------------------------------------------\n"
    )
