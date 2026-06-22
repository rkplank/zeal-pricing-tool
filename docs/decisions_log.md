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

---

## 2026-05-05 — eBay sold-listings access requires Marketplace Insights API, not Browse API

**Issue:** The spec and architecture docs originally referenced "eBay Browse API, sold listings filter" as the data source for the eBay sell %. This is incorrect. The Browse API returns active listings only; it has no sold-listings filter. Sold (completed) listing data on eBay's modern API surface requires the Marketplace Insights API, which is a separate, gated program beyond the general eBay developer program. Access requires a distinct business-case application.

**Application status:** The general eBay developer program application has been submitted. A response has not yet arrived. The specific API tier that will be granted — and in particular whether Marketplace Insights access will be approved — is pending. No code should be written against the live eBay API until the tier is confirmed.

**Fallback contingencies:** If Marketplace Insights is denied, the available fallbacks are poor. The Finding API's `findCompletedItems` call historically exposed sold-listing data but is being retired by eBay. The Trading API's `GetSellerTransactions` exposes only a seller's own transaction data, not the market. Both contingencies are v2-class problems: they require reassessing the core data source and potentially the algorithm's eBay sell % input. Scraping eBay's sold-listings pages is the last resort and was explicitly ruled out as too risky given eBay's scraper defenses (see the 2026-05-01 "eBay Browse API, not scraping eBay" entry — the same reasoning applies here with even more force on completed-listing pages).

**v1 build plan unchanged:** v1 proceeds against the `EbayClient` protocol seam with `SyntheticEbayClient` providing the synthetic data needed for Phase 2 dashboard rendering. Phase 3 (live eBay refresh) is gated on API access confirmation. The build sequence is unaffected because Phase 2 does not require live ingestion.

**Alternatives:** (a) block all eBay-related development until access is confirmed — rejected because Phase 1 and Phase 2 work is API-independent; (b) proceed assuming Browse API works — rejected because it demonstrably does not expose sold-listing data; (c) proceed as above.

**Rationale:** documenting this now prevents the Phase 3 build from starting under incorrect assumptions about which API to integrate against. Marketplace Insights is the correct target; Browse is the wrong target.

---

## 2026-05-08 — Continue synthetic-mode usability work while Marketplace Insights is blocked

**Status:** eBay has not yet responded. Production Marketplace Insights entitlement remains blocked because the production keyset cannot mint `buy.marketplace.insights`.

**Decision:** Continue dashboard UI/usability review and documentation alignment in synthetic mode. Do not run production live validation, do not use Browse API fallback, and do not change the pricing algorithm, schema, live eBay client behavior, or credential-day smoke-test logic while waiting.

**Alternatives:** (a) keep waiting without further work; (b) attempt a Browse API workaround; (c) proceed with synthetic-mode usability review.

**Rationale:** synthetic mode already provides seeded baseline recommendations that are sufficient for reviewing table scannability, labels, detail-page comprehension, formula explanations, and operator workflow. Browse API cannot supply sold listings and would produce the wrong market signal. Live data quality work belongs on credential day after production Marketplace Insights entitlement is enabled.

---

## 2026-05-09 — Rename manual override display to config override

**Alternatives:** (a) keep "manual override"; (b) rename dashboard source/status labels to "Config override."

**Rationale:** "manual override" was misleading because it sounded like the operator had taken an action inside the dashboard. The label actually reflected spreadsheet/config hardcoded inputs such as `online_sell_override` and `electronic_buy_override`, not operator action history, accept/override/skip workflow, or published-price state. The dashboard now says "Config override" for those source/status labels.

---

## 2026-05-09 — Bring narrow merchant config editor into v1 scope

**Alternatives:** (a) keep all config editing out of v1; (b) add broad admin/config editing; (c) allow only narrow one-merchant-at-a-time formula/config editing with history logging.

**Rationale:** This is an explicit v1 scope change while awaiting eBay access. The spreadsheet was both a display surface and a control surface; a narrow merchant config editor preserves operator authority and helps tune regexes/config after live eBay access. Allowed scope is one-merchant-at-a-time config editing with history logging. Still out of scope: global constants editor, bulk editing, accept/override/skip workflow, `published_prices`, `operator_actions`, `ebay_weight` UI, competitor blending, auto-publishing, scheduled refresh, and internal sale history.

