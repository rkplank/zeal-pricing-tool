# eBay Sold-Listings Scraper — Fresh-Session Handoff

_Branch: feature/competitor-scrapers (or a new branch cut from it / from main after merge)._
_This document is a starting brief for a new session. No eBay scraper code exists yet._

---

## 1. Goal

Replace the blocked eBay Marketplace Insights API path with a DIY httpx scraper of
eBay sold/completed listings. The scraper must:

- Fetch sold-listing data for a given merchant using `httpx.AsyncClient` (no browser,
  no Playwright — same as the CardCash approach).
- Implement the existing `EbayClient` Protocol so it slots in transparently behind the
  factory function. `filter_listings()`, `compute_ebay_average()`, and the refresh
  orchestrator are **unchanged**.
- Operate local-first, on-demand, from a residential IP at low bursty volume.

**What this is not:** it is not a replacement for Marketplace Insights if that access
ever comes through. A managed-scraper API (e.g. Scrapfly, SerpAPI) is a documented
fallback adapter that can be wired behind the same seam later. v1 is DIY httpx because
the operator profile makes it the right first path.

---

## 2. Why DIY over a paid API for this profile

eBay's scraper defenses are well-documented and rate-based. What trips them:

- Datacenter IP ranges (Scrapfly, SerpAPI, Render, etc.)
- High request rates (10+/s, parallel scrapers)
- Headless browser fingerprints without realistic JS execution

None of these apply here:

