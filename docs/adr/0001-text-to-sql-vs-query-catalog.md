# ADR-0001: Text-to-SQL, with measured thresholds for switching to a query catalog

Date: 2026-08-05
Status: Accepted — outcome deliberately open, settled by Phase 1 measurement

## Context

The first design review recommended replacing open-ended text-to-SQL with a
curated catalog of ~25–40 parameterised queries. A later audit of the numbers
behind that recommendation weakened it substantially, and the audit is the
reasoning here — not a footnote.

**What the audit found.** The Spider 2.0-Lite figures cited in support ("69.65%
top performer", "30–36%") came from a semantic-layer vendor's blog and were a
misreading of a fragmentary snippet. Worse, they were applied to the wrong
difficulty regime: Spider 2.0-Lite is 547 problems across 150+ databases
averaging ~800 columns, with multiple SQL dialects. This project's schema is
~15 tables. The better analogue is classic Spider, where DAIL-SQL with GPT-4
reached 86.2% execution accuracy in 2023. Reported Spider 2.0-Lite scores have
also moved fast — roughly 30% in early 2025, 60%+ with recent frontier models,
71.84 posted on the leaderboard in April 2026 — so any single snapshot is stale
on arrival.

The dbt Labs semantic-layer benchmark was also load-bearing in the original
argument, and dbt Labs sells a semantic layer. The corroborating source (Atlan)
sells a metadata catalog. The one independent, peer-reviewed data point cuts
differently: a JAMIA Open study found GPT-4 at 8.3% accuracy with schema alone
versus 78.3% with a business-context document, and narrowing the schema *without*
that document only reduced failure to 50%. **The context document was doing the
work, not deterministic query generation.**

## Decision

Use generated SQL against a documented schema. Write the business-context
document and schema documentation *before* any prompt engineering — it is the
highest-return work available. Measure on this schema with a 30–50 question eval
set, each question run 3x, and switch to a query catalog only if measurement
demands it.

**Build the catalog if any threshold fires:**

1. **Silent-wrong rate > 5%** — executes cleanly, returns plausible wrong numbers.
   Tightest threshold and overrides the others, because it is undetectable live.
   Measure by comparing result sets, not by whether the query ran.
2. **Execution accuracy < 85%** — catalog maintenance becomes cheaper than
   generation debugging.
3. **Cross-run variance > 10%** — non-determinism is fatal for a repeated demo.
4. **Median attempts-to-correct > 1.3** — a retry loop is a quota problem stacked
   on an accuracy problem.

### The measurement has to survive its own convenience layer

Phase 0 shipped a small set of views — `v_stock_status`,
`v_product_velocity_30d`, `v_supplier_terms_current`, `v_supplier_price_current`
— that encode the metric definitions a question would otherwise have to
reconstruct. That is legitimate schema design and it is the same bet this ADR
already makes: context does the work. But it moves the thresholds.

A question that a view answers is close to `SELECT * FROM view WHERE ... ORDER
BY ...`. If enough of the eval set looks like that, threshold 2 measures the
view rather than the model, and an inflated number keeps generated SQL alive
when the measurement should have killed it.

**So every question in `evals/sql/questions.jsonl` carries a `view_covered`
boolean, and the results block reports execution accuracy three ways: overall,
view-covered, and not-view-covered.** The threshold is evaluated against the
**not-view-covered** number, because that is the one describing what the model
can actually do. One extra field in the JSONL, and it is the difference between
a measurement and a flattering one.

**Pre-committed hybrid, regardless of results:** hand-write query templates for
the 10–15 questions the demo actually asks. Generated SQL handles the tail. The
demo path is deterministic even if general accuracy is excellent. This is not
hedging — it is declining to gamble on live inference for the thing being judged.

## Alternative rejected

A full curated query catalog from the start.

## Why

The evidence for it was drawn from a much harder problem than this one, and its
strongest sources had a commercial stake in the conclusion. A catalog also
carries a maintenance tax — every new question is a code change — which
reproduces exactly the rigidity this project set out to fix. And if the thesis is
"natural language over business data", a fixed catalog is a weaker demonstration
of it.

## What would flip it

Any of the four thresholds firing in Phase 1 measurement. Nothing else — not
argument, not a new benchmark. When the measurement lands, update this ADR rather
than writing a new one; a reader should find the question and its resolution in
one place.