---

## 2026-05-10 — Price history chart implemented as server-rendered SVG, recommendation history only

**Alternatives:** (a) client-side JS chart library (e.g. Chart.js); (b) no chart, history table only; (c) server-rendered SVG polylines.

**Rationale:** A server-rendered SVG chart requires no JavaScript dependencies, no CDN assets beyond HTMX, and produces a fully accessible, easily styled chart with no flash-of-unloaded-content. The chart plots Online sell, In-mail buy, In-store buy, Electronic buy, and eBay sell from saved `price_recommendations` rows only. It does not represent prices Zeal actually published or applied outside the tool — the template explicitly notes this. The chart requires at least two comparable recommendation rows before it renders; a single row shows an empty-state message instead of a misleading single-point line.

---

## 2026-05-10 — Dashboard shows saved tool recommendations, not Zeal published prices

**Alternatives:** (a) make the chart or detail pages represent published prices; (b) label chart/history rows as "recommendation" to distinguish from published; (c) add a "published price" column.

**Rationale:** v1 does not track which recommendations the operator chose to apply, and the tool has no connection to where Zeal's prices are published. Every recommendation displayed in the dashboard — pricing list rows, merchant detail cards, price history chart, recommendation history table — reflects `price_recommendations` rows written by `run_refresh()`. These are the algorithm's saved outputs. The operator applies prices outside the tool. The phrase "Zeal actual/published prices" must not appear in the dashboard or docs as something the tool shows or tracks; templates and docs use "saved tool recommendations" or "recommendation history."

---

## 2026-05-10 — CardCash competitor data schema and aggregation logic present; automated scraper not yet built

**Alternatives:** (a) ship CardCash scraper in v1 as originally planned; (b) defer schema/aggregation until scraper exists; (c) current path: schema + aggregation logic in v1, manual import only, automated scraper deferred.

**Rationale:** The competitor data schema (`competitor_sources`, `competitor_observations`) and the `aggregate_competitor_observations()` pure function are implemented and tested. The competitor reference panel on the merchant detail page reads from these tables. However, the automated CardCash scraper (`ingestion/competitor/`) was not built in v1. Competitor data is available in the DB only if inserted manually or through a future scraper. The architecture and algorithm docs previously described the scraper as if it were current code; this entry documents the actual v1 status. The scraper remains a planned v2 addition.

---

## 2026-05-10 — eBay access status: production keyset cannot mint buy.marketplace.insights; awaiting eBay support

**Status note added to decisions log for searchability.**

Production Marketplace Insights API access is NOT yet granted. The sandbox keyset has the `buy.marketplace.insights` scope; the production keyset does not. Awaiting eBay support. v1 currently operates in synthetic mode using seeded spreadsheet-baseline recommendations. Do not run live eBay validation and do not use Browse API (Browse provides active listings only, not sold listings) until production Marketplace Insights entitlement is confirmed.

See also: 2026-05-05 and 2026-05-08 entries above.

---

## 2026-05-30 — Two-concept competitor confidence model: stored source-quality vs effective confidence

**Alternatives:** (a) a single confidence value set at parse time that encodes both data-surface precision and recency in one step; (b) separate stored and computed values, with aggregation consuming the computed form.

