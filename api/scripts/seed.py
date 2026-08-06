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
# LOCALE — PLACEHOLDER, NOT YET DERIVED FROM THE CORPUS
#
# Phase 0's seed and Phase 2's corpus have to share a world: currency, holiday
# calendar, store names and SKU conventions should all come from the same place
# the real invoices come from. The corpus does not exist yet, so everything in
# this block is a placeholder chosen to be easy to replace, not a decision.
#
# To change it: edit this block, run `make seed-generate SEED_SIZE=small` and
# `make seed-generate SEED_SIZE=full`, then commit the regenerated
# seed/small/ and seed/CHECKSUMS.txt. Nothing else in the project needs to
# change. Roughly two minutes of work — but it must happen before the Phase 1
# eval set is written, because every expected result set depends on this data.
# ─────────────────────────────────────────────────────────────────────────────

CURRENCY = "GBP"
TIMEZONE = "Europe/London"
TAX_RATE = Decimal("0.20")
TAX_EXEMPT_DEPARTMENTS = ("Grocery", "Bakery")

STORE_DEFS = [
    # code, name, city, demand factor, opened
    ("ST-01", "Riverside", "Bristol", 1.00, date(2019, 3, 11)),
    ("ST-02", "Northgate", "Leeds", 0.72, date(2021, 9, 6)),
    ("ST-03", "Meadowbank", "Manchester", 1.35, date(2017, 6, 19)),
]

# Public holidays that fall inside the generated window. Retail does not simply
# stop on a holiday — trade collapses on the day and spikes in the days before
# it, and that shape is a large part of what makes seeded data look real.
HOLIDAY_DEFS = [
    (date(2025, 1, 1), "New Year's Day", 0.35),
    (date(2025, 4, 18), "Good Friday", 0.80),
    (date(2025, 4, 21), "Easter Monday", 0.75),
    (date(2025, 5, 5), "Early May bank holiday", 0.85),
    (date(2025, 5, 26), "Spring bank holiday", 0.85),
    (date(2025, 8, 25), "Summer bank holiday", 0.88),
    (date(2025, 12, 25), "Christmas Day", 0.00),
    (date(2025, 12, 26), "Boxing Day", 0.45),
    (date(2026, 1, 1), "New Year's Day", 0.35),
    (date(2026, 4, 3), "Good Friday", 0.80),
    (date(2026, 4, 6), "Easter Monday", 0.75),
    (date(2026, 5, 4), "Early May bank holiday", 0.85),
    (date(2026, 5, 25), "Spring bank holiday", 0.85),
]

# Days before a holiday, and the demand multiplier on each. Christmas gets its
# own, much larger ramp.
PRE_HOLIDAY_RAMP = {1: 1.35, 2: 1.18, 3: 1.08}
CHRISTMAS_RAMP = {1: 2.30, 2: 1.95, 3: 1.60, 4: 1.35, 5: 1.20, 6: 1.12, 7: 1.08}

OPEN_HOUR, CLOSE_HOUR = 8, 21
# Relative footfall by hour from OPEN_HOUR to CLOSE_HOUR - 1.
HOURLY_WEIGHTS = [3, 5, 7, 9, 12, 11, 8, 7, 8, 10, 9, 6, 3]

TENDER_WEIGHTS = [("card", 62), ("cash", 18), ("mobile", 17), ("voucher", 3)]


# ─────────────────────────────────────────────────────────────────────────────
# Catalogue definition
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CategoryDef:
    """Demand shape for a category.

    A dataclass rather than a tuple because these are read by position in the
    hot loop and adding a field to a tuple silently shifts every index.
    """

    name: str
    department: str
    amplitude: float  # seasonal swing, +/- around 1.0
    peak_doy: int  # day of year demand peaks
    weekend_uplift: float  # Saturday multiplier
    promo_elasticity: float  # demand response to a discount
    margin: float  # gross margin on shelf price
    demand_weight: float  # how much of total store volume this pulls


