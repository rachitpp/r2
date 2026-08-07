#!/usr/bin/env python3
"""Deterministic POS seed generator.

Writes one CSV per table, which `make seed` then COPYs into Postgres. Running
this twice with the same arguments produces byte-identical files.

The determinism rules, all of which this file obeys and any change to it must
keep obeying:

  1. One seed constant, MASTER_SEED = 42. Independent substreams are derived
     from it by hashing a stream name, so adding a product does not shift every
     other product's history, and no stream can perturb another. Never
     `random.*` at module level, never `hash()` (Python salts string hashes per
     process).
  2. No wall clock. DATA_END_DATE is a constant here and is deliberately NOT
     read from the environment — a configurable anchor would make the output
     depend on the machine. The application's AS_OF_DATE env var must match it.
  3. No uuid4. Every id is an integer assigned in iteration order and written
     into the CSV.
  4. Row order is iteration order. Nothing is sorted after the fact, which also
     keeps peak memory flat: the large tables stream straight to disk.
  5. No iteration over a set. Dicts preserve insertion order and are fine.
  6. Money is Decimal, quantised ROUND_HALF_UP. No float reaches a CSV.
  7. csv.writer with an explicit "\\n" terminator, UTF-8, no BOM.

Cross-platform byte identity is NOT claimed from bare Python: libm differences
can flip a Poisson draw, and the tzdata version affects timestamps. The claim
is scoped to generation inside the digest-pinned python:3.12-slim image, which
is how `make seed-generate` and CI both run it. See ADR-0006 for why a scoped
claim that is actually asserted beats a broad one that isn't.

Usage:
    python seed.py --size small
    python seed.py --size full --out /tmp/x --verify
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from random import Random
from zoneinfo import ZoneInfo

GENERATOR_VERSION = "1.0.0"
MASTER_SEED = 42

# The last trading day in the generated data. Constant, never from env: see
# rule 2 above. AS_OF_DATE in .env must match this.
DATA_END_DATE = date(2026, 6, 30)

REPO_ROOT = Path(__file__).resolve().parents[2]


# ─────────────────────────────────────────────────────────────────────────────
# LOCALE — India. Currency INR, timezone Asia/Kolkata.
#
# Phase 0's seed and Phase 2's corpus share a world: currency, festival
# calendar, store locations and SKU conventions all come from the same place
# the real invoices come from.
#
# The chain is modelled as a Maharashtra grocery retailer — Pune, Nashik,
# Nagpur — which is what makes the regional weighting below coherent: Ganesh
# Chaturthi is a far larger retail event in Maharashtra than nationally, and a
# chain spread across four states would not show that shape.
#
# Festival dates are verified. The two that carry the most weight — Dhanteras
# 2025-10-18 and Diwali 2025-10-20 — were checked directly. Moon-sighting dates
# (the two Eids) are inherently plus or minus a day and that does not move a
# demand curve, so they are not flagged.
#
# GST is NOT in this block. It changed on 22 September 2025, inside the window,
# so it is temporal data and lives in the gst_rates table — see GST_SLABS below
# and migrations/002_gst_rates.sql.
#
# To change any of it: edit this block, `make seed-generate` at both sizes,
# commit the regenerated seed/small/ and seed/CHECKSUMS.txt.
# ─────────────────────────────────────────────────────────────────────────────

CURRENCY = "INR"
TIMEZONE = "Asia/Kolkata"

STORE_DEFS = [
    # code, name, city, demand factor, opened
    ("ST-01", "Kothrud", "Pune", 1.00, date(2019, 3, 11)),
    ("ST-02", "Gangapur Road", "Nashik", 0.72, date(2021, 9, 6)),
    ("ST-03", "Dharampeth", "Nagpur", 1.35, date(2017, 6, 19)),
]


@dataclass(frozen=True)
class Festival:
    """A festival and the shape of trade around it.

    A single-day multiplier cannot express an Indian festive season. Diwali is
    not a spike — it is a build that starts three to four weeks out, steepens
    through Dhanteras, peaks the day before Lakshmi Puja, and drops into a
    slump afterwards. The yearly sinusoid in CategoryDef cannot produce it
    either: a sinusoid is symmetric and slow, and this shape is asymmetric and
    sharp. So festivals are their own factor, applied on top of seasonality.
    """

    name: str
    peak: date
    ramp_days: int  # how many days ahead demand starts building
    ramp_peak: float  # multiplier on the day before the peak
    ramp_shape: float  # >1 keeps the early ramp flat and steepens it late
    day_factor: float  # multiplier on the festival day itself
    tail_days: int  # length of the post-festival slump
    tail_factor: float  # multiplier at the start of that slump


# Only festivals falling inside 2025-01-01 .. 2026-06-30 are listed. Diwali
# 2026 (8 November) is past DATA_END_DATE, so `full` contains exactly one
# Diwali and `small` (which starts 2026-01-02) contains none — worth knowing
# before writing an eval question about it.
FESTIVALS = [
    # ── 2025 ────────────────────────────────────────────────────────────────
    Festival("Makar Sankranti", date(2025, 1, 14), 6, 1.30, 2.0, 1.05, 2, 0.88),
    Festival("Republic Day", date(2025, 1, 26), 3, 1.12, 1.5, 0.92, 1, 0.95),
    Festival("Maha Shivaratri", date(2025, 2, 26), 4, 1.18, 2.0, 0.85, 1, 0.94),
    Festival("Holi", date(2025, 3, 14), 9, 1.62, 2.2, 0.55, 2, 0.80),
    Festival("Gudi Padwa", date(2025, 3, 30), 7, 1.45, 2.0, 0.95, 2, 0.88),
    Festival("Eid al-Fitr", date(2025, 3, 31), 12, 1.55, 2.2, 0.75, 2, 0.85),
    Festival("Ram Navami", date(2025, 4, 6), 4, 1.16, 2.0, 0.90, 1, 0.94),
    Festival("Akshaya Tritiya", date(2025, 4, 30), 5, 1.28, 2.0, 1.10, 1, 0.92),
    Festival("Eid al-Adha", date(2025, 6, 7), 8, 1.38, 2.0, 0.80, 2, 0.87),
    Festival("Raksha Bandhan", date(2025, 8, 9), 8, 1.42, 2.1, 1.05, 2, 0.86),
    Festival("Independence Day", date(2025, 8, 15), 3, 1.14, 1.5, 0.95, 1, 0.95),
    Festival("Janmashtami", date(2025, 8, 16), 5, 1.26, 2.0, 0.92, 1, 0.92),
    # Ganesh Chaturthi runs eleven days in Maharashtra and is the largest
    # retail event of the year here after Diwali.
    Festival("Ganesh Chaturthi", date(2025, 8, 27), 14, 1.95, 2.3, 1.35, 11, 0.90),
    Festival("Navratri", date(2025, 9, 22), 8, 1.40, 2.0, 1.15, 9, 1.08),
    Festival("Dussehra", date(2025, 10, 2), 6, 1.55, 2.0, 1.10, 2, 0.90),
    # Diwali. Dhanteras (18 Oct) is the buying peak for anything durable or
    # gifted; Lakshmi Puja (20 Oct) is the festival itself. The ramp starts 26
    # days out, which overlaps Navratri and Dussehra — that overlap IS the
    # six-week festive season, and it is deliberate.
    Festival("Dhanteras", date(2025, 10, 18), 26, 2.75, 2.6, 2.40, 1, 1.60),
    Festival("Diwali", date(2025, 10, 20), 2, 2.20, 1.6, 1.45, 12, 0.72),
    Festival("Bhai Dooj", date(2025, 10, 23), 2, 1.30, 1.5, 1.10, 2, 0.85),
    Festival("Guru Nanak Jayanti", date(2025, 11, 5), 4, 1.18, 2.0, 0.90, 1, 0.94),
    Festival("Christmas", date(2025, 12, 25), 8, 1.45, 2.2, 0.85, 2, 0.88),
    # ── 2026 ────────────────────────────────────────────────────────────────
    Festival("New Year", date(2026, 1, 1), 4, 1.32, 1.8, 0.70, 2, 0.86),
    Festival("Makar Sankranti", date(2026, 1, 14), 6, 1.30, 2.0, 1.05, 2, 0.88),
    Festival("Republic Day", date(2026, 1, 26), 3, 1.12, 1.5, 0.92, 1, 0.95),
    Festival("Maha Shivaratri", date(2026, 2, 15), 4, 1.18, 2.0, 0.85, 1, 0.94),
    Festival("Holi", date(2026, 3, 4), 9, 1.62, 2.2, 0.55, 2, 0.80),
    Festival("Gudi Padwa", date(2026, 3, 19), 7, 1.45, 2.0, 0.95, 2, 0.88),
    Festival("Eid al-Fitr", date(2026, 3, 20), 12, 1.55, 2.2, 0.75, 2, 0.85),
    Festival("Ram Navami", date(2026, 3, 26), 4, 1.16, 2.0, 0.90, 1, 0.94),
    Festival("Akshaya Tritiya", date(2026, 4, 19), 5, 1.28, 2.0, 1.10, 1, 0.92),
    Festival("Eid al-Adha", date(2026, 5, 27), 8, 1.38, 2.0, 0.80, 2, 0.87),
]

# Ganesh Chaturthi and Gudi Padwa are weighted by store because they are
# regional events, not national ones. Pune is the Maharashtra stronghold.
# Any festival not listed applies equally at every store.
# The spread has to be wide enough to survive Poisson noise at a single store
# over a two-week window, or the effect is real in the generator and invisible
# in the data — which is worse than not modelling it, because a question about
# it then has an answer that contradicts its own premise. At 1.00/0.94/0.88 the
# Pune-to-Nagpur gap came out at roughly 2%, and Nashik out-indexed Pune on
# noise. Pune is the Ganeshotsav epicentre and Nagpur is Vidarbha, where it is
# a smaller event, so a wider spread is also the more accurate one.
REGIONAL_FESTIVAL_WEIGHT = {
    "Ganesh Chaturthi": {1: 1.00, 2: 0.88, 3: 0.72},
    "Gudi Padwa": {1: 1.00, 2: 0.92, 3: 0.82},
}

OPEN_HOUR, CLOSE_HOUR = 8, 22
# Relative footfall by hour, 08:00 to 21:00. Indian grocery skews to a strong
# evening peak after work rather than the UK lunchtime peak.
HOURLY_WEIGHTS = [4, 6, 7, 7, 8, 6, 5, 6, 9, 13, 14, 11, 7, 3]

TENDER_WEIGHTS = [("mobile", 52), ("cash", 27), ("card", 19), ("voucher", 2)]


# ─────────────────────────────────────────────────────────────────────────────
# Catalogue definition
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CategoryDef:
    """Demand shape for a category.

    Constructed with keyword arguments: there are enough fields that a
    positional call is unreadable, and adding one in the middle would silently
    shift every value after it.

    GST is deliberately NOT here. It is time-varying — see GST_SLABS.
    """

    name: str
    department: str
    amplitude: float  # seasonal swing, +/- around 1.0
    peak_doy: int  # day of year demand peaks
    weekend_uplift: float  # Sunday multiplier; Saturday derives from it
    promo_elasticity: float  # demand response to a discount
    margin: float  # gross margin on shelf price
    demand_weight: float  # how much of total store volume this pulls
    festive_lift: float  # sensitivity to the festival factor


def _cat(
    name, department, amplitude, peak_doy, weekend, elasticity, margin, weight, festive
) -> CategoryDef:
    return CategoryDef(
        name=name,
        department=department,
        amplitude=amplitude,
        peak_doy=peak_doy,
        weekend_uplift=weekend,
        promo_elasticity=elasticity,
        margin=margin,
        demand_weight=weight,
        festive_lift=festive,
    )


# Positional order: name, department, amplitude, peak_doy, weekend_uplift,
# promo_elasticity, margin, demand_weight, festive_lift.
CATEGORY_DEFS = [
    _cat("Fruits & Vegetables", "Fresh", 0.26, 150, 1.34, 1.10, 0.30, 2.40, 0.7),
    _cat("Atta, Rice & Dal", "Staples", 0.09, 300, 1.22, 0.70, 0.14, 3.10, 0.8),
    _cat("Dairy & Paneer", "Fresh", 0.13, 295, 1.26, 0.80, 0.22, 2.70, 0.9),
    _cat("Edible Oils & Ghee", "Staples", 0.24, 290, 1.20, 0.95, 0.18, 1.60, 1.5),
    _cat("Masalas & Spices", "Staples", 0.16, 298, 1.18, 0.75, 0.34, 1.30, 1.2),
    _cat("Snacks & Namkeen", "Packaged Foods", 0.21, 295, 1.40, 1.45, 0.36, 1.70, 1.4),
    _cat("Biscuits & Bakery", "Packaged Foods", 0.11, 320, 1.30, 1.20, 0.32, 1.55, 1.0),
    _cat("Ready to Cook", "Packaged Foods", 0.13, 200, 1.24, 1.05, 0.30, 0.85, 0.8),
    _cat("Tea & Coffee", "Beverages", 0.32, 15, 1.14, 1.10, 0.38, 1.10, 0.9),
    _cat("Soft Drinks & Juices", "Beverages", 0.52, 150, 1.38, 1.60, 0.34, 1.45, 0.9),
    _cat(
        "Sweets & Chocolates", "Packaged Foods", 0.34, 293, 1.42, 1.55, 0.40, 1.20, 2.4
    ),
    _cat("Home Care", "Household", 0.17, 290, 1.20, 0.95, 0.36, 0.75, 1.6),
    _cat("Detergents & Laundry", "Household", 0.11, 190, 1.18, 0.90, 0.32, 0.80, 0.9),
    _cat("Paper & Disposables", "Household", 0.08, 300, 1.20, 0.75, 0.30, 0.55, 0.8),
    _cat("Personal Care", "Health & Beauty", 0.11, 180, 1.16, 0.95, 0.42, 0.90, 1.1),
    _cat("Health & Wellness", "Health & Beauty", 0.26, 30, 1.10, 0.85, 0.44, 0.35, 0.6),
    _cat("Baby Care", "Health & Beauty", 0.07, 180, 1.22, 0.80, 0.30, 0.40, 0.7),
    # The festive category — diyas, rangoli, incense, gift boxes. Its seasonal
    # peak sits on Diwali and its festive_lift is the highest in the catalogue,
    # so the October ramp is unmistakable in the data.
    _cat(
        "Pooja & Festive", "General Merchandise", 0.62, 292, 1.30, 1.70, 0.48, 0.30, 3.2
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# GST — and the 22 September 2025 reform, which is INSIDE the data window
#
# The 56th GST Council meeting (3 September 2025) approved a restructuring
# effective 22 September 2025. The 12% and 28% slabs were removed: 12% items
# moved almost entirely to 5%, around 90% of 28% items moved to 18%, and
# luxury and sin goods — aerated beverages among them — moved to a new 40%
# slab. The resulting structure is 0 / 5 / 18 / 40.
#
# This is modelled temporally rather than as a flat correction, because the
# reform date falls inside the generated window. Rates live in the gst_rates
# table with the same [from, to) + exclusion-constraint machinery as
# supplier_terms, and the seed looks up the rate for the business_date of each
# sale — not the rate as it stands today.
#
# It also creates a genuine silent-wrong trap. "What was our average tax rate
# last year" spanning 22 September returns a blended figure that was true of no
# actual period, executes cleanly, and looks entirely plausible. That is
# ADR-0001's first threshold, found rather than invented.
# ─────────────────────────────────────────────────────────────────────────────

GST_REFORM_DATE = date(2025, 9, 22)

# category -> (rate before the reform, rate from the reform onward)
GST_SLABS = {
    "Fruits & Vegetables": (0, 0),
    "Atta, Rice & Dal": (5, 5),
    "Dairy & Paneer": (12, 5),
    "Edible Oils & Ghee": (5, 5),
    "Masalas & Spices": (5, 5),
    "Snacks & Namkeen": (12, 5),
    "Biscuits & Bakery": (18, 18),
    "Ready to Cook": (12, 5),
    "Tea & Coffee": (5, 5),
    "Soft Drinks & Juices": (28, 40),  # aerated beverages -> the new sin slab
    "Sweets & Chocolates": (5, 5),
    "Home Care": (18, 18),
    "Detergents & Laundry": (18, 18),
    "Paper & Disposables": (18, 18),
    "Personal Care": (12, 5),
    "Health & Wellness": (12, 5),
    "Baby Care": (12, 5),
    "Pooja & Festive": (12, 5),
}


# Typical shelf price in rupees for a mid-size pack in each category. Without
# these the log-normal is category-blind and produces ₹225 bananas next to a
# ₹78 five-litre oil jar — which loads cleanly, passes every constraint, and
# makes "highest-revenue category" answer noise.
CATEGORY_PRICE_MEDIAN = {
    "Fruits & Vegetables": 45,
    "Atta, Rice & Dal": 180,
    "Dairy & Paneer": 60,
    "Edible Oils & Ghee": 220,
    "Masalas & Spices": 85,
    "Snacks & Namkeen": 45,
    "Biscuits & Bakery": 40,
    "Ready to Cook": 75,
    "Tea & Coffee": 250,
    "Soft Drinks & Juices": 50,
    "Sweets & Chocolates": 180,
    "Home Care": 110,
    "Detergents & Laundry": 140,
    "Paper & Disposables": 90,
    "Personal Care": 130,
    "Health & Wellness": 150,
    "Baby Care": 280,
    "Pooja & Festive": 120,
}

# Pack size moves price. Matched as substrings against the product's variant,
# most specific first — "10 kg" must be tested before "1 kg".
VARIANT_PRICE_FACTOR = [
    ("10 kg", 3.20),
    ("5 kg", 2.40),
    ("5 L Jar", 2.80),
    ("2 kg", 1.70),
    ("1 kg", 1.30),
    ("1.25 L", 1.40),
    ("2 L", 1.80),
    ("1 L", 1.20),
    ("Gift Set", 2.20),
    ("Gift Box", 2.00),
    ("Party Pack", 1.60),
    ("Family Pack", 1.60),
    ("Value Pack", 1.50),
    ("Sharing Pack", 1.35),
    ("Multipack", 1.50),
    ("Pack of 12", 1.80),
    ("Pack of 6", 1.40),
    ("12 Pack", 1.80),
    ("6 Pack", 1.50),
    ("4 Pack", 1.35),
    ("2 Pack", 1.20),
    ("Twin Pack", 1.20),
    ("Combo Pack", 1.40),
    ("Combo", 1.40),
    ("Premium", 1.40),
    ("Large", 1.35),
    ("Medium", 1.00),
    ("Small", 0.75),
    ("Refill Pouch", 0.80),
    ("Refill", 0.80),
    ("Pouch", 0.85),
    ("Tub", 1.10),
    ("Loose", 0.70),
    ("Single", 0.60),
    ("Assorted", 1.25),
    ("100 g", 0.60),
    ("150 g", 0.70),
    ("200 g", 0.80),
    ("250 g", 0.85),
    ("400 g", 1.05),
    ("500 g", 1.00),
    ("250 ml", 0.70),
    ("500 ml", 0.90),
    ("600 ml", 0.95),
]


def variant_price_factor(variant: str) -> float:
    for token, factor in VARIANT_PRICE_FACTOR:
        if token in variant:
            return factor
    return 1.0


CATEGORY_CODES = {
    "Fruits & Vegetables": "FNV",
    "Atta, Rice & Dal": "STP",
    "Dairy & Paneer": "DRY",
    "Edible Oils & Ghee": "OIL",
    "Masalas & Spices": "MSL",
    "Snacks & Namkeen": "NMK",
    "Biscuits & Bakery": "BSK",
    "Ready to Cook": "RTC",
    "Tea & Coffee": "TEA",
    "Soft Drinks & Juices": "BEV",
    "Sweets & Chocolates": "SWT",
    "Home Care": "HMC",
    "Detergents & Laundry": "DET",
    "Paper & Disposables": "PPR",
    "Personal Care": "PSC",
    "Health & Wellness": "HLW",
    "Baby Care": "BBY",
    "Pooja & Festive": "POO",
}

# House-brand prefixes are invented. Real brand names do not belong in a
# synthetic dataset in a public repository.
NAME_PARTS = {
    "Fruits & Vegetables": (
        ["Sahyadri", "Krishi Bazaar", "Green Konkan", "Ratnagiri"],
        [
            "Bananas",
            "Tomatoes",
            "Onions",
            "Potatoes",
            "Okra",
            "Cauliflower",
            "Spinach",
            "Green Chillies",
            "Coriander",
            "Alphonso Mangoes",
            "Bottle Gourd",
            "Lemons",
        ],
        ["Loose", "500 g Pack", "1 kg Pack", "Grade A", "Farm Fresh"],
    ),
    "Atta, Rice & Dal": (
        ["Annapurna", "Suvarna", "Godavari", "Panchali"],
        [
            "Chakki Atta",
            "Basmati Rice",
            "Sona Masoori Rice",
            "Toor Dal",
            "Moong Dal",
            "Chana Dal",
            "Urad Dal",
            "Rajma",
            "Kabuli Chana",
            "Poha",
            "Rava",
            "Besan",
        ],
        ["1 kg", "5 kg", "10 kg", "Value Pack", "Premium"],
    ),
    "Dairy & Paneer": (
        ["Gokul", "Nandini Vale", "Chitale Wadi", "Amrit Dhara"],
        [
            "Toned Milk",
            "Full Cream Milk",
            "Paneer",
            "Dahi",
            "Butter",
            "Cheese Slices",
            "Shrikhand",
            "Lassi",
            "Buttermilk",
        ],
        ["Standard", "Family Pack", "Pouch", "Tub", "Twin Pack"],
    ),
    "Edible Oils & Ghee": (
        ["Suvarna", "Deccan Gold", "Tulsi", "Konkan Pure"],
        [
            "Sunflower Oil",
            "Groundnut Oil",
            "Mustard Oil",
            "Cow Ghee",
            "Rice Bran Oil",
            "Coconut Oil",
            "Vanaspati",
        ],
        ["1 L", "5 L Jar", "500 ml", "1 kg Tin", "Refill Pouch"],
    ),
    "Masalas & Spices": (
        ["Rasoi Rani", "Swad Sagar", "Malvani", "Kesari"],
        [
            "Turmeric Powder",
            "Red Chilli Powder",
            "Garam Masala",
            "Coriander Powder",
            "Cumin Seeds",
            "Mustard Seeds",
            "Pav Bhaji Masala",
            "Goda Masala",
            "Sambar Powder",
            "Black Pepper",
        ],
        ["100 g", "200 g", "500 g", "Refill", "Value Pack"],
    ),
    "Snacks & Namkeen": (
        ["Chivda Ghar", "Bhusari", "Nagpur Crisp", "Haldi Bazaar"],
        [
            "Aloo Bhujia",
            "Chivda",
            "Farsan",
            "Potato Chips",
            "Chakli",
            "Mixture",
            "Masala Peanuts",
            "Banana Chips",
            "Sev",
        ],
        ["Sharing Pack", "150 g", "400 g", "Multipack", "Party Pack"],
    ),
    "Biscuits & Bakery": (
        ["Chandni", "Poona Bakers", "Golden Crust", "Malabar"],
        [
            "Glucose Biscuits",
            "Marie Biscuits",
            "Cream Biscuits",
            "Khari",
            "Nankhatai",
            "Rusk",
            "Bread Loaf",
            "Pav",
            "Cookies",
        ],
        ["Standard", "Family Pack", "Multipack", "Assorted", "Premium"],
    ),
    "Ready to Cook": (
        ["Jhat Pat", "Rasoi Rani", "Mumbai Tiffin", "Instant Ghar"],
        [
            "Instant Noodles",
            "Upma Mix",
            "Dosa Batter",
            "Idli Batter",
            "Soup Mix",
            "Pasta",
            "Frozen Parathas",
            "Gravy Base",
        ],
        ["Standard", "Family Pack", "4 Pack", "Multipack", "Value Pack"],
    ),
    "Tea & Coffee": (
        ["Nilgiri Hills", "Assam Trail", "Coorg Roast", "Chai Adda"],
        [
            "CTC Tea",
            "Green Tea",
            "Masala Chai",
            "Filter Coffee",
            "Instant Coffee",
            "Darjeeling Leaf Tea",
            "Cardamom Tea",
        ],
        ["250 g", "500 g", "1 kg", "Refill", "Premium"],
    ),
    "Soft Drinks & Juices": (
        ["Sharbat Co", "Fizz Bazaar", "Aamras", "Coolwave"],
        [
            "Cola",
            "Lemon Soda",
            "Mango Drink",
            "Orange Juice",
            "Nimbu Pani",
            "Packaged Water",
            "Energy Drink",
            "Coconut Water",
            "Jaljeera",
        ],
        ["250 ml", "600 ml", "1.25 L", "2 L", "6 Pack"],
    ),
    "Sweets & Chocolates": (
        ["Mithas", "Chitale Wadi", "Kesari", "Cocoa Bazaar"],
        [
            "Soan Papdi",
            "Kaju Katli",
            "Motichoor Ladoo",
            "Gulab Jamun Tin",
            "Milk Chocolate",
            "Dark Chocolate",
            "Rasgulla Tin",
            "Dry Fruit Box",
            "Chikki",
        ],
        ["250 g Box", "500 g Box", "Gift Box", "Assorted", "Family Pack"],
    ),
    "Home Care": (
        ["Chamak", "Nirmal", "Safai Sathi", "Gharwala"],
        [
            "Dishwash Gel",
            "Floor Cleaner",
            "Toilet Cleaner",
            "Glass Cleaner",
            "Phenyl",
            "Scrub Pads",
            "Garbage Bags",
            "Room Freshener",
        ],
        ["500 ml", "1 L", "Refill", "Twin Pack", "Value Pack"],
    ),
    "Detergents & Laundry": (
        ["Ujala Ghar", "Nirmal", "Shubhra", "Dhulai"],
        [
            "Detergent Powder",
            "Detergent Bar",
            "Liquid Detergent",
            "Fabric Conditioner",
            "Stain Remover",
            "Blue Whitener",
        ],
        ["1 kg", "2 kg", "500 ml", "Refill", "Value Pack"],
    ),
    "Paper & Disposables": (
        ["Softwrap", "Gharwala", "Panchali", "Neatfold"],
        [
            "Kitchen Towel",
            "Toilet Rolls",
            "Facial Tissues",
            "Aluminium Foil",
            "Cling Wrap",
            "Paper Plates",
            "Napkins",
        ],
        ["Single", "2 Pack", "4 Pack", "Family Pack", "Value Pack"],
    ),
    "Personal Care": (
        ["Kesh Kanti", "Neem Vatika", "Chandan Bazaar", "Silverbirch"],
        [
            "Shampoo",
            "Hair Oil",
            "Bathing Soap",
            "Body Wash",
            "Toothpaste",
            "Face Wash",
            "Talc",
            "Shaving Cream",
            "Deodorant",
        ],
        ["Standard", "Large", "Combo Pack", "Refill", "Family Pack"],
    ),
    "Health & Wellness": (
        ["Ayur Bhandar", "Wellspring", "Tulsi", "Arogya"],
        [
            "Chyawanprash",
            "Multivitamins",
            "Pain Relief Balm",
            "Antiseptic Liquid",
            "Honey",
            "Glucose Powder",
            "Bandages",
            "Digestive Tablets",
        ],
        ["Standard", "Large", "Value Pack", "Family Pack", "Combo"],
    ),
    "Baby Care": (
        ["Nanhe Kadam", "Little Konkan", "Shishu", "Nazuk"],
        [
            "Diapers",
            "Baby Wipes",
            "Baby Soap",
            "Baby Oil",
            "Infant Cereal",
            "Baby Lotion",
            "Feeding Bottle",
        ],
        ["Small", "Medium", "Large", "Multipack", "Value Pack"],
    ),
    "Pooja & Festive": (
        ["Deepmala", "Shubh Labh", "Kesari", "Utsav Ghar"],
        [
            "Diya Set",
            "Agarbatti",
            "Camphor",
            "Rangoli Colours",
            "Puja Thali",
            "Cotton Wicks",
            "Gift Wrap",
            "Torans",
            "LED String Lights",
            "Dhoop Sticks",
        ],
        ["Pack of 6", "Pack of 12", "Single", "Assorted", "Gift Set"],
    ),
}

SUPPLIER_DEFS = [
    ("SUP-01", "Sahyadri Agro Traders", ("Fruits & Vegetables",)),
    ("SUP-02", "Godavari Grains & Pulses", ("Atta, Rice & Dal",)),
    ("SUP-03", "Gokul Dairy Distributors", ("Dairy & Paneer",)),
    ("SUP-04", "Deccan Oils & Provisions", ("Edible Oils & Ghee", "Masalas & Spices")),
    ("SUP-05", "Bhusari Foods Pvt Ltd", ("Snacks & Namkeen", "Biscuits & Bakery")),
    ("SUP-06", "Jhat Pat Foods", ("Ready to Cook",)),
    ("SUP-07", "Nilgiri Beverage Company", ("Tea & Coffee", "Soft Drinks & Juices")),
    ("SUP-08", "Mithas Confectioners", ("Sweets & Chocolates",)),
    ("SUP-09", "Nirmal Home Products", ("Home Care", "Detergents & Laundry")),
    ("SUP-10", "Softwrap Paper Mills", ("Paper & Disposables",)),
    ("SUP-11", "Arogya Consumer Care", ("Personal Care", "Health & Wellness")),
    ("SUP-12", "Deepmala Festive Supplies", ("Baby Care", "Pooja & Festive")),
]


@dataclass(frozen=True)
class SizeSpec:
    """What differs between the two datasets.

    small and full are INDEPENDENT datasets, not subset and superset. The
    reference data (categories, products, suppliers) is identical; the store
    count, the length of history and the transaction volume differ. Every eval
    runs against full — see docs/PROGRESS.md.
    """

    name: str
    store_count: int
    days: int
    units_per_day: int
    product_count: int
    promotion_count: int


SIZES = {
    "small": SizeSpec("small", 1, 180, 420, 600, 14),
    "full": SizeSpec("full", 3, 546, 520, 600, 46),
}


# ─────────────────────────────────────────────────────────────────────────────
# Determinism helpers
# ─────────────────────────────────────────────────────────────────────────────


def substream(*parts: object) -> Random:
    """An independent RNG derived from MASTER_SEED and a stream name.

    Deliberately not `hash()`: Python salts string hashes per process, so a
    hash()-derived seed changes between runs. sha256 does not.
    """
    key = "|".join(str(p) for p in parts).encode("utf-8")
    digest = hashlib.sha256(key).digest()
    return Random(int.from_bytes(digest[:8], "big") ^ MASTER_SEED)


_EXP_CACHE: dict[float, float] = {}


def poisson(rng: Random, lam: float) -> int:
    """Knuth's Poisson sampler.

    lam is quantised to four decimals before use. That makes the exp() cache
    effective and, more importantly, stops the draw depending on the last bits
    of a long chain of float multiplications.
    """
    if lam <= 0.0:
        return 0
    lam = min(lam, 40.0)
    key = round(lam, 4)
    limit = _EXP_CACHE.get(key)
    if limit is None:
        limit = math.exp(-key)
        _EXP_CACHE[key] = limit
    k = 0
    p = 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


TWO_PLACES = Decimal("0.01")


def money(value: object) -> Decimal:
    """Quantise to 2dp, ROUND_HALF_UP. Every monetary value goes through here."""
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def weighted_choice(rng: Random, options: list[tuple[object, int]]) -> object:
    total = sum(w for _, w in options)
    roll = rng.randrange(total)
    upto = 0
    for value, weight in options:
        upto += weight
        if roll < upto:
            return value
    return options[-1][0]


# ─────────────────────────────────────────────────────────────────────────────
# CSV output
# ─────────────────────────────────────────────────────────────────────────────

TABLE_ORDER = [
    "stores",
    "categories",
    "gst_rates",
    "festivals",
    "suppliers",
    "products",
    "users",
    "supplier_products",
    "supplier_prices",
    "supplier_terms",
    "promotions",
    "promotion_products",
    "inventory",
    "purchase_orders",
    "purchase_order_lines",
    "sales",
    "sale_lines",
    "sale_operators",
    "inventory_movements",
    "stockout_days",
]

# Column order matches the declaration order in migrations/001_core_schema.sql,
# minus generated columns (valid_period), which COPY must not receive.
COLUMNS = {
    "stores": ["store_id", "code", "name", "city", "timezone", "opened_on"],
    "categories": ["category_id", "name", "department"],
    "festivals": [
        "festival_id",
        "name",
        "festival_date",
        "ramp_start",
        "ramp_end",
        "is_regional",
        "notes",
    ],
    "gst_rates": [
        "gst_rate_id",
        "category_id",
        "rate_pct",
        "effective_from",
        "effective_to",
        "source",
        "notes",
        "supersedes_id",
    ],
    "suppliers": ["supplier_id", "code", "name", "contact_email", "is_active"],
    "products": [
        "product_id",
        "sku",
        "name",
        "category_id",
        "unit_of_measure",
        "pack_size",
        "list_price",
        "is_active",
        "discontinued_on",
    ],
    "users": ["user_id", "username", "display_name", "role", "store_id", "is_active"],
    "supplier_products": [
        "supplier_product_id",
        "supplier_id",
        "product_id",
        "supplier_sku",
        "is_preferred",
        "min_order_qty",
        "case_pack",
    ],
    "supplier_prices": [
        "supplier_price_id",
        "supplier_id",
        "product_id",
        "unit_cost",
        "currency",
        "effective_from",
        "effective_to",
        "source",
        "supersedes_id",
    ],
    "supplier_terms": [
        "supplier_terms_id",
        "supplier_id",
        "payment_terms_days",
        "lead_time_days",
        "min_order_value",
        "volume_discount_pct",
        "returns_window_days",
        "effective_from",
        "effective_to",
        "source",
        "source_note",
        "supersedes_id",
    ],
    "promotions": [
        "promotion_id",
        "store_id",
        "name",
        "discount_pct",
        "starts_on",
        "ends_on",
    ],
    "promotion_products": ["promotion_id", "product_id"],
    "inventory": [
        "store_id",
        "product_id",
        "on_hand",
        "reorder_point",
        "reorder_qty",
        "last_counted_on",
    ],
    "purchase_orders": [
        "po_id",
        "store_id",
        "supplier_id",
        "status",
        "source",
        "ordered_on",
        "expected_on",
        "received_on",
        "subtotal",
        "created_by_user_id",
    ],
    "purchase_order_lines": [
        "po_line_id",
        "po_id",
        "product_id",
        "quantity_ordered",
        "quantity_received",
        "unit_cost",
        "line_total",
    ],
    "sales": [
        "sale_id",
        "store_id",
        "sold_at",
        "business_date",
        "sale_type",
        "tender_type",
        "subtotal",
        "discount_total",
        "tax_total",
        "total",
    ],
    "sale_lines": [
        "sale_line_id",
        "sale_id",
        "store_id",
        "business_date",
        "product_id",
        "promotion_id",
        "quantity",
        "unit_price",
        "unit_cost",
        "discount_amount",
        "line_total",
    ],
    "sale_operators": ["sale_id", "store_id", "business_date", "user_id"],
    "inventory_movements": [
        "movement_id",
        "store_id",
        "product_id",
        "business_date",
        "movement_type",
        "quantity",
        "reference_type",
        "reference_id",
        "note",
    ],
    "stockout_days": ["store_id", "product_id", "business_date"],
}


class CsvSet:
    """Open writers for every table, written to as rows are produced.

    Row order is iteration order — nothing is sorted afterwards. That is both a
    determinism rule and what keeps memory flat on the 600k-row tables.
    """

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir
        self._files: dict[str, object] = {}
        self._writers: dict[str, object] = {}
        self.counts: dict[str, int] = {}
        out_dir.mkdir(parents=True, exist_ok=True)

        # Clear previously generated files first. Adding or removing a table
        # renumbers every file after it, and a stale CSV left behind from the
        # old numbering gets picked up by `make seed`'s glob and loaded a
        # second time under its old name — which surfaces as a duplicate-key
        # error if you are lucky and as duplicated data if you are not.
        # Scoped to the NNN_name.csv pattern so nothing else in the directory
        # is at risk.
        for stale in out_dir.glob("[0-9][0-9][0-9]_*.csv"):
            stale.unlink()
        for index, table in enumerate(TABLE_ORDER, start=1):
            path = out_dir / f"{index:03d}_{table}.csv"
            handle = path.open("w", newline="", encoding="utf-8")
            writer = csv.writer(handle, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
            writer.writerow(COLUMNS[table])
            self._files[table] = handle
            self._writers[table] = writer
            self.counts[table] = 0

    def row(self, table: str, *values: object) -> None:
        self._writers[table].writerow(values)  # type: ignore[attr-defined]
        self.counts[table] += 1

    def close(self) -> None:
        for handle in self._files.values():
            handle.close()  # type: ignore[attr-defined]

    def filenames(self) -> list[str]:
        return [
            f"{index:03d}_{table}.csv"
            for index, table in enumerate(TABLE_ORDER, start=1)
        ]


# ─────────────────────────────────────────────────────────────────────────────
# Reference data
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Product:
    product_id: int
    sku: str
    name: str
    category_id: int
    category_name: str
    department: str
    list_price: Decimal
    unit_cost: Decimal
    pack_size: int
    base_rate: float
    supplier_id: int
    case_pack: int
    min_order_qty: int


@dataclass
class Store:
    store_id: int
    code: str
    name: str
    city: str
    factor: float
    opened_on: date
    tz: ZoneInfo = field(repr=False, default=None)  # type: ignore[assignment]


def build_categories(csvs: CsvSet) -> dict[str, int]:
    ids: dict[str, int] = {}
    for index, cat in enumerate(CATEGORY_DEFS, start=1):
        ids[cat.name] = index
        csvs.row("categories", index, cat.name, cat.department)
    return ids


def build_festivals(csvs: CsvSet, window_start: date, window_end: date) -> None:
    """Emit the festival calendar the demand model already runs on.

    Only festivals whose day falls inside the window, so the table never
    describes trade the sales history does not contain. Consumes no RNG — this
    is the same static calendar the multiplier is built from, published rather
    than recomputed, so the two can never disagree.
    """
    festival_id = 0
    for festival in FESTIVALS:
        if not (window_start <= festival.peak <= window_end):
            continue
        festival_id += 1
        regional = festival.name in REGIONAL_FESTIVAL_WEIGHT
        csvs.row(
            "festivals",
            festival_id,
            festival.name,
            festival.peak.isoformat(),
            (festival.peak - timedelta(days=festival.ramp_days)).isoformat(),
            (festival.peak + timedelta(days=festival.tail_days)).isoformat(),
            "true" if regional else "false",
            "Larger in Pune than elsewhere in the chain" if regional else None,
        )


def build_gst_rates(csvs: CsvSet, category_ids: dict[str, int]) -> None:
    """GST rates as a temporal history, one row per category per slab period.

    Two rows per category: the pre-reform rate, closed on the reform date, and
    the post-reform rate, open-ended. Categories whose rate did not change
    still get two rows — the slab was legally re-enacted, the period boundary
    is real, and collapsing unchanged categories into one row would make
    "which categories changed on 22 September" answerable only by comparing
    row counts, which is a worse question to have to ask.
    """
    rate_id = 0
    for name, (before, after) in GST_SLABS.items():
        category_id = category_ids[name]
        rate_id += 1
        first_id = rate_id
        csvs.row(
            "gst_rates",
            rate_id,
            category_id,
            f"{before}.00",
            (GST_REFORM_DATE - timedelta(days=1826)).isoformat(),
            GST_REFORM_DATE.isoformat(),
            "seed",
            "Pre-reform slab",
            None,
        )
        rate_id += 1
        csvs.row(
            "gst_rates",
            rate_id,
            category_id,
            f"{after}.00",
            GST_REFORM_DATE.isoformat(),
            None,
            "seed",
            "56th GST Council, effective 22 September 2025"
            + ("" if before == after else f" — moved from {before}% to {after}%"),
            first_id,
        )


def build_stores(csvs: CsvSet, spec: SizeSpec) -> list[Store]:
    stores: list[Store] = []
    for index, (code, name, city, factor, opened) in enumerate(
        STORE_DEFS[: spec.store_count], start=1
    ):
        stores.append(
            Store(index, code, name, city, factor, opened, ZoneInfo(TIMEZONE))
        )
        csvs.row("stores", index, code, name, city, TIMEZONE, opened.isoformat())
    return stores


def build_users(csvs: CsvSet, stores: list[Store]) -> dict[int, list[int]]:
    """Staff accounts.

    ADR-0002 forbids demoing with employee names, including realistic-looking
    synthetic ones, in a public repository. Display names are therefore
    role-and-ordinal labels and nothing else.
    """
    per_store: dict[int, list[int]] = {s.store_id: [] for s in stores}
    user_id = 0

    user_id += 1
    csvs.row("users", user_id, "owner", "Owner", "owner", None, "true")

    for store in stores:
        user_id += 1
        csvs.row(
            "users",
            user_id,
            f"manager{store.store_id:02d}",
            f"Manager {store.store_id:02d}",
            "manager",
            store.store_id,
            "true",
        )
        per_store[store.store_id].append(user_id)

    for store in stores:
        for n in range(1, 7):
            user_id += 1
            csvs.row(
                "users",
                user_id,
                f"clerk{store.store_id:02d}{n:02d}",
                f"Clerk {store.store_id:02d}-{n:02d}",
                "clerk",
                store.store_id,
                "true",
            )
            per_store[store.store_id].append(user_id)
    return per_store


def build_suppliers(csvs: CsvSet) -> dict[str, int]:
    by_category: dict[str, int] = {}
    for index, (code, name, categories) in enumerate(SUPPLIER_DEFS, start=1):
        slug = code.lower().replace("-", "")
        csvs.row("suppliers", index, code, name, f"orders@{slug}.example", "true")
        for category in categories:
            by_category[category] = index
    return by_category


def build_products(
    csvs: CsvSet,
    spec: SizeSpec,
    category_ids: dict[str, int],
    supplier_by_category: dict[str, int],
) -> list[Product]:
    """Generate the catalogue and normalise demand rates to the size target."""
    rng = substream("catalogue")
    by_name = {cat.name: cat for cat in CATEGORY_DEFS}
    category_names = [cat.name for cat in CATEGORY_DEFS]

    # Distribute products across categories, weighted so grocery is deepest.
    # This is catalogue DEPTH, which is a different thing from demand_weight:
    # a store carries many kinds of pasta and sells a lot of milk.
    weights = [
        3.0 if by_name[name].department == "Grocery" else 1.6 for name in category_names
    ]
    total_weight = sum(weights)
    allocation = [max(8, int(spec.product_count * w / total_weight)) for w in weights]
    while sum(allocation) > spec.product_count:
        allocation[allocation.index(max(allocation))] -= 1
    while sum(allocation) < spec.product_count:
        allocation[allocation.index(min(allocation))] += 1

    products: list[Product] = []
    product_id = 0
    per_category_seq: dict[str, int] = {}

    for category_name, count in zip(category_names, allocation, strict=True):
        cat = by_name[category_name]
        prefixes, nouns, variants = NAME_PARTS[category_name]
        code = CATEGORY_CODES[category_name]
        seen: dict[str, int] = {}
        for _ in range(count):
            product_id += 1
            seq = per_category_seq.get(category_name, 0) + 1
            per_category_seq[category_name] = seq

            prefix = prefixes[rng.randrange(len(prefixes))]
            noun = nouns[rng.randrange(len(nouns))]
            variant = variants[rng.randrange(len(variants))]
            name = f"{prefix} {noun} {variant}"
            if name in seen:
                seen[name] += 1
                name = f"{name} #{seen[name]}"
            else:
                seen[name] = 1

            # Log-normal shelf price, snapped to a retail-looking ending.
            # Price: the category's typical shelf price, moved by pack size,
            # with log-normal spread around it. Indian MRP is whole rupees
            # ending in 0, 5 or 9 — no paise on a shelf edge.
            raw_price = (
                CATEGORY_PRICE_MEDIAN[category_name]
                * variant_price_factor(variant)
                * math.exp(rng.gauss(0.0, 0.34))
            )
            if raw_price < 25:
                price = money(Decimal(max(5, round(raw_price / 5) * 5)))
            else:
                tens = max(1, round(raw_price / 10))
                price = money(Decimal(tens * 10 - rng.choice([0, 0, 1, 5])))

            margin = cat.margin * rng.uniform(0.85, 1.15)
            cost = money(price * Decimal(str(1.0 - min(0.7, max(0.12, margin)))))

            # Log-normal demand — a short head of fast movers and a long tail —
            # scaled by how much volume the category pulls. Without the
            # category weight the top sellers come out as whatever the
            # log-normal happened to favour, and a grocer's best-selling list
            # led by stain remover and dog treats does not look like a real
            # store.
            base_rate = math.exp(rng.gauss(-0.9, 1.05)) * cat.demand_weight

            case_pack = rng.choice([1, 6, 6, 12, 12, 24])
            products.append(
                Product(
                    product_id=product_id,
                    sku=f"{code}-{seq:04d}",
                    name=name,
                    category_id=category_ids[category_name],
                    category_name=category_name,
                    department=cat.department,
                    list_price=price,
                    unit_cost=cost,
                    pack_size=rng.choice([1, 1, 1, 2, 4]),
                    base_rate=base_rate,
                    supplier_id=supplier_by_category[category_name],
                    case_pack=case_pack,
                    min_order_qty=case_pack,
                )
            )

    # Normalise so a store at factor 1.0 sells about units_per_day units.
    scale = spec.units_per_day / sum(p.base_rate for p in products)
    for product in products:
        product.base_rate *= scale
        csvs.row(
            "products",
            product.product_id,
            product.sku,
            product.name,
            product.category_id,
            "each",
            product.pack_size,
            str(product.list_price),
            "true",
            None,
        )
    return products


def build_supplier_relationships(
    csvs: CsvSet, products: list[Product], window_start: date, window_end: date
) -> dict[int, int]:
    """supplier_products, supplier_prices and supplier_terms.

    Terms and prices are written as temporal histories from the start: a period
    that was superseded, and an open-ended current period. Phase 2 adds real
    documents behind them; it does not reshape the tables.

    Every changeover date is placed RELATIVE TO THE WINDOW, not at a fixed
    offset. A fixed offset that happens to land past DATA_END_DATE produces
    rows whose "current" period has not started yet — which reads as correct in
    the table and is wrong in every answer, since the terms actually in force
    throughout the data would be the superseded ones. That is exactly the
    silent-wrong failure demo beat 2 exists to avoid.
    """
    price_id = 0
    span = (window_end - window_start).days
    lead_times: dict[int, int] = {}

    # Terms: one superseded period and one current period per supplier. The
    # renegotiation sits between 25% and 70% through the window so both
    # periods have real trading either side of them.
    terms_id = 0
    for supplier_index in range(1, len(SUPPLIER_DEFS) + 1):
        srng = substream("terms", supplier_index)
        lead_time = srng.choice([2, 3, 3, 4, 5, 5, 7, 10])
        lead_times[supplier_index] = lead_time
        renegotiated = window_start + timedelta(
            days=srng.randrange(int(span * 0.25), int(span * 0.70))
        )
        old_from = renegotiated - timedelta(days=srng.randrange(200, 700))

        terms_id += 1
        first_id = terms_id
        csvs.row(
            "supplier_terms",
            terms_id,
            supplier_index,
            srng.choice([14, 30, 30, 45]),
            lead_time + srng.choice([0, 1, 2]),
            str(money(srng.choice([8000, 12000, 15000, 25000]))),
            str(money(srng.choice([0, 0, 1.5, 2.5]))),
            srng.choice([14, 28, 30]),
            old_from.isoformat(),
            renegotiated.isoformat(),
            "seed",
            None,
            None,
        )

        terms_id += 1
        csvs.row(
            "supplier_terms",
            terms_id,
            supplier_index,
            srng.choice([30, 45, 45, 60]),
            lead_time,
            str(money(srng.choice([10000, 15000, 20000, 30000]))),
            str(money(srng.choice([0, 1.0, 2.0, 3.0]))),
            srng.choice([14, 28, 30]),
            renegotiated.isoformat(),
            None,
            "seed",
            None,
            first_id,
        )

    for supplier_product_id, product in enumerate(products, start=1):
        csvs.row(
            "supplier_products",
            supplier_product_id,
            product.supplier_id,
            product.product_id,
            f"{product.sku}-S{product.supplier_id:02d}",
            "true",
            product.min_order_qty,
            product.case_pack,
        )

        # About 60% of the catalogue was repriced during the window; the rest
        # has been on its current price since before the data starts. Both
        # cases leave the open-ended row genuinely in force today.
        prng = substream("price", product.product_id)
        if prng.random() < 0.6:
            changed_on = window_start + timedelta(
                days=prng.randrange(int(span * 0.15), int(span * 0.80))
            )
        else:
            changed_on = window_start - timedelta(days=prng.randrange(10, 120))
        old_from = changed_on - timedelta(days=prng.randrange(120, 400))
        old_cost = money(product.unit_cost * Decimal(str(prng.uniform(0.88, 0.97))))

        price_id += 1
        first_price_id = price_id
        csvs.row(
            "supplier_prices",
            price_id,
            product.supplier_id,
            product.product_id,
            str(old_cost),
            CURRENCY,
            old_from.isoformat(),
            changed_on.isoformat(),
            "seed",
            None,
        )

        price_id += 1
        csvs.row(
            "supplier_prices",
            price_id,
            product.supplier_id,
            product.product_id,
            str(product.unit_cost),
            CURRENCY,
            changed_on.isoformat(),
            None,
            "seed",
            first_price_id,
        )

    return lead_times


def build_promotions(
    csvs: CsvSet,
    spec: SizeSpec,
    products: list[Product],
    stores: list[Store],
    window_start: date,
    window_end: date,
) -> dict[tuple[int, int], list[tuple[date, date, int, Decimal]]]:
    """Promotional events, returned as a lookup for the simulation."""
    rng = substream("promotions")
    span = (window_end - window_start).days
    lookup: dict[tuple[int, int], list[tuple[date, date, int, Decimal]]] = {}

    for promotion_id in range(1, spec.promotion_count + 1):
        store = stores[rng.randrange(len(stores))]
        starts = window_start + timedelta(days=rng.randrange(0, max(1, span - 21)))
        ends = starts + timedelta(days=rng.choice([6, 13, 13, 20, 27]))
        if ends > window_end:
            ends = window_end
        discount = money(rng.choice([10, 15, 20, 25, 25, 33]))

        category = CATEGORY_DEFS[rng.randrange(len(CATEGORY_DEFS))].name
        pool = [p for p in products if p.category_name == category]
        chosen = rng.sample(pool, min(len(pool), rng.randrange(4, 12)))
        chosen.sort(key=lambda p: p.product_id)

        csvs.row(
            "promotions",
            promotion_id,
            store.store_id,
            f"{category} — {int(discount)}% off",
            str(discount),
            starts.isoformat(),
            ends.isoformat(),
        )
        for product in chosen:
            csvs.row("promotion_products", promotion_id, product.product_id)
            lookup.setdefault((store.store_id, product.product_id), []).append(
                (starts, ends, promotion_id, discount)
            )
    return lookup


# ─────────────────────────────────────────────────────────────────────────────
# Demand factors, precomputed
# ─────────────────────────────────────────────────────────────────────────────


def festival_multiplier(festival: Festival, day: date) -> float | None:
    """Where `day` sits on this festival's curve, or None if outside it.

    Three regions: a ramp before, the day itself, and a tail after.

    The ramp is `1 + (peak - 1) * progress ** shape`, where progress runs 0 at
    the far edge to 1 the day before. With shape > 1 the early weeks stay
    almost flat and the last few days climb hard, which is the shape a real
    festive build has — and the reason a single-day multiplier or a sinusoid
    cannot stand in for it.
    """
    delta = (day - festival.peak).days

    if delta == 0:
        return festival.day_factor

    if delta < 0:
        offset = -delta
        if offset > festival.ramp_days:
            return None
        progress = (festival.ramp_days - offset + 1) / festival.ramp_days
        return 1.0 + (festival.ramp_peak - 1.0) * progress**festival.ramp_shape

    if delta > festival.tail_days:
        return None
    decay = 1.0 - (delta / (festival.tail_days + 1))
    return 1.0 + (festival.tail_factor - 1.0) * decay


def build_day_factors(
    window_start: date, window_end: date, store_id: int
) -> dict[date, float]:
    """The festival factor for every day in the window, for one store.

    Per store, because some festivals are regional. Overlapping festivals
    combine by taking the strongest rather than by multiplying: through
    September and October, Ganesh Chaturthi's tail, Navratri, Dussehra and the
    Diwali ramp all overlap, and multiplying four ramps together produces a
    number no shop has ever seen. Taking the max produces a sustained six-week
    elevation with peaks on the individual days, which is what the season
    actually looks like.

    Days at or below 1.0 win outright — Holi morning is quiet regardless of
    what else is ramping.
    """
    factors: dict[date, float] = {}
    for festival in FESTIVALS:
        weight = REGIONAL_FESTIVAL_WEIGHT.get(festival.name, {}).get(store_id, 1.0)
        span_start = festival.peak - timedelta(days=festival.ramp_days)
        span_end = festival.peak + timedelta(days=festival.tail_days)
        day = span_start
        while day <= span_end:
            if window_start <= day <= window_end:
                raw = festival_multiplier(festival, day)
                if raw is not None:
                    # Regional weight scales the deviation from 1.0, not the
                    # multiplier, so a weight of 0.9 damps the effect rather
                    # than damping trade.
                    value = 1.0 + (raw - 1.0) * weight
                    current = factors.get(day)
                    if current is None:
                        factors[day] = value
                    elif current <= 1.0 or value <= 1.0:
                        factors[day] = min(current, value)
                    else:
                        factors[day] = max(current, value)
            day += timedelta(days=1)
    return factors


def build_seasonality() -> dict[int, list[float]]:
    """A yearly sinusoid per category, precomputed for all 366 days.

    Precomputing takes math.sin out of the inner loop entirely, which is worth
    about a third of total runtime and removes 1M libm calls from the
    reproducibility surface.
    """
    table: dict[int, list[float]] = {}
    for index, cat in enumerate(CATEGORY_DEFS, start=1):
        table[index] = [
            1.0
            + cat.amplitude * math.cos(2.0 * math.pi * (doy - cat.peak_doy) / 365.25)
            for doy in range(0, 367)
        ]
    return table


def build_dow_factors() -> dict[int, list[float]]:
    """Weekday shape per category. Monday index 0, Sunday index 6.

    Sunday is the peak, not Saturday: Indian grocery weeks build to a Sunday
    family shop, with Saturday second. Weekend_uplift on the category is the
    Sunday figure and Saturday derives from it.
    """
    base = [0.86, 0.90, 0.95, 1.00, 1.08, 1.00, 1.00]
    table: dict[int, list[float]] = {}
    for index, cat in enumerate(CATEGORY_DEFS, start=1):
        row = list(base)
        row[6] = cat.weekend_uplift
        row[5] = 1.0 + (cat.weekend_uplift - 1.0) * 0.80
        table[index] = row
    return table


# ─────────────────────────────────────────────────────────────────────────────
# Simulation
# ─────────────────────────────────────────────────────────────────────────────


def simulate(csvs: CsvSet, spec: SizeSpec) -> dict[str, object]:
    window_end = DATA_END_DATE
    window_start = window_end - timedelta(days=spec.days - 1)

    category_ids = build_categories(csvs)
    build_gst_rates(csvs, category_ids)
    build_festivals(csvs, window_start, window_end)
    stores = build_stores(csvs, spec)
    supplier_by_category = build_suppliers(csvs)
    products = build_products(csvs, spec, category_ids, supplier_by_category)
    users_by_store = build_users(csvs, stores)
    lead_times = build_supplier_relationships(csvs, products, window_start, window_end)
    promo_lookup = build_promotions(
        csvs, spec, products, stores, window_start, window_end
    )

    seasonality = build_seasonality()
    dow_factors = build_dow_factors()
    dates = [window_start + timedelta(days=i) for i in range(spec.days)]
    trend = [1.0 + 0.12 * (i / max(1, spec.days - 1)) for i in range(spec.days)]

    by_id = {p.product_id: p for p in products}
    # GST is looked up by (category, business_date), not by category alone:
    # the 22 September 2025 reform falls inside the window, so a sale in
    # August and a sale in October are taxed at different rates for the same
    # product. Both rates are precomputed as fractions to keep the hot loop
    # free of lookups.
    gst_before = {
        p.product_id: Decimal(GST_SLABS[p.category_name][0]) / 100 for p in products
    }
    gst_after = {
        p.product_id: Decimal(GST_SLABS[p.category_name][1]) / 100 for p in products
    }
    festive_lift = {
        p.product_id: CATEGORY_DEFS[p.category_id - 1].festive_lift for p in products
    }

    sale_id = 0
    sale_line_id = 0
    movement_id = 0
    po_id = 0
    po_line_id = 0

    for store in stores:
        srng = substream("store-ops", store.store_id)
        # Per store: some festivals are regional.
        day_factors = build_day_factors(window_start, window_end, store.store_id)
        demand_rngs = {
            p.product_id: substream("demand", store.store_id, p.product_id)
            for p in products
        }

        # Opening stock, recorded as a movement so that the invariant
        # on_hand = sum(movements) - sum(sale_lines) holds for every product.
        on_hand: dict[int, int] = {}
        reorder_point: dict[int, int] = {}
        reorder_qty: dict[int, int] = {}
        for product in products:
            daily = product.base_rate * store.factor
            cover = srng.uniform(12.0, 26.0)
            opening = max(2, round(daily * cover))
            on_hand[product.product_id] = opening
            reorder_point[product.product_id] = max(
                2, round(daily * (lead_times[product.supplier_id] + 3))
            )
            reorder_qty[product.product_id] = max(
                product.case_pack, round(daily * srng.uniform(14.0, 24.0))
            )
            movement_id += 1
            csvs.row(
                "inventory_movements",
                movement_id,
                store.store_id,
                product.product_id,
                window_start.isoformat(),
                "count_correction",
                opening,
                None,
                None,
                "Opening stock count",
            )

        incoming: dict[date, list[tuple[int, int, int]]] = {}
        open_orders: dict[int, bool] = {}
        clerks = users_by_store[store.store_id]

        for day_index, business_date in enumerate(dates):
            weekday = business_date.weekday()
            doy = business_date.timetuple().tm_yday
            day_factor = day_factors.get(business_date, 1.0)
            # Which side of the 22 September 2025 GST reform this day sits on.
            rate_today = gst_after if business_date >= GST_REFORM_DATE else gst_before
            trend_factor = trend[day_index]

            # Deliveries arrive before trading.
            for po_ref, product_id, quantity in incoming.pop(business_date, []):
                on_hand[product_id] += quantity
                movement_id += 1
                csvs.row(
                    "inventory_movements",
                    movement_id,
                    store.store_id,
                    product_id,
                    business_date.isoformat(),
                    "delivery",
                    quantity,
                    "purchase_order",
                    po_ref,
                    None,
                )
                open_orders.pop(product_id, None)

            # No Indian festival in FESTIVALS closes the store — trade drops
            # sharply on Holi morning but does not stop. The guard stays for
            # any calendar that does set a zero.
            if day_factor <= 0.0:
                continue  # closed

            # Demand, clamped by stock.
            sold_today: list[tuple[int, int, int | None, Decimal]] = []
            for product in products:
                pid = product.product_id
                # The festival factor is scaled per category before it is
                # applied: a 2.4x Dhanteras is 2.4x for gift boxes and diyas
                # and much less than that for toilet rolls.
                #
                # Only the UPLIFT is scaled. A quiet day — Holi morning, the
                # slump after Diwali — hits every category equally, because
                # what closes is the shop's footfall, not one aisle's appeal.
                # Scaling downward by festive_lift would also drive lambda
                # negative for the high-lift categories.
                if day_factor >= 1.0:
                    festival_factor = 1.0 + (day_factor - 1.0) * festive_lift[pid]
                else:
                    festival_factor = day_factor

                lam = (
                    product.base_rate
                    * store.factor
                    * seasonality[product.category_id][doy]
                    * dow_factors[product.category_id][weekday]
                    * trend_factor
                    * festival_factor
                )

                promotion_id: int | None = None
                unit_price = product.list_price
                for starts, ends, promo_id, discount in promo_lookup.get(
                    (store.store_id, pid), ()
                ):
                    if starts <= business_date <= ends:
                        promotion_id = promo_id
                        elasticity = CATEGORY_DEFS[
                            product.category_id - 1
                        ].promo_elasticity
                        lam *= 1.0 + elasticity * float(discount) / 100.0
                        unit_price = money(
                            product.list_price
                            * (Decimal(100) - discount)
                            / Decimal(100)
                        )
                        break

                demand = poisson(demand_rngs[pid], lam)
                if demand <= 0:
                    continue
                available = on_hand[pid]
                if available <= 0:
                    csvs.row(
                        "stockout_days", store.store_id, pid, business_date.isoformat()
                    )
                    continue
                sold = min(demand, available)
                if sold < demand:
                    csvs.row(
                        "stockout_days", store.store_id, pid, business_date.isoformat()
                    )
                on_hand[pid] -= sold
                sold_today.append((pid, sold, promotion_id, unit_price))

            # Split the day's units into lines, then deal lines into baskets.
            brng = substream("basket", store.store_id, business_date.toordinal())
            lines: list[tuple[int, int, int | None, Decimal]] = []
            for pid, sold, promotion_id, unit_price in sold_today:
                remaining = sold
                while remaining > 0:
                    take = min(remaining, brng.choice([1, 1, 1, 1, 2, 2, 3]))
                    lines.append((pid, take, promotion_id, unit_price))
                    remaining -= take
            brng.shuffle(lines)

            cursor = 0
            while cursor < len(lines):
                basket_size = min(
                    len(lines) - cursor, brng.choice([1, 1, 2, 2, 3, 3, 4, 5, 6, 8])
                )
                basket = lines[cursor : cursor + basket_size]
                cursor += basket_size

                hour = weighted_choice(
                    brng,
                    [(OPEN_HOUR + i, w) for i, w in enumerate(HOURLY_WEIGHTS)],
                )
                sold_at = datetime(
                    business_date.year,
                    business_date.month,
                    business_date.day,
                    int(hour),
                    brng.randrange(60),
                    brng.randrange(60),
                    tzinfo=store.tz,
                )

                sale_id += 1
                subtotal = Decimal("0.00")
                discount_total = Decimal("0.00")
                tax_total = Decimal("0.00")
                pending: list[tuple] = []
                for pid, quantity, promotion_id, unit_price in basket:
                    product = by_id[pid]
                    gross = money(unit_price * quantity)
                    discount = money((product.list_price - unit_price) * quantity)
                    tax = money(gross * rate_today[pid])
                    subtotal += gross
                    discount_total += discount
                    tax_total += tax
                    sale_line_id += 1
                    pending.append(
                        (
                            "sale_lines",
                            sale_line_id,
                            sale_id,
                            store.store_id,
                            business_date.isoformat(),
                            pid,
                            promotion_id,
                            quantity,
                            str(unit_price),
                            str(product.unit_cost),
                            str(discount),
                            str(gross),
                        )
                    )

                csvs.row(
                    "sales",
                    sale_id,
                    store.store_id,
                    sold_at.isoformat(),
                    business_date.isoformat(),
                    "sale",
                    weighted_choice(brng, TENDER_WEIGHTS),
                    str(subtotal),
                    str(discount_total),
                    str(tax_total),
                    str(subtotal + tax_total),
                )
                for row in pending:
                    csvs.row(*row)
                csvs.row(
                    "sale_operators",
                    sale_id,
                    store.store_id,
                    business_date.isoformat(),
                    clerks[brng.randrange(len(clerks))],
                )

            # Returns: a few baskets a day come back, and stock goes back with
            # them. This is why sale_lines.quantity is signed.
            if sold_today and brng.random() < 0.55:
                for _ in range(brng.randrange(1, 4)):
                    pid, _sold, promotion_id, unit_price = sold_today[
                        brng.randrange(len(sold_today))
                    ]
                    product = by_id[pid]
                    quantity = -brng.choice([1, 1, 2])
                    on_hand[pid] -= quantity
                    gross = money(unit_price * quantity)
                    tax = money(gross * rate_today[pid])
                    sale_id += 1
                    sale_line_id += 1
                    sold_at = datetime(
                        business_date.year,
                        business_date.month,
                        business_date.day,
                        brng.randrange(OPEN_HOUR, CLOSE_HOUR),
                        brng.randrange(60),
                        brng.randrange(60),
                        tzinfo=store.tz,
                    )
                    csvs.row(
                        "sales",
                        sale_id,
                        store.store_id,
                        sold_at.isoformat(),
                        business_date.isoformat(),
                        "return",
                        weighted_choice(brng, TENDER_WEIGHTS),
                        str(gross),
                        "0.00",
                        str(tax),
                        str(gross + tax),
                    )
                    csvs.row(
                        "sale_lines",
                        sale_line_id,
                        sale_id,
                        store.store_id,
                        business_date.isoformat(),
                        pid,
                        promotion_id,
                        quantity,
                        str(unit_price),
                        str(product.unit_cost),
                        "0.00",
                        str(gross),
                    )
                    csvs.row(
                        "sale_operators",
                        sale_id,
                        store.store_id,
                        business_date.isoformat(),
                        clerks[brng.randrange(len(clerks))],
                    )

            # Shrinkage: a handful of units go missing most days.
            if srng.random() < 0.6:
                for _ in range(srng.randrange(1, 4)):
                    product = products[srng.randrange(len(products))]
                    pid = product.product_id
                    if on_hand[pid] <= 0:
                        continue
                    loss = min(on_hand[pid], srng.choice([1, 1, 2]))
                    on_hand[pid] -= loss
                    movement_id += 1
                    csvs.row(
                        "inventory_movements",
                        movement_id,
                        store.store_id,
                        pid,
                        business_date.isoformat(),
                        "shrinkage",
                        -loss,
                        None,
                        None,
                        "Cycle count variance",
                    )

            # Restock. One purchase order per supplier per day at most.
            due: dict[int, list[tuple[int, int]]] = {}
            for product in products:
                pid = product.product_id
                if open_orders.get(pid):
                    continue
                if on_hand[pid] > reorder_point[pid]:
                    continue
                quantity = max(product.min_order_qty, reorder_qty[pid])
                quantity = (-(-quantity // product.case_pack)) * product.case_pack
                due.setdefault(product.supplier_id, []).append((pid, quantity))

            for supplier_id, items in due.items():
                lead_time = lead_times[supplier_id]
                po_id += 1
                subtotal = Decimal("0.00")
                expected_on = business_date + timedelta(days=lead_time)
                actual_on = expected_on + timedelta(
                    days=srng.choice([-1, 0, 0, 0, 1, 1, 2, 4])
                )
                if actual_on < business_date:
                    actual_on = business_date
                received = actual_on <= window_end

                lines_out = []
                for pid, quantity in items:
                    product = by_id[pid]
                    line_total = money(product.unit_cost * quantity)
                    subtotal += line_total
                    po_line_id += 1
                    lines_out.append(
                        (
                            "purchase_order_lines",
                            po_line_id,
                            po_id,
                            pid,
                            quantity,
                            quantity if received else 0,
                            str(product.unit_cost),
                            str(line_total),
                        )
                    )
                    open_orders[pid] = True
                    if received:
                        incoming.setdefault(actual_on, []).append(
                            (po_id, pid, quantity)
                        )

                csvs.row(
                    "purchase_orders",
                    po_id,
                    store.store_id,
                    supplier_id,
                    "received" if received else "submitted",
                    "seed",
                    business_date.isoformat(),
                    expected_on.isoformat(),
                    actual_on.isoformat() if received else None,
                    str(subtotal),
                    users_by_store[store.store_id][0],
                )
                for row in lines_out:
                    csvs.row(*row)

        for product in products:
            csvs.row(
                "inventory",
                store.store_id,
                product.product_id,
                on_hand[product.product_id],
                reorder_point[product.product_id],
                reorder_qty[product.product_id],
                window_end.isoformat(),
            )

    return {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "store_count": len(stores),
        "product_count": len(products),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Manifest and checksums
# ─────────────────────────────────────────────────────────────────────────────


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(
    out_dir: Path, spec: SizeSpec, csvs: CsvSet, summary: dict[str, object]
) -> dict[str, str]:
    hashes = {name: sha256_of(out_dir / name) for name in csvs.filenames()}
    manifest = {
        "generator_version": GENERATOR_VERSION,
        "master_seed": MASTER_SEED,
        "data_end_date": DATA_END_DATE.isoformat(),
        "size": spec.name,
        "currency": CURRENCY,
        "timezone": TIMEZONE,
        "locale_status": "PLACEHOLDER — not yet derived from corpus/sources/",
        "summary": summary,
        "row_counts": {table: csvs.counts[table] for table in TABLE_ORDER},
        "files": hashes,
    }
    (out_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return hashes


def checksum_lines(size: str, hashes: dict[str, str]) -> list[str]:
    return [f"{digest}  {size}/{name}" for name, digest in sorted(hashes.items())]


def update_checksums(path: Path, size: str, hashes: dict[str, str]) -> None:
    """Rewrite this size's section of seed/CHECKSUMS.txt, leaving others alone."""
    existing: list[str] = []
    if path.exists():
        existing = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.split("  ", 1)[1].startswith(f"{size}/")
        ]
    merged = sorted(
        {*existing, *checksum_lines(size, hashes)}, key=lambda x: x.split("  ")[1]
    )
    path.write_text("\n".join(merged) + "\n", encoding="utf-8")


