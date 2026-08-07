<!-- Hand-written. Nothing generates this file.

     schema.md next door describes what the columns ARE. This describes what
     they MEAN, what people asking questions actually want, and where the
     honest-looking wrong answers are. ADR-0001 is the reasoning: on a schema
     this size, the context document is what moves accuracy, not the schema
     dump. When a query comes back plausible and wrong, the fix usually
     belongs here rather than in the prompt. -->

# The business

A grocery retail chain in Maharashtra, India, trading as three stores:

| Store | Location | Notes |
|---|---|---|
| ST-01 | Kothrud, Pune | The reference store. Mid-sized. |
| ST-02 | Gangapur Road, Nashik | The smallest — about 72% of Pune's revenue. |
| ST-03 | Dharampeth, Nagpur | The largest — about 136% of Pune's revenue. |

Around 600 active SKUs across 18 categories, from staples (atta, rice, dal)
through fresh produce, dairy, packaged foods, household and personal care, to a
small Pooja & Festive range. Twelve suppliers, each covering one or two
categories, each with one preferred relationship per product.

There is no separate warehouse. Stock is held at the store, ordered from the
supplier on a per-store purchase order, and delivered against a lead time.

Currency is **Indian rupees (INR)**. Prices in the database are plain numbers —
no symbol, no formatting.

---

# Dates: "today" is not today

**The data ends on a fixed date, and that date is what "now" means.** The
system supplies it as `as_of_date`. Every relative period resolves against it:

- **"last month" is the calendar month before the month containing
  `as_of_date`.** `as_of_date` happens to be the last day of a month, so the
  month containing it is complete — but "last month" still means the one
  before it. Call the current one "this month" or name it.
- "the last 30 days" is the 30 days ending on `as_of_date`, inclusive
- "this year" is the calendar year containing `as_of_date`
- "year to date" runs from 1 January of that year to `as_of_date`

**Never use `current_date`, `now()`, `CURRENT_TIMESTAMP` or `CURRENT_DATE` in a
query.** Real wall-clock time has moved past the end of the data, so a query
anchored to it returns zero rows — silently, with no error, looking exactly
like "we sold nothing".

## `business_date`, not `sold_at`

Every sales table carries both:

- **`business_date`** — the store's trading day. **Use this for every
  aggregation**: daily, weekly, monthly, year-on-year, "last month", "since
  Diwali".
- **`sold_at`** — the exact transaction timestamp, with timezone. Use it only
  when the *time of day* is the question ("when is our evening rush?").

They are not interchangeable. `sold_at::date` is the UTC date and will disagree
with `business_date` for late-evening transactions. Aggregating on it produces
numbers that are quietly a little wrong — the worst kind.

---

# Money and GST

- **`sales.subtotal`** — takings net of tax.
- **`sales.tax_total`** — GST charged.
- **`sales.total`** — `subtotal + tax_total`. What the customer actually paid.

**"Revenue", "sales" and "turnover" mean `subtotal`** — net of tax. Only use
`total` when the question is about cash collected, banking, or what a customer
paid.

## GST changed on 22 September 2025, inside this data

This is the single most important thing to know about tax here.

GST is charged **per category**. It is also charged **per date**: the 56th GST
Council meeting restructured the slabs with effect from **22 September 2025**,
which falls in the middle of the sales history. The 12% and 28% slabs were
withdrawn. Most 12% items moved to 5%, most 28% items moved to 18%, and luxury
and sin goods — aerated beverages among them — moved to a new 40% slab.

| | Slabs in use |
|---|---|
| Before 22 Sep 2025 | 0 / 5 / 12 / 18 / 28 |
| From 22 Sep 2025 | 0 / 5 / 18 / 40 |

The categories that actually moved:

| Category | Before | From 22 Sep 2025 |
|---|---|---|
| Soft Drinks & Juices | 28% | **40%** |
| Dairy & Paneer, Snacks & Namkeen, Ready to Cook | 12% | 5% |
| Personal Care, Health & Wellness, Baby Care, Pooja & Festive | 12% | 5% |

Everything else kept its rate. The full history is in the **`gst_rates`**
table, one row per category per rate period, with the same shape as supplier
terms: `effective_from` inclusive, `effective_to` exclusive, NULL meaning in
force.

**For the rate that applied to a past sale, look it up by that sale's date:**

    JOIN gst_rates g
      ON g.category_id = p.category_id
     AND g.valid_period @> s.business_date

**For the rate today**, use `v_gst_rate_current`.

`rate_pct` is percentage points — 18 means 18%. Divide by 100 before
multiplying.

### The trap this creates