CATEGORY_DEFS = [
    CategoryDef("Fresh Produce", "Grocery", 0.28, 196, 1.30, 1.10, 0.32, 2.60),
    CategoryDef("Bakery", "Bakery", 0.16, 350, 1.42, 0.90, 0.45, 1.90),
    CategoryDef("Dairy & Eggs", "Grocery", 0.12, 200, 1.28, 0.85, 0.28, 2.80),
    CategoryDef("Meat & Fish", "Grocery", 0.22, 355, 1.48, 1.25, 0.30, 1.80),
    CategoryDef("Frozen Foods", "Grocery", 0.18, 20, 1.24, 1.05, 0.34, 1.40),
    CategoryDef("Store Cupboard", "Grocery", 0.10, 340, 1.15, 0.80, 0.36, 1.50),
    CategoryDef("Snacks & Confectionery", "Grocery", 0.20, 300, 1.38, 1.45, 0.42, 1.70),
    CategoryDef("Soft Drinks", "Beverages", 0.42, 200, 1.35, 1.60, 0.40, 1.60),
    CategoryDef("Hot Drinks", "Beverages", 0.38, 15, 1.12, 1.15, 0.44, 0.90),
    CategoryDef("Beer, Wine & Spirits", "Beverages", 0.30, 355, 1.62, 1.35, 0.30, 1.00),
    CategoryDef("Household Cleaning", "Household", 0.12, 90, 1.18, 0.95, 0.38, 0.60),
    CategoryDef("Laundry", "Household", 0.10, 100, 1.16, 0.90, 0.36, 0.45),
    CategoryDef("Paper & Disposables", "Household", 0.08, 340, 1.20, 0.75, 0.33, 0.80),
    CategoryDef(
        "Health & Wellbeing", "Health & Beauty", 0.24, 25, 1.10, 0.85, 0.46, 0.35
    ),
    CategoryDef("Personal Care", "Health & Beauty", 0.10, 180, 1.14, 0.95, 0.44, 0.60),
    CategoryDef("Baby & Child", "Health & Beauty", 0.08, 180, 1.22, 0.80, 0.35, 0.40),
    CategoryDef(
        "Pet Supplies", "General Merchandise", 0.10, 190, 1.26, 0.90, 0.37, 0.50
    ),
    CategoryDef(
        "Seasonal & Gifting", "General Merchandise", 0.55, 352, 1.55, 1.70, 0.52, 0.25
    ),
]

CATEGORY_CODES = {
    "Fresh Produce": "PRD",
    "Bakery": "BAK",
    "Dairy & Eggs": "DRY",
    "Meat & Fish": "MTF",
    "Frozen Foods": "FRZ",
    "Store Cupboard": "CUP",
    "Snacks & Confectionery": "SNK",
    "Soft Drinks": "SFT",
    "Hot Drinks": "HOT",
    "Beer, Wine & Spirits": "BWS",
    "Household Cleaning": "CLN",
    "Laundry": "LDY",
    "Paper & Disposables": "PPR",
    "Health & Wellbeing": "HLW",
    "Personal Care": "PSC",
    "Baby & Child": "BBY",
    "Pet Supplies": "PET",
    "Seasonal & Gifting": "SEA",
}

