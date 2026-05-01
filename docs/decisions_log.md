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
