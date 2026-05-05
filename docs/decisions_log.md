# Decisions Log

A running record of design decisions made during the Zeal Pricing Tool project, with rationale. Append-only — when a decision is revisited, add a new entry rather than editing the old one.

Format: date, decision, alternatives considered, rationale.

---

## 2026-05-01 — v1 is a faithful port of the spreadsheet, not an improved algorithm

**Alternatives:** Improved port (fold in better signal processing, dynamic tiers, etc. from day one).

**Rationale:** Operator has full pricing authority and decades of pattern recognition. He needs to trust the baseline before trusting upgrades. Faithful port lets us validate cell-for-cell against the spreadsheet, separating "is the new system correct?" from "are the operator's instincts right?" Improvements tracked in pricing_algorithm.md §10.

---

## 2026-05-01 — Per-merchant configuration, not per-tier

**Alternatives:** (a) clean tier-based logic; (b) hybrid (tier with per-merchant overrides).

**Rationale:** Spreadsheet analysis showed merchants within the same tier reference different margin rows. Whether deliberate or drift is unknown without operator input. Per-merchant config preserves whatever the operator intended without forcing a premature decision. Tier becomes a descriptive label, used to suggest defaults for new merchants.

---

## 2026-05-01 — Decision-support tool, not automated pricing

**Alternatives:** Automated pricing with operator override option.

**Rationale:** Operator wants to retain full pricing authority. Auto-publishing would change the product from "tool that helps me" to "system I have to babysit," which is the opposite of what's wanted.

---

## 2026-05-01 — Standalone tool, not integrated with the website rebuild

**Alternatives:** Wait for or coordinate with the Zeal Cards website rebuild.

**Rationale:** Website rebuild timeline is uncertain (>few months). Building standalone unblocks immediate value. If the tool proves useful, integration with the rebuilt site is a small future project.

---

## 2026-05-01 — Stack: Python 3.12 + FastAPI + SQLite + HTMX + Tailwind

**Alternatives:** Python+Django, TypeScript+Next.js, Python+React.

**Rationale:** Best ecosystem for the data-handling work (eBay API, scraping, analysis). FastAPI/HTMX combination gives server-rendered HTML with light interactivity — right complexity for a one-user dashboard. SQLite is plenty for one user × ~300 merchants. Tailwind for fast styling without a design system overhead.

---

## 2026-05-01 — Local-only on operator's Windows machine, no VPS

**Alternatives:** Small VPS (~$5/mo); hybrid local + GitHub Actions for scheduled refresh.

**Rationale:** Operator works from a home office, not multiple locations. No need for "anywhere access." Local-only avoids hosting cost, avoids server management, keeps pricing data on operator's machine. Trade-off: requires laptop to be on for scheduled refresh, but Windows Task Scheduler runs on wake. Migration to VPS later is a half-day project if circumstances change.

---

## 2026-05-01 — Scheduled refresh via Windows Task Scheduler, no Windows Service for web app

**Alternatives:** Run web app as Windows Service (via NSSM); skip scheduling and refresh on demand only.

**Rationale:** Task Scheduler is built into Windows, no extra dependency. Web app doesn't need to be running 24/7 — only the scheduled refresh does, and that runs independently. Desktop shortcut launches the web app on demand. Simpler than a service, easier to debug. Revisit if operator finds launching annoying.

---

## 2026-05-01 — eBay Browse API, not scraping eBay

**Alternatives:** Scraping eBay's sold-listings pages.