**Any question about tax over a period spanning 22 September 2025 has two
answers, not one.** Averaging across the boundary produces a number that was
never the rate:

- Effective rate July to 21 September 2025: **8.23%**
- Effective rate 22 September to November 2025: **6.73%**
- Average across the whole of July–November: **7.50%** — a figure that was the
  rate on no day at all

It executes cleanly and looks entirely reasonable. September itself is a blend
of both regimes (7.67%), because the reform lands mid-month — so even "the rate
in September" needs splitting.

So: **if a question about tax, or about a total that includes tax, spans
22 September 2025, split the period at that date and report both — or say which
side you are reporting.** Do not return a single blended rate for a span that
crosses it. The same applies to "has our tax bill gone up" questions: the rate
change is usually the entire explanation and should be named.

Never compute tax by multiplying a total by one rate. Sum `tax_total`, which
was calculated per line at the rate in force on the day of that sale.

**Margin** is `net_revenue - cogs`, both available per product per day in
`daily_product_sales`. Cost is frozen on the sale line at the moment of sale
(`sale_lines.unit_cost`), so historical margin is correct. Do **not** join to
`supplier_prices` to work out what something cost last year — that gives
today's cost.

---

# Counting units: quantity is signed

`sale_lines.quantity` is **negative on a return**. A refund is a separate
`sales` row with `sale_type = 'return'` whose lines carry negative quantities.

This means **`SUM(sale_lines.quantity)` is NET units, not gross.** It is a
perfectly reasonable-looking expression that answers a different question from
the one usually asked.

`daily_product_sales` names the three concepts separately, and using it is
almost always better than summing raw lines:

| Column | Meaning |
|---|---|
| `units_sold` | Gross units out. Positive lines only. |
| `return_units` | Units handed back, as a positive number. |
| `net_units` | `units_sold - return_units`. |
| `net_revenue` | Takings, **net of returns and net of GST**. |
| `cogs` | Cost of goods sold, net of returns. |

**Default to `net_units`** for "how much did we sell". Use `units_sold` only
when the question is explicitly about gross movement, and `return_units` when
it is about refunds. If someone asks "what are we returning most of", that is
`return_units`, not a negative `net_units`.

---

# Stock: three different questions

These get conflated constantly, and they have different answers:

**1. Out of stock — `on_hand = 0`.** We have none. The sale is already lost.
This is a "what went wrong" question.

**2. Low stock — `on_hand > 0` and few days of cover left.** We still have
some, but not for long. This is a "what do I act on today" question, and it is
almost always what "what are we low on", "what's running out", "what should I
worry about" mean.

**3. Below reorder point — `on_hand <= reorder_point`.** The store's own
restocking policy says to place an order. This is the purchasing question.

They overlap but are not the same, and a product can be in one and not another.
**If a question is about running out or running low, exclude `on_hand = 0`
unless the question is specifically about items already out of stock** — a list
of ten products all showing zero cover is not an answer to "what's running
low", it is an answer to a different question.

`days_of_cover` in `v_stock_status` is `on_hand / units_per_day`: how many days
the shelf will last at the current rate. Low means urgent. **`NULL` means the
product has not sold in 30 days**, which is a slow mover, not an emergency —
never sort NULLs to the top of an urgency list.

---

# Restocking

**"What should we reorder" means `on_hand <= reorder_point` by default.**
`reorder_point` is set per store per product, because a busy store needs a
higher floor than a quiet one.

If the question names an explicit number — "anything under 5 units" — that
number is an **override**: use `on_hand <= 5` and ignore the reorder point.

When drafting an order, the relevant facts are in `v_stock_status`:
`reorder_qty` (how many to order), `case_pack` and `min_order_qty` from the
supplier, `lead_time_days`, `current_unit_cost`, and `on_order_qty`.

**`on_order_qty` matters.** It is the quantity already on an open purchase
order and not yet received. A product below its reorder point with stock
already inbound usually does not need ordering again — check it before
proposing anything.

---

# Sales velocity, and why raw sales understate it

`v_product_velocity_30d` gives units per day over the 30 trading days ending at
the latest date in the data.

**It divides by the days the product was actually available, not by 30.** This
matters more than it sounds. Sales are capped by stock: if something sold out
on day 3, it recorded no sales on days 4 through 30 — not because nobody wanted
it, but because there was none. Dividing those zero days into the average
punishes exactly the products that sell fastest.

`stockout_days` records which days a product was unavailable while customers
were still asking. `available_days_30d` is the corrected denominator.

**So: "what sells fastest" should use `units_per_day` from the velocity view,
not `SUM(quantity) / 30` computed by hand.** The hand-rolled version is
systematically wrong in the same direction for the products the question is
usually about.