**Rationale:** Conflating precision and recency in a single stored value makes it impossible to re-evaluate freshness as observations age without updating existing rows — which is undesirable in an append-only table. Separating the concepts allows: (1) the scraper to record what it knows at parse time (the surface's inherent precision), immutably; (2) the aggregation layer to apply a recency decay at query time without touching stored data. This design keeps `competitor_observations` append-only while still allowing effective confidence to degrade as observations age. See `competitor_scraper_design.md §6` and `pricing_algorithm.md §7.5`.

---

## 2026-05-30 — CompetitorClient Protocol parameter renamed source_key (from cardcash_id)

**Alternatives:** (a) keep `cardcash_id: int` as the parameter name, accept that it is source-specific; (b) use `source_key: int` as a more generic name that accommodates future non-CardCash sources; (c) use `source_key: str | int` immediately to handle both numeric and string identifiers.

**Rationale:** `cardcash_id` in the Protocol signature is a leaking abstraction: the Protocol is meant to be source-agnostic, but a CardCash-named field makes every future implementer feel out-of-place. `source_key: int` is generic enough for v1 (all identifiers in v1 are integers from the CardCash blob `id` field) while being specific enough to type correctly. Widening to `str | int` is a one-line change when a source with string identifiers is added. The DB column `merchants.cardcash_id` retains its name — this is the Protocol parameter only. See `competitor_scraper_design.md §3.1`.

---

## 2026-05-30 — Cart POST response parsed by field match, not positional index

**Alternatives:** (a) use `response["cards"][-1]["percentage"]` (the last entry, assuming it is the one just added); (b) locate the entry by matching `card["merchant"] == source_key` (the merchantId just POSTed).

**Rationale:** the CartCash cart API accumulates entries across merchants in a single session — adding a second merchant produces a two-entry `cards` array under the same `cartId`. Positional access `cards[-1]` assumes the API always returns the most-recently-added card last, and that no reordering ever occurs. This assumption is fragile and unverifiable without exhaustive testing across every merchant and API version. Field-based matching on the `merchant` integer is unambiguous regardless of array order. The scraper already knows `source_key` (it just POSTed it); the match is trivial and eliminates a category of cross-merchant contamination bug. See `competitor_scraper_design.md §4.5` step 3 and `§4.8` step 3.

---

## 2026-05-30 — enterValue standardized to 100, clamped to [minFaceValue, maxFaceValue] from blob

**Alternatives:** (a) use a fixed value of 100 with no guard; (b) use the merchant's `maxFaceValue` from the blob; (c) clamp 100 to the merchant's face-value range, skip if bounds are malformed.

**Rationale:** standardizing on $100 ensures comparability across merchants and across runs — a consistent basis for the `percentage` rate returned by the API. However, some merchants may not support a $100 denomination (e.g. a merchant whose cards only come in $25 increments). Posting an unsupported `enterValue` could produce a non-201 response or an error payload rather than a rate. Reading `minFaceValue` and `maxFaceValue` from the blob (already fetched) and clamping 100 to that range handles the common edge case without a live probe. Malformed bounds (`minFaceValue > maxFaceValue`) indicate a corrupt blob entry and warrant a `no_data` observation rather than a heuristic guess. The clamp is a Phase 1 safety assumption; Phase 2 verification with real API behavior is explicitly required. See `competitor_scraper_design.md §4.5` step 3 and `§4.8` step 3.

---

## 2026-05-30 — Session resilience: re-bootstrap on 401/403 or ≥18-min elapsed; 40-min total budget cap

**Alternatives:** (a) no session resilience — rely on the 20-minute JWT covering a ~3-4 minute normal run; (b) re-bootstrap on any non-2xx response; (c) re-bootstrap specifically on 401/403 or at 18 minutes elapsed, with a 40-minute total cap.

**Rationale:** a normal run of ~300 merchants at 750ms per-POST takes ~3-4 minutes, comfortably within the 20-minute JWT lifetime. However, the session can become invalid mid-run due to stale tokens (401/403) or if the run is paused or slowed by retries. Checking elapsed time at 18 minutes (2-minute safety margin) provides a proactive escape hatch without polling or inspecting the JWT's `exp` field. Re-bootstrapping on 401/403 handles the reactive case. The 40-minute total budget cap prevents a stalled merchant or repeated re-bootstraps from extending a run indefinitely, ensuring the `refresh_runs` row reaches a terminal state (`partial`) in all scenarios. See `competitor_scraper_design.md §4.6`.

---

## 2026-05-30 — Canary invariants checked before processing catalog; failure raises CompetitorClientError

**Alternatives:** (a) no canary check — proceed with catalog regardless of size or anchor presence; (b) per-merchant validation only, skipping merchants that fail field-type checks; (c) catalog-wide canary before any per-merchant processing.

**Rationale:** structural failures (schema renames, response format changes, truncated catalog) affect all merchants simultaneously and produce systematically wrong data, not isolated per-merchant errors. Emitting ~300 `no_data` observations when the catalog is empty or missing key fields provides the operator with no useful information and obscures the real failure mode. Raising `CompetitorClientError` on catalog-level canary failure aborts the run cleanly, sets `status='failed'`, and surfaces a single error message. The three invariants chosen (catalog size >100, anchor merchant presence, field type checks) are observable from the blob without network calls and detect the most common structural breakage. Anchor IDs may need updating if CardCash renumbers merchants (rare). See `competitor_scraper_design.md §9`.

---

## 2026-05-30 — Phase 4 migration hard gate before first live scraper run

**Alternatives:** (a) run the scraper immediately after schema.sql edits with delete-and-reseed assuming no production data exists; (b) require explicit confirmation of an ALTER TABLE path or a DB backup before the first live run.

**Rationale:** the Phase 1 schema additions (`cardcash_id` on `merchants`, `kind` on `refresh_runs`) are applied via `schema.sql` + delete-and-reseed. By the time Phase 4 ships, the production `data/zeal.db` may contain operator-entered merchant config edits, live eBay observations, and recommendation history not reproducible from the seed fixture. A silent delete-and-reseed would silently destroy this data. Requiring an explicit gate (ALTER TABLE path documented, or backup confirmed) prevents accidental data loss. This is a one-time gate for the Phase 4 feature, not an ongoing operational requirement. See `competitor_scraper_design.md §10 Phase 4` and `architecture.md §11 Phase 4`.

---

## 2026-05-30 — Second competitor source triggers evaluation of competitor_merchant_mapping table

**Alternatives:** (a) add a source-specific column to `merchants` for each new source (e.g. `raise_id`, `cardpool_id`); (b) normalize source-specific identifiers into a `competitor_merchant_mapping(merchant_id, source_name, source_key)` table from the start; (c) defer the mapping table decision until a second source is actively being added.

**Rationale:** one column per source (`cardcash_id`, `raise_id`, …) is straightforward for 2-3 sources but becomes unwieldy at 4+. A `competitor_merchant_mapping` table normalizes the pattern and avoids schema churn for each source addition. v1 uses the per-column approach (only `cardcash_id`) because it is simpler and the single-source requirement is well-defined. The decision to migrate to the normalized table should be made when a second source is actively scoped — at that point the operator will know whether both sources' identifiers are numeric integers (in which case the column approach extends easily) or whether source-specific shapes require a more flexible schema. See `pricing_algorithm.md §11` item 17 and `competitor_scraper_design.md §5`.

---

## 2026-06-14 — Python 3.12 (python.org CPython) standardization and truststore TLS fix

**Alternatives:** (a) continue on python-build-standalone 3.14 (the uv default); (b) standardize on 3.12 python.org CPython; (c) set `python-preference = "only-managed"` to pin uv-managed 3.12.

**Rationale:** The venv was being created on python-build-standalone 3.14 (the uv default when no system 3.12 exists). Two problems with that: (1) `pyproject.toml` targets Python 3.12 — running on 3.14 means CI and local are testing different minor versions; (2) python-build-standalone on Windows omits the OpenSSL `applink.c` shim, which routes `malloc`/`free` calls between DLLs at SSL startup. Without it, Python's `ssl` module can raise `CERTIFICATE_VERIFY_FAILED` even on sites with well-known CA chains. The python.org installer bundles the correct OpenSSL build with the applink wiring intact.

`python-preference = "only-system"` in `[tool.uv]` ensures uv will not silently fall back to a managed interpreter if the system one is missing — the error is explicit and correctable, rather than a silent version drift.

Python 3.12.10 installed via `winget install Python.Python.3.12 --source winget`. All 507 tests pass on 3.12.

**Truststore:** `truststore==0.10.4` added as a runtime dependency; approved by operator 2026-06-14. `truststore.inject_into_ssl()` called once in `zeal.cli.main()` and once in `zeal.web.app._lifespan()` — startup only, not inside library or ingestion modules, and not in tests (respx mocks are unaffected). Before/after probe: both `api.ebay.com` and `www.cardcash.com` raised `CERTIFICATE_VERIFY_FAILED` without injection; after injection both return successful TLS handshakes (HTTP 404 and 200 respectively). This resolves a blocker that would have prevented any live eBay or CardCash network calls on this machine.

---

## 2026-06-14 — upToPercentage semantic gate confirmed: percentage-points, formula price_pct = 1 − up/100 correct

**Gate required by:** `competitor_scraper_design.md §4.4` and `§10 Phase 2`. Phase 4 must not ship until this is confirmed and documented here.

**Verification method:** parsed the real `tests/fixtures/cardcash/buy_catalog.html` fixture (773 merchants) using `json.JSONDecoder().raw_decode()` and inspected field values directly. No scraper code consumed; literals checked by hand.

**Findings:**

| Merchant | id | `upToPercentage` (type) | `price_pct = 1 − up/100` |
|---|---|---|---|
| Home Depot | 27 | `2` (int) | `0.9800` — consumer pays 98.0% of face value |
| Starbucks | 54 | `5.6` (float) | `0.9440` — consumer pays 94.4% of face value |
| Macaroni Grill | 352 | `45.5` (float) | `0.5450` — consumer pays 54.5% of face value |

Full catalog stats: `upToPercentage` ranges [0.0, 45.5] across all 773 entries; all values in [0, 100]; median ≈ 5.5. These are clearly percentage-points (a discount in percentage-point units), not normalized fractions (which would all be <1.0).

**Gate result — CONFIRMED:**
- (a) `upToPercentage` is a discount in percentage-points. A value of 2 means "2% off face value," so the consumer pays 98.0%, not 2.0% of face value.
- (b) The formula `price_pct = 1 − upToPercentage / 100` yields plausible consumer prices. Derived values cluster in [0.54, 1.0], consistent with real gift-card market rates.

**Non-obvious finding — field types:** `sellIsOff` and `cardsAvailable` are `int` in the live API response, not `bool`. `sellIsOff ∈ {0, 1}`; `cardsAvailable` is a card-inventory count (0 = none in stock, N = N cards available). 79 of 773 merchants have `sellIsOff=1`; 182 have `cardsAvailable=0`. The parser uses Python truthiness checks (`if entry["sellIsOff"]`, `if not entry["cardsAvailable"]`), which handle both int and bool correctly and match the spec's intent.

**Alternatives considered:** no alternatives — this was an empirical verification step, not a design choice. The only decision was the formula direction (consumer-pays vs discount), and the data confirms the consumer-pays reading: `upToPercentage=2` on Home Depot means the buyer pays 98% of face value.

**Consequence:** Phase 4 (`zeal refresh-competitors`) may proceed once the sell-side cart flow (Prompt 2b) is implemented and validated. The buy-blob `sell`-channel formula is locked as `price_pct = 1 − upToPercentage / 100`.

---

## 2026-06-22 — CardCash sell-flow auth + cart shape corrected from live capture

**Decision:** Updated `competitor_scraper_design.md §4.5, §4.6, §4.8` to reflect confirmed live API behavior. Supersedes the auth-recon and cart-shape assumptions in the 2026-05-30 entries.

**Corrections:**

1. **Auth is cookie-not-header.** Bootstrap is `POST /v3/session` with `json {}` and header `x-cc-app: q3vsT1zXO`. The server responds with `Set-Cookie: q3vsT1zXO=<JWT>`. A cookie-jar httpx client carries the JWT automatically on all subsequent `/v3/` calls. There is no `Authorization` header. The `x-cc-app` header value is the literal string `q3vsT1zXO` (an app identifier), sent on every `/v3/` request — it is not the JWT value. The prior design described a homepage GET bootstrap (`GET https://www.cardcash.com/`) that does not work headlessly; the homepage GET sets no cookies.

2. **Cart action must be `"sell"`, not empty.** `POST /v3/carts` with body `{"action":"sell"}` returns 201. The body `{"action":"buy"}` also returns 201 but then rejects card-adds with a JSON schema validation error (`instance is not exactly one from </AddGiftCard>,</AddNewGiftCard>,</AddNewCartCard>`). The prior design described an empty body.

3. **cartId is flat.** The cart-create response body is `{"cartId": "...", "cards": []}`. The prior design described a nested shape (`cart.sellCart.cartId`) which does not match the live API.

4. **`sellIsOff` and `cardsAvailable` are `int`, not `bool`.** `sellIsOff ∈ {0, 1}`; `cardsAvailable` is a card-inventory count. Python truthiness checks handle both int and bool correctly; the canary field-type check is updated to accept `int`.

**Source:** confirmed by headless probe script (anonymous session, no transaction, two merchants) executed 2026-06-21. Probe committed as a fixture-capture run; probe script not committed.

**Alternatives:** none — this was empirical correction, not a design choice.
