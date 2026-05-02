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