def verify_against(path: Path, size: str, hashes: dict[str, str]) -> int:
    if not path.exists():
        print(f"FAIL: {path} does not exist — run `make seed-generate` first.")
        return 1
    recorded = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        if name.startswith(f"{size}/"):
            recorded[name.split("/", 1)[1]] = digest

    expected = dict(sorted(hashes.items()))
    if not recorded:
        print(f"FAIL: no checksums recorded for size '{size}' in {path}.")
        return 1

    failures = []
    for name, digest in expected.items():
        if name not in recorded:
            failures.append(f"  {name}: not in CHECKSUMS.txt")
        elif recorded[name] != digest:
            failures.append(
                f"  {name}:\n    recorded {recorded[name]}\n    generated {digest}"
            )
    for name in recorded:
        if name not in expected:
            failures.append(f"  {name}: in CHECKSUMS.txt but not generated")

    if failures:
        print(f"FAIL: regenerated '{size}' does not match seed/CHECKSUMS.txt")
        print("\n".join(failures))
        print(
            "\nSeed output is supposed to be byte-identical on re-run. Either a "
            "change to seed.py was intended — in which case run "
            "`make seed-generate` and commit the new checksums — or determinism "
            "has been broken. Note the claim is scoped to generation inside the "
            "pinned python:3.12-slim image; running bare Python on a different "
            "platform can differ."
        )
        return 1

    print(f"OK: '{size}' matches seed/CHECKSUMS.txt ({len(expected)} files)")
    return 0


# ─────────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", choices=sorted(SIZES), default="small")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="compare against seed/CHECKSUMS.txt instead of updating it",
    )
    args = parser.parse_args(argv)

    spec = SIZES[args.size]
    out_dir = args.out or (REPO_ROOT / "seed" / spec.name)
    checksums = REPO_ROOT / "seed" / "CHECKSUMS.txt"
    checksums.parent.mkdir(parents=True, exist_ok=True)

    csvs = CsvSet(out_dir)
    try:
        summary = simulate(csvs, spec)
    finally:
        csvs.close()

    hashes = write_manifest(out_dir, spec, csvs, summary)

    if args.verify:
        return verify_against(checksums, spec.name, hashes)

    update_checksums(checksums, spec.name, hashes)
    total = sum(csvs.counts.values())
    print(f"{spec.name}: {total:,} rows across {len(TABLE_ORDER)} tables -> {out_dir}")
    for table in TABLE_ORDER:
        print(f"  {table:<24} {csvs.counts[table]:>9,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