# Product name parts per category: (brand-ish prefixes, nouns, variants).
NAME_PARTS = {
    "Fresh Produce": (
        ["Marsh Lane", "Orchard Row", "Green Acre", "Fieldgate"],
        [
            "Apples",
            "Bananas",
            "Tomatoes",
            "Potatoes",
            "Carrots",
            "Salad Bag",
            "Peppers",
            "Onions",
            "Mushrooms",
            "Berries",
        ],
        ["Loose", "Pack of 6", "Family Pack", "Class I", "Organic"],
    ),
    "Bakery": (
        ["Stonemill", "Old Harbour", "Baker's Row"],
        [
            "White Loaf",
            "Wholemeal Loaf",
            "Sourdough",
            "Bagels",
            "Croissants",
            "Muffins",
            "Baguette",
            "Crumpets",
        ],
        ["800g", "6 Pack", "4 Pack", "Sliced", "Thick Cut"],
    ),
    "Dairy & Eggs": (
        ["Fern Valley", "Coldbrook", "Hillfoot"],
        [
            "Whole Milk",
            "Semi-Skimmed Milk",
            "Cheddar",
            "Butter",
            "Yoghurt",
            "Free Range Eggs",
            "Double Cream",
            "Mozzarella",
        ],
        # Form-neutral: this category mixes litres, grams and boxes, and a
        # cross product of nouns and units produces "Butter 2L".
        ["Standard", "Large", "Family Pack", "Twin Pack", "Organic"],
    ),
    "Meat & Fish": (
        ["Wold Farm", "Harbourside", "Longacre"],
        [
            "Chicken Breast",
            "Beef Mince",
            "Pork Sausages",
            "Salmon Fillet",
            "Bacon",
            "Lamb Chops",
            "Cod Fillet",
            "Turkey Slices",
        ],
        ["400g", "500g", "2 Pack", "Value Pack", "Smoked"],
    ),
    "Frozen Foods": (
        ["Northwind", "Frostgate", "Polar Row"],
        [
            "Garden Peas",
            "Oven Chips",
            "Fish Fingers",
            "Pizza",
            "Ice Cream",
            "Mixed Vegetables",
            "Yorkshire Puddings",
        ],
        ["Standard", "Family Size", "12 Pack", "Value Pack", "Sharing"],
    ),
    "Store Cupboard": (
        ["Pantry Hill", "Saltway", "Millstone"],
        [
            "Pasta",
            "Basmati Rice",
            "Chopped Tomatoes",
            "Olive Oil",
            "Baked Beans",
            "Tuna Chunks",
            "Plain Flour",
            "Stock Cubes",
        ],
        ["Standard", "Large", "4 Pack", "Value Pack", "Multipack"],
    ),
    "Snacks & Confectionery": (
        ["Crestwood", "Bramble & Co", "Tin Box"],
        [
            "Crisps",
            "Milk Chocolate",
            "Dark Chocolate",
            "Salted Nuts",
            "Biscuits",
            "Popcorn",
            "Cereal Bars",
            "Wine Gums",
        ],
        ["Sharing Bag", "6 Pack", "Multipack", "100g", "200g"],
    ),
    "Soft Drinks": (
        ["Clearspring", "Fizzworks", "Bright Hollow"],
        [
            "Cola",
            "Lemonade",
            "Orange Juice",
            "Sparkling Water",
            "Still Water",
            "Energy Drink",
            "Iced Tea",
            "Ginger Beer",
        ],
        ["330ml", "1L", "2L", "6 Pack", "12 Pack"],
    ),
    "Hot Drinks": (
        ["Kiln Street", "Roastworks", "Copperpot"],
        [
            "Ground Coffee",
            "Instant Coffee",
            "Breakfast Tea",
            "Green Tea",
            "Hot Chocolate",
            "Coffee Pods",
            "Herbal Infusion",
        ],
        ["Standard", "Large", "Refill Pack", "Decaf", "Rich Roast"],
    ),
    "Beer, Wine & Spirits": (
        ["Anvil Brook", "Cask & Quay", "Southfield"],
        [
            "Lager",
            "Pale Ale",
            "Red Wine",
            "White Wine",
            "Cider",
            "Gin",
            "Whisky",
            "Prosecco",
        ],
        ["500ml", "750ml", "4 Pack", "70cl", "Case of 6"],
    ),
    "Household Cleaning": (
        ["Brightwell", "Keenedge", "Larkspur"],
        [
            "Washing-Up Liquid",
            "Surface Spray",
            "Bleach",
            "Floor Cleaner",
            "Glass Cleaner",
            "Bin Liners",
            "Sponges",
        ],
        ["Standard", "Large", "Refill", "Twin Pack", "Value Pack"],
    ),
    "Laundry": (
        ["Whitlow", "Softline", "Ashgrove"],
        [
            "Washing Powder",
            "Laundry Liquid",
            "Fabric Softener",
            "Stain Remover",
            "Colour Catchers",
            "Dryer Sheets",
        ],
        ["25 Wash", "40 Wash", "Large", "Twin Pack"],
    ),
    "Paper & Disposables": (
        ["Fold & Co", "Nettlebed", "Quiller"],
        [
            "Kitchen Roll",
            "Toilet Tissue",
            "Facial Tissues",
            "Foil",
            "Cling Film",
            "Freezer Bags",
            "Baking Parchment",
        ],
        ["4 Roll", "9 Roll", "2 Pack", "30m", "50 Bags"],
    ),
    "Health & Wellbeing": (
        ["Wellspring", "Thornhill", "Beacon Lane"],
        [
            "Paracetamol",
            "Ibuprofen",
            "Multivitamins",
            "Vitamin D",
            "Plasters",
            "Throat Lozenges",
            "Antacid Tablets",
        ],
        ["16 Tablets", "32 Tablets", "60 Capsules", "20 Pack"],
    ),
    "Personal Care": (
        ["Merrow", "Silverbirch", "Duneside"],
        [
            "Shampoo",
            "Conditioner",
            "Shower Gel",
            "Toothpaste",
            "Deodorant",
            "Hand Wash",
            "Razor Blades",
            "Moisturiser",
        ],
        ["250ml", "400ml", "75ml", "4 Pack", "Twin Pack"],
    ),
    "Baby & Child": (
        ["Little Harbour", "Puddleduck", "Wren & Fox"],
        [
            "Nappies",
            "Baby Wipes",
            "Infant Formula",
            "Baby Food Pouch",
            "Nappy Cream",
            "Bath Wash",
        ],
        ["Standard", "Large", "Multipack", "Sensitive", "Value Pack"],
    ),
    "Pet Supplies": (
        ["Redcollar", "Barnfield", "Two Paws"],
        ["Dog Food", "Cat Food", "Cat Litter", "Dog Treats", "Bird Seed", "Puppy Food"],
        ["Standard", "Large", "12 Pack", "Multipack", "Value Pack"],
    ),
    "Seasonal & Gifting": (
        ["Winterlane", "Gilded Pine", "Marchmont"],
        [
            "Gift Wrap",
            "Greeting Cards",
            "Candles",
            "Chocolate Box",
            "Crackers",
            "Fairy Lights",
            "Gift Bags",
        ],
        ["Pack of 3", "Single", "Large", "Set of 12", "Assorted"],
    ),
}