- Residential IP (operator's home machine) — looks like a person browsing
- Low bursty volume — ~300 merchants, on-demand, not continuous
- httpx with realistic headers — indistinguishable from a browser at low rates

This is the same reasoning that made the CardCash scraper work without Cloudflare
issues. A managed API adds cost and latency for defenses that don't affect this profile.
Fallback: if eBay's sold-listing pages do trip residential-IP blocks at this volume,
a SerpAPI/Scrapfly adapter behind the same `EbayClient` seam is the upgrade path —
not a rewrite.

---

## 3. The proven playbook (mirror the CardCash approach)

Same five steps that worked for CardCash:

1. **Recon:** fetch a real sold-listing page with a throwaway script (residential IP,
   operator-run). Inspect the HTML. Identify what data is in the static response vs
   what requires JS execution.

2. **Capture a real fixture:** save the raw HTML for a known merchant's sold-listings
   page. This becomes the test fixture. Confirm face value and sale price are parseable
   from the static response before writing any adapter code.

3. **Firewall hand-derivation (critical — see §4):** before trusting the parser,
   hand-check 3-5 rows against the live eBay page. Confirm: (a) which field is sale
   price vs face value, (b) whether shipping is separate or included, (c) what the
   correct `sold_at` timestamp format is. Do not delegate this to a test — a test
   written against a misread fixture will pass and silently corrupt the eBay sell %.

4. **Build parser/adapter against the fixture:** implement `EbayScraperClient` that
   implements the `EbayClient` Protocol. All tests use the saved fixture; no live
   network in tests.

5. **Wire into the factory:** add `ZEAL_EBAY_MODE=scraper` as a new mode in
   `src/zeal/config.py` and `src/zeal/ingestion/ebay_client_factory.py`. The
   orchestrator (`src/zeal/ingestion/refresh.py`) calls `create_ebay_client()` and
   is unaware of which concrete client it receives.

---

## 4. The firewall caution (state this loudly)

**Face value comes from the listing title** (e.g. "$100 Gift Card" → `100.00`). A
silent parse misread of price or face value corrupts the core `ebay_sell_pct` formula
(`sale_price / face_value`) and would pass every unit test written against the same
misread fixture. The golden test suite cannot catch this because it tests the engine
with known inputs, not the parser.

**Before writing the adapter, hand-check a few rows:**

- Find 3 listings for a clean merchant (e.g. Home Depot) on the live eBay sold page.
- Note the face value shown in the title, the sale price shown in the listing, and
  whether the sale price includes shipping.
- Confirm the fixture HTML contains these same values in the same fields.
- If shipping is separate and shown in the listing, decide whether to add it to
  `sale_price` or ignore it — this is a spec decision (see `pricing_algorithm.md §6`)
  that must be made explicitly, not by default.

The CardCash equivalent of this step was the `upToPercentage` semantic gate
(2026-06-14 decisions_log entry). It caught a direction ambiguity before any
production data was written.

---

## 5. Key seam facts (exact paths from the codebase)

### The EbayClient Protocol

**`src/zeal/ingestion/ebay_client.py`**

```python
class EbayClient(Protocol):
    async def sold_listings_for_merchant(
        self,
        *,
        merchant_id: str,
        inclusion_regex: str,
        exclusion_regex: str | None,
    ) -> Sequence[EbaySoldListing]: ...
```

The new `EbayScraperClient` must implement this exactly. `EbaySoldListing` is defined
in `src/zeal/models/ebay.py`.

### The factory

**`src/zeal/ingestion/ebay_client_factory.py`** — `create_ebay_client(*, config, http_client, max_results_default)`.

Currently returns `SyntheticEbayClient` when `config.ebay_mode == "synthetic"` and
`EbayMarketplaceInsightsClient` when `config.ebay_mode == "live"`. Add a third branch:
`config.ebay_mode == "scraper"` → `EbayScraperClient(http_client=http_client)`.

### Mode config

**`src/zeal/config.py`** — `EbayMode = Literal["synthetic", "live"]`. Extend to
`Literal["synthetic", "live", "scraper"]`. Set via `ZEAL_EBAY_MODE=scraper` in `.env`.

### Downstream consumers (unchanged)

- **`src/zeal/pricing/listing_filter.py`** — `filter_listings(listings, merchant, now)`
  applies validity filters per spec §6.2. Takes `Sequence[EbaySoldListing]`.
- **`src/zeal/pricing/ebay_average.py`** — `compute_ebay_average(observations)` per
  spec §6.3. Takes `list[EbayObservation]` (derived from filtered listings).
- **`src/zeal/ingestion/refresh.py`** — `run_refresh()` orchestrator. Calls
  `create_ebay_client()` once per run; iterates merchants; calls
  `client.sold_listings_for_merchant(...)`. No changes needed here.

---

## 6. Current state and the next operator action

A throwaway recon script (`ebay_sold_recon.py`) **exists** (operator-run, residential
IP). It is **not committed** to `src/` and must not be — it is a one-off probe script,
not production code.

**Next action (operator, not CC):**

1. Run the recon script on 3 merchants:
   - A clean high-volume one (e.g. Home Depot or Target)
   - A disambiguation trap (e.g. "Michael Kors" vs "Michaels" — tests that
     `inclusion_regex` filtering works correctly against noisy search results)
   - A noisy financial card (e.g. "Visa" or "Mastercard" — tests rejection of
     activation fees, bank cards, and non-gift items)
2. Paste the parse output back into the chat.
3. Save the raw HTML fixture for the clean merchant.

The real adapter gets built against that fixture. A new session starts from this doc,
the paste, and the fixture — not from memory of prior conversations.

---

## 7. What the managed-scraper fallback looks like

If DIY httpx hits eBay blocks at residential IP (unlikely at this volume, but possible):

- Scrapfly or SerpAPI can be wired as an `EbayScraperClient` variant that calls their
  API instead of eBay directly. The HTML response shape is the same; only the fetch
  function changes.
- The adapter is a one-file swap behind the factory. Nothing else changes.
- Cost: ~$0.002/request at ~300 merchants/run = ~$0.60/run — acceptable if needed.

This is documented here so the next session knows the fallback exists and what it costs,
not as a first-move recommendation.

---

## 8. DON'T list for the eBay scraper build

- Do not commit `ebay_sold_recon.py` or any probe script into `src/` or `tests/`.
- Do not use the Browse API — it returns active listings only; sold data is not available
  through Browse. See decisions_log 2026-05-05.
- Do not put real eBay credentials in code, fixtures, docs, or commit history.
- Do not change `filter_listings()`, `compute_ebay_average()`, or the pricing engine.
- Do not change the `EbayClient` Protocol signature — the new client must match it.
- Do not run live eBay validation until the face-value firewall check (§4) is done and
  the parse output has been hand-verified against the live eBay page.