**Rationale:** Official API is free, structured, survives layout changes. eBay actively blocks scrapers. Application takes ~1 week, low effort. (Scraping competitors like CardCash/Raise is acceptable in v2 since it's a small operation, but eBay specifically is too high-volume and well-defended to be worth scraping.)

---

## Template for future entries

```
## YYYY-MM-DD — [decision in one line]

**Alternatives:** [what else was considered]

**Rationale:** [why this choice; trade-offs accepted]
```
## 2026-05-02 — Merchant ID scheme: merchant[_subtype][_qualifier] slug

**Alternatives:** Numeric IDs; UUIDs; hash of display name.

**Rationale:** Slugs are stable (don't change if display name is reworded), readable in URLs and logs, sortable (variants of one merchant cluster together), and the subtype segment (`merch_credit`, `estore_credit`) is reusable for similar variants of other merchants. Lowercase ASCII with underscore separators. Variants disambiguated with descriptive qualifiers (`home_depot`, `home_depot_merch_credit_no_id`, etc.). See docs/spreadsheet_recon.md §6.

## 2026-05-02 — Per-channel ineligibility flags, not just electronic

**Alternatives:** (a) keep single `electronic_eligible` flag and exclude rows with `"No"` in C or E from baseline; (b) separate flags per channel.

**Rationale:** The spreadsheet's `"No"` convention applies uniformly to columns C (in-mail), D (electronic), and E (in-store). Eight merch-credit variants and one eStore Credit row use combinations across all three. Treating these as exclusions would lose real merchants from the baseline. Three flags (`in_store_eligible`, `in_mail_eligible`, `electronic_eligible`) preserve the operator's intent. Engine guards each channel formula on its corresponding flag and returns `"No"` sentinel where ineligible. See spreadsheet_recon.md §8.1.

---

## 2026-05-02 — `online_sell_override` field for Pattern A merchants

**Alternatives:** (a) add `online_sell_override: float | None`; (b) treat Pattern A as a separate row class with its own computation path; (c) exclude these merchants from baseline and add manual entry in dashboard.

**Rationale:** Approximately 25 NC-tier merchants (rows 250–274, 294) have hardcoded `online_sell` because eBay has no useful sold-listing data for them. Their downstream formulas (in-mail, in-store, electronic) compute normally from this hardcoded value. Adding a single optional override field is the minimal change that preserves spreadsheet behavior without splitting the engine into multiple computation paths. The operator updates the value through the merchant config UI when local market conditions shift. See spreadsheet_recon.md §8.2 and §4.3.

---

## 2026-05-02 — `electronic_buy_override` field

**Alternatives:** (a) add `electronic_buy_override: float | None`; (b) exclude Home Depot eStore Credit (row 14) as a one-off curiosity.

**Rationale:** Currently used by exactly one merchant, but the override mechanism parallels `online_sell_override` and costs little to support. Future-proofs against more eStore-credit-style variants. The override path bypasses the `in_mail_buy` dependency in the electronic formula, which is necessary because eStore Credit has `in_mail_eligible = False`. See spreadsheet_recon.md §8.3.

---

## 2026-05-02 — `ebay_differential` stored as derived per-merchant value

**Alternatives:** (a) store the derived value (4.5% or 2.5%) as a per-merchant float, faithful to spreadsheet; (b) compute dynamically from global constants at engine call time, with a per-merchant `differential_variant` enum (`competitive` / `zen_nocomp`); (c) store both.

**Rationale:** The spreadsheet stores B23 (4.5%) and B24 (2.5%) as formulas (`=B2+B4-B6-B5` and `=B2+B4-B7-B5`), but at the merchant level the formulas only ever reference B23 or B24 — never the components directly. v1 stores the derived per-merchant value because that's a faithful port of the merchant-level data model and avoids introducing a new variant enum. The components (`online_sell_bonus_competitive` = 0.065, `online_sell_bonus_zen_nocomp` = 0.085) are added to global constants for reference and v2 use. v2 may switch to dynamic computation if it simplifies tier reassignment. See spreadsheet_recon.md §8.4.

---

## 2026-05-02 — `merch_credit_variant` flag detected by display-name substring match

**Alternatives:** (a) substring match on display name (`merch credit`, `merchandise credit`, `estore credit`, `rebate`); (b) explicit operator flag per merchant; (c) separate column in the spreadsheet (doesn't exist today).

**Rationale:** The spreadsheet has no dedicated column for variant flagging; the display name is the only signal. Eight rows match the four substrings cleanly with no false positives observed in the recon. Substring match is automatic during seeding, no operator data entry. The operator can override the flag through the merchant config UI if the rule produces a wrong answer in the future. See spreadsheet_recon.md §7.4.

---

## 2026-05-02 — Four spreadsheet rows excluded from baseline due to in-store bad-debt typo

**Rows:** 44 Southwest, 45 Speedway - Food and Merch, 46 Speedway - Fuel, 70 Family Dollar.

**Issue:** E (in-store) formulas reference InputsandMargins!$B$9 (in_mail_bad_debt = 0.02) where the canonical pattern is $B$8 (in_store_bad_debt = 0.048). Diff is exactly 0.028 in the in-store column. 4 rows out of 288 use B9; the other 284 use B8.

**Confirmed with operator:** typos, not deliberate. The four merchants do not have a different in-store fraud rate.

**Resolution:** documented baseline exclusions in `spreadsheet_recon.md` §10. Engine remains correct (uses in_store_bad_debt for in-store buys per spec §5.3). When merchant config is seeded into SQLite, these four rows are seeded with their *correct* margin/bad-debt values, not the spreadsheet's typo'd computation. The exclusion is from the baseline *test*, not from the production tool.

**Alternatives considered:** (a) add a per-merchant `in_store_bad_debt_override` field — rejected as unnecessary complexity for confirmed typos. (b) fix the spreadsheet — decided against, since the spreadsheet is the legacy artifact being replaced; fixing it adds confusion without value.

---

## 2026-05-02 — Five AVERAGE summary rows reclassified as section aggregates

**Rows:** 19 BREAD AND BUTTER, 60 TOP CARDS, 83 COVID WATCH LIST, 210 TAKE ONLINE, 276 LOCAL.

**Issue:** these rows have F/C/D/E columns containing AVERAGE() formulas over preceding sections (e.g. F19 = AVERAGE(F3:F18)). They are summary statistics the operator added for visibility, not merchants. The recon doc §4.5 only listed name-keyed dividers ("PHYSICAL ONLY", "Bankrupt", "Merchant"); these formula-keyed aggregates were missed.

**Resolution:** new row classification rule in the parser. Detect via "F-column formula starts with `=AVERAGE(`". Treat as section_divider (no merchant_id, no config, excluded from baseline). Recon doc §4.5 updated to cover both name-keyed and formula-keyed dividers.

**Alternatives considered:** create a new `section_aggregate` classification — rejected as gratuitous since downstream behavior is identical to existing dividers.

---

## 2026-05-02 — Row classifier uses F-column as the type signal, not B-column

**Rows affected (one row today, but the rule generalizes):** row 253 Biggby Coffee.

**Issue:** original classifier (recon §4.6) keyed on B-column numeric vs non-numeric. Row 253 has B=0.668 (numeric, looks like eBay data) but F=0.75 (hardcoded literal, not a formula). The C/D/E formulas reference F, so the spreadsheet's actual behavior is Pattern A (hardcoded online_sell), but the classifier called it "normal" and the engine then computed online_sell from B.

**Resolution:** classifier rule changes from "B-numeric → normal" to "F-is-formula → normal; F-is-literal-number → no_ebay_data_local; F-is-empty/error → bankrupt_broken". F-column is the source of truth for row type because it determines what the downstream channels actually consume.

**Alternatives considered:** keep B-keyed rule and add a special-case for row 253 — rejected as fragile (anyone who later updates B for a Pattern A merchant would silently flip it back to "normal").

---

## 2026-05-03 — Dashboard displays percentages, not dollar amounts

**Alternatives:** Display buy/sell prices as dollar amounts for a given face value (e.g. "buy at $0.92 per $1.00" → show "$92.00 for a $100 card").

**Rationale:** Operator confirmed during session 5 that percentages are the right unit for the dashboard. Percentages are already the internal representation (all values stored and computed as fractions of face value per CLAUDE.md), so no conversion layer is needed for v1. Dollar-amount display can be added at the display layer later if the operator changes his mind, without touching the engine. See pricing_algorithm.md Q6.

---

## 2026-05-04 — v1 scope expanded with four enhanced features and competitor data layer

**Alternatives:** (a) ship faithful port only, defer all enhancements to post-feedback work; (b) add only the four "strong-recommend" features (extended exclusions, risk flag, CSV export, formula breakdown); (c) add all eleven proposed scope revisions; (d) the chosen path: four strong-recommend features plus competitor data integration.

**Rationale:** Three pieces of project context shifted the calculus from a minimal-v1 framing toward a more ambitious one. First, no fixed deadline — v1 ships when it's ready to show the operator, not on a schedule. Second, the operator goal is to *improve* the existing workflow, not just port it; competitor pricing has always been part of his manual process (the original RFP references Cardpool and GiftCardZen) and "a more accurate pricing tool" is a stated objective. Third, the project is explicitly experimental and iterative — features that don't earn their keep can be removed cheaply, which lowers the bar for inclusion.

The four strong-recommend features (extended eBay exclusions, risk/watchlist flag, CSV export, formula breakdown) earn inclusion on operational grounds independent of timeline: extended exclusions are hygiene on a filter that's already specified; the risk flag prevents accidental acceptance of known-bad merchants; CSV export bridges the tool to the operator's downstream workflow; formula breakdown is the highest trust-yield feature in the proposal.

Competitor data is included on the strength of the operator's stated goal. Implementation is staged: schema and manual import path in v1's first build, CardCash scraper as the first automated source, Raise as the second, Cardpool and GiftCardGranny deferred to post-feedback work. This staging protects against the operational risk of shipping four scrapers simultaneously before any have been validated against operator judgment.

Six revisions deferred to post-feedback work: recency-weighted eBay average, override reason codes, drift-audit dashboard surfacing, full data-quality dashboard, partial-balance parsing, and additional competitor sources beyond CardCash/Raise. Each is a reasonable idea whose value is best assessed after the operator has used the tool.

---

## 2026-05-04 — Competitor data integration via Path A: per-merchant eBay weight, single float, applied to three channels

**Alternatives:** (a) Path A — operator-controlled blending weight per merchant, defaulting to 1.0 (eBay-only, matches spreadsheet); (b) Path B — system-opinionated default weight (e.g. 70/30 eBay/competitor for high-confidence merchants), operator-overridable; (c) competitor data displayed alongside eBay recommendation but never blended; (d) separate weights per channel rather than one weight per merchant.

**Rationale:** Path A preserves the spreadsheet-faithful baseline as the day-one default — every merchant starts at `ebay_weight = 1.0`, making v1 algorithmically equivalent to the spreadsheet until the operator chooses otherwise. This protects the validation property established by Phase 1's golden tests. The operator dials competitor weight up over time as competitor data accumulates and as he develops trust in the blended signal.

A single per-merchant weight rather than per-channel weights keeps the configuration surface small. If a specific channel needs different treatment, the operator can override the recommendation directly through the existing override flow — channel-level weights would be a config burden not yet justified by observed need.

System-opinionated defaults (Path B) were rejected for v1 on epistemic grounds: choosing 70/30 vs 50/50 requires knowing what "better" means, which the project doesn't yet have evidence for. Path B becomes a reasonable evolution if operator-tuned weights cluster around predictable values across merchants.

Competitor data informs three of the four channels: `online_sell`, `in_mail_buy`, and `electronic_buy`. The `in_store_buy` channel has no clean competitor analogue (no major competitor operates physical storefronts) and continues to compute from the eBay-derived value only. Confidence is computed independently per source; the blending weight is operator-set and does not auto-adjust based on confidence. Less automation, more operator control — the right default for a tool the operator should learn before it learns him.

---

## 2026-05-04 — Formula breakdown implemented engine-side, exposed via PriceRecommendation return type

**Alternatives:** (a) compute the breakdown in the dashboard template using merchant config and global constants; (b) extend the pricing engine to return a structured breakdown alongside the final price.

**Rationale:** Engine-side keeps the engine as the single source of truth for pricing logic. The breakdown is part of the engine's contract, verifiable by tests, and rendered by templates that are pure presentation. Template-side breakdown computation works but introduces drift risk: any change to engine formulas would require parallel updates to templates with no automated check that they stay synchronized.

---

## 2026-05-04 — v1 reframed as read-only review tool, not operator action workflow

**Alternatives:** (a) keep the original v1 scope with accept/override/skip workflow, risk gates, CSV export, and seven-screen dashboard; (b) collapse to a read-only review tool the operator runs on demand to view recommendations, with all pricing application happening outside the tool.

**Rationale:** the operator's actual workflow is to look at recommendations, decide on prices in his head, and apply them through whatever channel he uses today. The original scope's accept/override/skip flow added a tracking surface for decisions the operator does not currently track. Removing it eliminates the need for `published_prices` and `operator_actions` tables, the config editor, the global constants editor, the admin panels, the CSV export, and the priority-grouped dashboard layout — all replaced by a single scrollable list view and a drill-down detail page. The tool becomes faster to build, faster to use, and easier to extend later when the operator's actual needs are known. v2 reintroduces decision-tracking surfaces if and when "what did I publish" becomes a question worth answering inside the tool.

---

## 2026-05-04 — Drop `published_prices` and `operator_actions` tables; drop `risk_status` and `risk_note` columns

**Alternatives:** (a) keep the tables and columns dormant in v1 (no UI to write to them, but schema reserved); (b) drop them and reintroduce in v2 if needed.

**Rationale:** dormant schema is quiet complexity — every migration, every audit, every test surface has to deal with tables that nothing reads or writes. Re-adding tables and columns when v2 needs them is cheap; carrying dead schema forward is not. The v1 use case (read-only review) does not require any of these surfaces. `risk_status` was tied to the accept-button gate that v1 doesn't have; with no edit UI to set it, the field is unsettable.

---

## 2026-05-04 — Refresh model: on-demand only, background task with progress polling

**Alternatives:** (a) Windows Task Scheduler runs a daily refresh at 6 AM; (b) on-demand only, synchronous (button blocks until refresh completes); (c) on-demand only, background task with progress polling; (d) CLI-only refresh, web app reads what's in the database.

**Rationale:** the operator runs the tool when he wants to price cards, not on a fixed cadence. Daily scheduled refresh produces stale data on the days he doesn't use the tool and competes with his actual schedule on the days he does. Synchronous in-app refresh would block the UI for 2-4 minutes, which is too long. Background task with progress polling gives the operator clear feedback while keeping the request model simple — one POST starts the task, polls show progress, the table updates when done. Eliminating Task Scheduler also removes a Windows-specific deployment dependency, simplifying setup.

---

## 2026-05-04 — Single competitor scraper in v1: CardCash, reference-only display

**Alternatives:** (a) ship multiple competitor scrapers in v1 (CardCash + Raise, with Cardpool/GiftCardGranny in v2); (b) ship one source, with additional sources tracked as v2 work; (c) defer all competitor scraping to v2 and ship v1 with eBay only.

**Rationale:** CardCash is the right first source on three criteria. Merchant-catalog overlap with Zeal's ~300 merchants is highest among the candidates (1,000+ merchants on CardCash; the Zeal subset is almost entirely covered). Data shape matches the operator's manual-workflow input — CardCash publishes a per-merchant "we'll buy at X%" rate, the same shape as the spreadsheet's competitor cells. Site stability is acceptable: server-rendered HTML, stable URL pattern, Cloudflare tractable with polite request rates. Raise is structurally noisier (marketplace pricing across denominations), Cardpool's catalog has shrunk significantly, and GiftCardGranny is an aggregator (scraping a scraper compounds fragility). Shipping one source rather than two protects against the operational risk of investing scraper-debugging time on two sources before either has been validated against operator judgment. Additional sources are tracked in `pricing_algorithm.md` §11 item 11.

Competitor data is reference-only in v1 — displayed on the merchant detail page, not consumed by the engine. The algorithm stays spreadsheet-faithful. v2 introduces the `ebay_weight` slider that connects the existing competitor aggregation pipeline to the engine's blending path.

---

## 2026-05-04 — `price_recommendations` is the system of record; append-only, no pruning

**Alternatives:** (a) overwrite the latest recommendation per merchant (one row per merchant, current-state model); (b) append-only with periodic pruning of old rows; (c) append-only with no pruning, storing all history forever.

**Rationale:** the operator wants the tool to be a continuous historical reference of pricing data from the moment v1 launches. Append-only achieves this; overwriting destroys the "what did the algorithm say last week" answer. SQLite handles ~300 merchants x weekly refresh x indefinite retention without strain (~15K rows/year, well under any meaningful threshold). Pruning is easy to add later; un-pruning is impossible. No pruning in v1.

---

## 2026-05-04 — Future website integration is the architectural North Star

**Alternatives:** (a) treat website integration as a future redesign and don't constrain v1 around it; (b) build v1 with the integration as an explicit architectural constraint, even though it's not a v1 feature.

**Rationale:** the operator described website integration as a likely v2/v3 outcome if v1 proves useful. The cost of preserving feasibility now is low — the pure-function engine boundary in `pricing/` already exists and is enforced by the test suite. The cost of *not* preserving it is high: any cross-layer leak (e.g. SQLite calls in the engine, FastAPI imports in `pricing/`) would mean the website integration is a rewrite rather than a wiring exercise. The constraint is documented in `architecture.md` §1 (goal: forward-compatible) and §14 (acceptance criterion 10: import-linter rule in CI). v1 ships without any website integration code; it ships with the engine boundary defended.

---

## 2026-05-04 — Sort signals: delta-from-last-run (default) and max-abs-delta-over-N (secondary)

**Alternatives:** (a) sort by delta-from-last-run only; (b) sort by max-abs-delta-over-N only; (c) sort by delta-from-published-price (the original scope); (d) provide both delta-from-last-run and max-abs-delta-over-N as sortable columns.

**Rationale:** delta-from-last-run answers "what changed since I last refreshed" — the most common question. Max-abs-delta-over-N answers "what has been drifting steadily" — caught only by looking across multiple runs. Both are computed at query time from the `price_recommendations` table; no schema changes, no triggers. Default sort is delta-from-last-run by absolute value, descending — large movers float to the top. The secondary column is sortable on click. N defaults to 5, configurable later if 5 turns out to be wrong. Delta-from-published-price (original scope) is no longer applicable because v1 doesn't track published prices.