Two more distortions worth knowing:

- **Promotions inflate a product's numbers while they run.** `sale_lines`
  carries `promotion_id` when a line was discounted. A "best seller" list over
  a period containing a promotion is partly a list of what was on offer.
- **The festive season swamps year-on-year comparisons** (below).

---

# Suppliers, terms and prices change over time

Supplier terms and supplier prices are **historical records, not current
values**. Each row covers a date range: `effective_from` inclusive,
`effective_to` exclusive, and `effective_to IS NULL` means still in force.

**For any question about a specific date — "what were the terms in March",
"what were we paying before the renegotiation" — use the generated range
column:**

    WHERE valid_period @> DATE '2025-03-01'

That is a single containment test and it cannot get the boundary wrong.
Comparing `effective_from` and `effective_to` by hand invites an off-by-one on
the changeover day, which returns the wrong contract while looking correct.

**For the current position, use the views**: `v_supplier_terms_current` and
`v_supplier_price_current`. They are the rows with no end date.

Three things that follow:

- Every supplier has been renegotiated once, so each has a superseded period
  and a current one, linked by `supersedes_id`.
- **A supplier absent from a point-in-time query has no terms in force on that
  date. That is not the same as the supplier not existing.** If a question
  lands in a gap, say so — "no terms were in force on that date" is a real,
  correct answer and is different from "supplier not found".
- `lead_time_days` on the terms is what the supplier *contracted* to. What they
  actually deliver is `purchase_orders.received_on - ordered_on`. Asking
  whether a supplier hits their lead time is a real and different question.

---

# Seasonality and the festive season

Demand is strongly seasonal, and the festive season is the single largest
signal in the data.

**The festival calendar is in the database — use it, do not hardcode dates.**
The `festivals` table has one row per festival occurrence, with `festival_date`
and, more usefully, `ramp_start` and `ramp_end` bounding the window over which
trade is actually affected:

    JOIN festivals f
      ON d.business_date BETWEEN f.ramp_start AND f.ramp_end
    WHERE f.name = 'Diwali'

**"During a festival" almost always means the window, not the day.** Trade
builds for weeks beforehand and frequently *drops* on the festival itself, so
filtering to `festival_date` answers a different and much less useful question.

**Navratri → Dussehra → Dhanteras → Diwali is one continuous six-week build,
not four separate spikes.** In 2025 it runs from late September, peaks the day
before Dhanteras (18 October), and drops into a marked slump for about a
fortnight after Diwali. At its peak, daily takings run well over double the
baseline. Their ramp windows overlap in the table, which is what that
continuity looks like in the data.

Consequences for queries:

- **A month-on-month comparison spanning October is mostly measuring Diwali.**
  So is a comparison of the fortnight after Diwali against anything.
- **Pooja & Festive, Sweets & Chocolates, and Edible Oils & Ghee move hardest**
  in the season. Staples barely move at all.
- **Ganesh Chaturthi is a large regional event** — bigger in Pune than in
  Nagpur, because this is a Maharashtra chain. `festivals.is_regional` flags
  these. A store comparison across one of them is partly measuring geography,
  so normalise against each store's own baseline rather than comparing raw
  totals.
- Holi is quiet on the day itself and busy in the week before it.
- Other seasonality: soft drinks peak hard in the May–June summer, tea and
  coffee peak in winter, fresh produce peaks with the mango season.

### What the window can and cannot support

The data runs from January 2025 to the end of June 2026 — about 18 months. That
has a hard consequence for festival comparisons:

- **There is exactly one Diwali in the data** (Dhanteras 18 October 2025).
  Dhanteras 2026 falls on 6 November, past the end of the data. **A
  Diwali-over-Diwali comparison is therefore impossible**, and so is any
  "compared to last Diwali", "year-on-year festive season", or "how did this
  Diwali do against last" question.
- **Holi and Gudi Padwa appear twice** — March 2025 and March 2026 — so
  spring-festival year-on-year comparisons work normally.

If a question asks for a comparison the window cannot support, **say so rather
than producing one**. Constructing a Diwali-over-Diwali figure from a single
Diwali means either silently comparing it to a non-festive period or inventing
a baseline, and both produce a confident number with nothing behind it. Where
the SQL interface is concerned, that is the
`-- INSUFFICIENT SCHEMA: <what is missing>` path, and using it is the correct
answer, not a failure to answer.

---

# Vocabulary

What people mean when they ask:

| They say | They mean |
|---|---|
| revenue, sales, turnover, takings | `subtotal` / `net_revenue` — net of GST |
| units, volume, how many we sold | `net_units` |
| fast-moving, sells fastest, top seller | high `units_per_day`, or `net_units` over a period |
| running low, running out, low on | `on_hand > 0` and low `days_of_cover` |
| out of stock | `on_hand = 0` |
| needs reordering, should we order | `on_hand <= reorder_point` |
| cover, days of stock, how long will it last | `days_of_cover` |
| margin | `net_revenue - cogs` |
| what we pay for it | `supplier_prices.unit_cost` — not `list_price` |
| what we sell it for | `products.list_price`, or `sale_lines.unit_price` if a promotion applied |
| lead time | contracted `lead_time_days`; actual delivery is a different question |
| a line, a SKU | one row of `products` |

## Words that need a number behind them

A manager says "fast-moving" and does not say how fast. These are the working
definitions — use them when the question does not give its own, and **say which
one you used** so the answer can be checked.

| Phrase | Means | Why that number |
|---|---|---|
| fast-moving, fast-selling | `units_per_day > 1` | The top quartile of the range; the median line sells 0.47/day |
| very fast-moving | `units_per_day > 2` | Roughly the top tenth |
| slow-moving, barely moving | `units_per_day < 0.2` | The bottom of the range, well below the median |
| a top seller | the top 10 by units unless a number is given | "More than 1,000 units" would be 264 of 600 products — a threshold that names nearly half the catalogue names nothing |
| about to run out | fewer than 7 days of cover | A week is the natural planning horizon and shorter than every supplier's lead time |
| running low | at or below the reorder point | The store's own policy, per store |

If a question gives its own number — "under 5 units", "more than 2 a day" — that
number wins.

## Two defaults worth stating

**Grain: stock questions are per store.** Stock is held at a store, reorder
points are set per store, and shrinkage happens at a store. A chain-wide total
for "what is our stock worth" or "what is going missing" is almost never what
was meant — report per store unless the question asks to combine them.

**Period: when no period is named, use all the history there is**, and make
that visible in the column naming so nobody reads a lifetime figure as a recent
one. Do not silently pick a recent window; a number whose period is invisible
is the kind that gets quoted out of context.

---

# The four views, and when to reach for each

Prefer these over reconstructing their logic. They encode definitions that are
easy to get subtly wrong.

- **`v_stock_status`** — one row per store per product: stock, reorder policy,
  velocity, days of cover, preferred supplier, terms, cost, quantity on order.
  The default starting point for anything about stock or restocking.
- **`v_product_velocity_30d`** — how fast each product sells, with the stockout
  correction applied.
- **`v_supplier_terms_current`** / **`v_supplier_price_current`** — what is in
  force now. For any other date, query the base table with `valid_period`.

`daily_product_sales` is a pre-aggregated rollup of `sale_lines` per store, per
product, per day. Use it for anything time-series; it is much smaller than the
line table and it names gross, returns and net separately so they cannot be
confused.

---

# Query hygiene

- **Every `ORDER BY` needs a tiebreak column.** Row order is not guaranteed
  otherwise, and two runs of the same query can return different rows in the
  same positions. End every sort with something unique — `sku` or an id — even
  when the primary sort looks sufficient.
- **Filter by `store_id` when a store is named.** When none is named, aggregate
  across all three and make that obvious in the column naming. Do not silently
  pick one store.
- **Prefer explicit column lists to `SELECT *`**, so a result set is
  self-describing.
- Products have `is_active`; discontinued lines are still in the catalogue.
  Exclude inactive products unless the question is historical.

---

# Where the honest-looking wrong answers are

A short list of what to double-check, in rough order of how often it bites:

1. `current_date` anywhere — returns nothing, looks like no sales.
2. **A single tax rate over a period spanning 22 September 2025.** The rates
   changed; a blended figure was true of no period.
3. `SUM(quantity)` when the question wanted gross units.
4. Aggregating on `sold_at` instead of `business_date`.
5. Dividing sales by 30 instead of by available days for velocity.
6. Listing `on_hand = 0` products as the answer to "what's running low".
7. Applying one GST rate to a mixed basket.
8. Comparing periods across the festive season without saying so.
9. Joining to current supplier prices — or `v_gst_rate_current` — for a
   historical figure.
10. An `ORDER BY` with no tiebreak.
11. Treating "no terms in force on that date" as "supplier not found".
12. **Fabricating a year-on-year comparison that the data cannot support.**
    There is only one Diwali in the window (October 2025); Dhanteras 2026 falls
    past the end of the data. A Diwali-over-Diwali comparison is impossible and
    the honest answer says so. Holi and Gudi Padwa appear twice, so spring
    festival comparisons are fine.