SUPPLIER_DEFS = [
    ("SUP-01", "Ashcombe Wholesale", ("Fresh Produce", "Bakery")),
    ("SUP-02", "Pennine Fresh Foods", ("Fresh Produce", "Meat & Fish")),
    ("SUP-03", "Calder Dairy Group", ("Dairy & Eggs",)),
    ("SUP-04", "Northgate Frozen Ltd", ("Frozen Foods",)),
    ("SUP-05", "Blackwater Provisions", ("Store Cupboard", "Snacks & Confectionery")),
    ("SUP-06", "Verity Beverages", ("Soft Drinks", "Hot Drinks")),
    ("SUP-07", "Harrowgate Wine & Spirits", ("Beer, Wine & Spirits",)),
    ("SUP-08", "Meridian Household", ("Household Cleaning", "Laundry")),
    ("SUP-09", "Fenwick Paper Co", ("Paper & Disposables",)),
    ("SUP-10", "Loxley Health Supply", ("Health & Wellbeing", "Personal Care")),
    ("SUP-11", "Bramford Baby & Pet", ("Baby & Child", "Pet Supplies")),
    ("SUP-12", "Kestrel Seasonal Goods", ("Seasonal & Gifting",)),
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
            raw_price = math.exp(rng.gauss(0.55, 0.62))
            price = money(max(Decimal("0.45"), money(raw_price)))
            pence = rng.choice([Decimal("0.99"), Decimal("0.49"), Decimal("0.95")])
            price = money(Decimal(int(price)) + pence)

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
            str(money(srng.choice([150, 200, 250, 400]))),
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
            str(money(srng.choice([200, 250, 300, 500]))),
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


def build_day_factors(window_start: date, window_end: date) -> dict[date, float]:
    """Holiday collapse plus the ramp of trade in the days before it."""
    factors: dict[date, float] = {}
    for holiday, name, factor in HOLIDAY_DEFS:
        factors[holiday] = factor
        ramp = CHRISTMAS_RAMP if "Christmas" in name else PRE_HOLIDAY_RAMP
        for offset, multiplier in ramp.items():
            day = holiday - timedelta(days=offset)
            if day in factors and factors[day] < 1.0:
                continue
            factors[day] = max(factors.get(day, 1.0), multiplier)
    return {d: f for d, f in factors.items() if window_start <= d <= window_end}


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
    """Weekday shape per category. Monday index 0, Sunday index 6."""
    base = [0.85, 0.88, 0.94, 1.02, 1.22, 1.00, 1.00]
    table: dict[int, list[float]] = {}
    for index, cat in enumerate(CATEGORY_DEFS, start=1):
        row = list(base)
        row[5] = cat.weekend_uplift
        row[6] = 1.0 + (cat.weekend_uplift - 1.0) * 0.72
        table[index] = row
    return table


# ─────────────────────────────────────────────────────────────────────────────
# Simulation
# ─────────────────────────────────────────────────────────────────────────────


def simulate(csvs: CsvSet, spec: SizeSpec) -> dict[str, object]:
    window_end = DATA_END_DATE
    window_start = window_end - timedelta(days=spec.days - 1)

    category_ids = build_categories(csvs)
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
    day_factors = build_day_factors(window_start, window_end)
    dates = [window_start + timedelta(days=i) for i in range(spec.days)]
    trend = [1.0 + 0.12 * (i / max(1, spec.days - 1)) for i in range(spec.days)]

    by_id = {p.product_id: p for p in products}
    tax_exempt = {
        p.product_id: (p.department in TAX_EXEMPT_DEPARTMENTS) for p in products
    }

    sale_id = 0
    sale_line_id = 0
    movement_id = 0
    po_id = 0
    po_line_id = 0

    for store in stores:
        srng = substream("store-ops", store.store_id)
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

            if day_factor <= 0.0:
                continue  # closed

            # Demand, clamped by stock.
            sold_today: list[tuple[int, int, int | None, Decimal]] = []
            for product in products:
                pid = product.product_id
                lam = (
                    product.base_rate
                    * store.factor
                    * seasonality[product.category_id][doy]
                    * dow_factors[product.category_id][weekday]
                    * trend_factor
                    * day_factor
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
                    tax = (
                        Decimal("0.00") if tax_exempt[pid] else money(gross * TAX_RATE)
                    )
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
                    tax = (
                        Decimal("0.00") if tax_exempt[pid] else money(gross * TAX_RATE)
                    )
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
