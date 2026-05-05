# Zeal Cards Pricing Algorithm — v1 Specification

**Status:** Draft for review — v1 scope realigned 2026-05-04
**Owner:** [your name]
**Last updated:** 2026-05-04
**Source of truth:** `GiftCardPricingData_2025.xlsx` (PricingSheet, InputsandMargins) — March 2022 baseline

---

## 1. Purpose

This document specifies the v1 pricing algorithm for the Zeal Cards pricing tool. The tool is a read-only review dashboard used by one operator (the owner) to view buy and sell price recommendations for gift cards. It is not an automated pricing system; the operator applies prices outside the tool, and the algorithm produces *recommendations* the operator references.

v1 has two design properties:

**Spreadsheet-faithful algorithm.** Given the same eBay sell input and the same per-merchant configuration, the v1 system produces the same Buy and Sell prices the spreadsheet produces. Phase 1 golden tests verify this property over 281 baseline merchant records.

**Competitor data collected and displayed, not blended.** The tool ingests competitor data from at least one external source (CardCash in v1) on each refresh and displays it on the merchant detail page as reference material. Competitor data does not feed the recommendation in v1; the operator sees competitor rates alongside the eBay-derived recommendation and uses both as inputs to his own pricing decision.

The engine's internal structure is forward-compatible with competitor blending: `ebay_weight` is a per-merchant column that defaults to 1.0 (eBay-only) and the engine code paths for competitor-only and blended computation exist and are unit-tested. v1 does not surface a UI to change `ebay_weight`; v2 will. This preserves the validation property while keeping the v2 expansion to a minimal change.

Improvements that materially change the algorithm beyond the above are tracked in §11 and explicitly out of v1 scope.

---

## 2. Glossary

| Term | Meaning |
|---|---|
| **Face value** | The dollar value loaded on the gift card (e.g. a $100 Home Depot card has $100 face value). |
| **eBay Sell %** | The fraction of face value at which a card sells on eBay, computed from sold listings. The market price ground truth. A merchant trading at 92% means a $100 card sells for $92 on eBay. |
| **Online Sell %** | The fraction Zeal lists the card for on its own storefront. In v1 this is computed from eBay-derived signal only. |
| **In-Store Buy %** | The fraction Zeal pays a customer who walks into a physical location with a card. |
| **In-Mail Buy %** | The fraction Zeal pays a customer who mails the card in. |
| **Electronic Buy %** | The fraction Zeal pays a customer who submits the card code online (no physical card transfer). |
| **Margin** | Zeal's gross-profit cushion on a transaction, expressed as a fraction of face value. Set per merchant by the operator. |
| **Tier** | A merchant grouping label (T24 / C / Z / NC) used as a default suggester. Not a hard rule — see §3. |
| **Channel** | One of the four price types: in-store buy, in-mail buy, electronic buy, online sell. |
| **Competitor Sell %** | The fraction at which a competitor is currently buying or selling a card, expressed as a fraction of face value. Per-source, refreshed as part of the on-demand refresh. See §7. |
| **Blended recommendation** | A channel price computed as a weighted combination of the eBay-derived recommendation and the competitor-derived recommendation, weighted by the merchant's `ebay_weight`. When `ebay_weight = 1.0`, the blended recommendation equals the eBay-only recommendation. In v1, `ebay_weight` is fixed at 1.0 for all merchants, so the blended recommendation always equals the eBay-only recommendation. |
| **eBay Weight** | A per-merchant float in `[0, 1]` controlling how much of the recommendation comes from eBay vs competitor signal. Default 1.0 (eBay-only). Locked at 1.0 in v1 with no UI to change it; v2 introduces the slider. |

All percentages in this document are expressed as fractions of card face value unless otherwise noted (e.g. 0.92 = 92%).

---

## 3. Tier vs. per-merchant configuration

The original spreadsheet documents four tiers:

| Tier | Code | Meaning |
|---|---|---|
| Top 24 | T24 | The 24 highest-volume merchants — most competitive market |
| Competitive | C | Merchants with active competing buyers |
| Zen-Only | Z | Limited competitor coverage (Z = legacy GiftCardZen reference) |
| No Competition | NC | Zeal is the only or near-only buyer |

The intent is that more competition means tighter margin (compete on price), less competition means wider margin (capture more profit per card).

**Important finding from analysis of the spreadsheet:** In practice, formulas do not strictly follow the tier label. Within the same tier, individual merchants reference different margin rows in `InputsandMargins`. For example, in the Competitive tier:
- Home Depot uses the **T24 in-store margin** (25%)
- Lowe's uses the **Competitive in-store margin** (25%)
- Disney uses the **Zen-Only in-store margin** (29%)
- Massage Envy uses the **No-Competition in-store margin** (30%)

This pattern recurs across the in-mail margin, e-bonus, and eBay differential as well.

**Decision for v1:** Configuration is **per-merchant**, not per-tier. Each merchant carries its own margin configuration. The tier label is preserved as a descriptive field used to suggest defaults when adding a new merchant later, but the algorithm reads margins from the merchant's own row.

This decision is conservative: it preserves whatever the operator intended (whether the per-merchant variations were deliberate or accidental drift). The question of intent versus drift is out of scope for v1; a config editor and drift audit are v2 work.

---

## 4. Inputs

### 4.1 Per-merchant configuration (stored, edited rarely)

| Field | Type | Notes |
|---|---|---|
| `merchant_id` | string | Stable internal identifier |
| `display_name` | string | Customer-facing name (e.g. "Home Depot") |
| `tier` | enum {T24, C, Z, NC} | Descriptive only — does not drive computation |
| `in_store_margin` | float | Fraction of face value Zeal keeps on in-store buys (e.g. 0.25 = 25%) |
| `in_mail_margin` | float | Same for in-mail buys |
| `e_bonus` | float \| null | Fraction subtracted from in-mail buy for electronic redemption. `null` = no electronic computation needed (override or ineligible). |
| `ebay_differential` | float | Difference between Zeal's online sell and eBay sell — see §5 |
| `in_store_eligible` | bool | If false, In-Store Buy = "No" regardless of inputs |
| `in_mail_eligible` | bool | If false, In-Mail Buy = "No" regardless of inputs |
| `electronic_eligible` | bool | If false, Electronic Buy = "No" regardless of inputs |
| `online_sell_override` | float \| null | If set, used directly as `online_sell` instead of computing from eBay input. For "Pattern A" merchants where eBay has no useful data and the operator hardcodes a storefront price (~25 local NC-tier merchants today). |
| `electronic_buy_override` | float \| null | If set, used directly as `electronic_buy` instead of computing from `in_mail_buy - e_bonus`. Currently used only by Home Depot eStore Credit (0.65). |
| `merch_credit_variant` | bool | True for merchant credit / store credit / rebate / no-receipt cards. Detected via display-name substring match (`merch credit`, `merchandise credit`, `estore credit`, `rebate`, case-insensitive). See spreadsheet_recon.md §7.4. |
| `notes` | string | Free-text operator notes |
| `ebay_weight` | float in [0, 1] | Default 1.0. The engine reads this field, but v1 keeps it locked at 1.0 with no UI. At 1.0, the recommendation equals the eBay-only path. |

### 4.2 Per-merchant market data (refreshed on demand)

| Field | Type | Notes |
|---|---|---|
| `ebay_sell_pct` | float \| null | Fraction of face value at which the card sells on eBay. `null` if no valid data. |
| `ebay_sample_size` | int | Number of valid sold-listing observations used to compute `ebay_sell_pct`. |
| `ebay_data_freshness_days` | int | Days since most recent observation. |
| `ebay_confidence` | enum {high, medium, low, none} | Derived — see §6.4 |

### 4.3 Global constants (from `InputsandMargins`, March 2022)

These are channel costs and bad-debt rates. Stored as a single global config row.

| Constant | Value | Source cell | Description |
|---|---|---|---|
| `ebay_sale_costs` | 0.13 | B2 | eBay's seller fee, fraction of sale price |
| `paypal_sell_costs` | 0.03 | B3 | PayPal processing fee on sales |
| `ebay_postage_costs` | 0.01 | B4 | Cost to ship a card sold on eBay |
| `online_store_postage_costs` | 0.03 | B5 | Cost to ship a card sold on Zeal's storefront |
| `online_sell_bonus_competitive` | 0.065 | B6 | Markdown passed to buyers on Zeal's storefront for Competitive/T24-tier merchants. Component of `ebay_differential` for those merchants. |
| `online_sell_bonus_zen_nocomp` | 0.085 | B7 | Markdown passed to buyers for Zen-Only and No-Competition tier merchants. Component of `ebay_differential` for those merchants. |
| `in_store_bad_debt` | 0.048 | B8 | Fraction of face value lost to fraud/empty cards on in-store buys |
| `in_mail_bad_debt` | 0.02 | B9 | Same for in-mail buys |
| `online_bad_debt` | 0.05 | B10 | Same for online (electronic) buys |
| `competitor_electronic_markdown` | 0.05 | — | v2-relevant fallback markdown for competitor electronic buy when a source lacks electronic-specific data. Provisional; not used in v1 recommendations. |

> Note: `ebay_differential` (B23 competitive = 4.5%, B24 Zen/NoComp = 2.5%) is itself derived from the constants above:
> - `B23 = ebay_sale_costs + ebay_postage_costs - online_sell_bonus_competitive - online_store_postage_costs`
> - `B24 = ebay_sale_costs + ebay_postage_costs - online_sell_bonus_zen_nocomp - online_store_postage_costs`
>
> v1 stores the differential as a per-merchant value (faithful to the spreadsheet's encoding). v2 may compute it dynamically from the components plus a per-merchant tier choice.

### 4.4 Per-merchant competitor data (collected as reference material)

Competitor observations are pulled from each active competitor source during the on-demand refresh. **v1 scope:** competitor observations are displayed on the merchant detail page alongside the recommendation. They are not consumed by the recommendation engine in v1. v2 may incorporate competitor data into the algorithm via the `ebay_weight` blending path; the schema and ingestion pipeline are designed for that progression.

| Field | Type | Notes |
|---|---|---|
| `source_name` | enum {cardcash, ...} | Identifies the competitor source. v1 ships with CardCash only. Additional sources (Raise, Cardpool, GiftCardGranny) are deferred to v2+ once the CardCash integration has been validated against operator judgment. |
| `merchant_id` | string | The Zeal merchant this observation refers to. |
| `channel` | enum {buy_mail, buy_electronic, sell, marketplace_sell} | Most competitors expose buy-side prices (what they pay sellers). Sell-side prices are less commonly available. |
| `price_pct` | float | Fraction of face value. |
| `availability` | enum {available, unavailable, no_data} | Whether the source is currently buying/selling this merchant. |
| `confidence` | enum {high, medium, low, none} | Per-source, per-observation. Independent of eBay confidence. |
| `observed_at` | timestamp | When the observation was captured. |
| `source_url` | string \| null | Link to the source page, for operator verification. |

**Source-to-channel mapping for v2:** competitor data can eventually inform `online_sell`, `in_mail_buy`, and `electronic_buy`. The `in_store_buy` channel has no clean competitor analogue because no major competitor operates physical storefronts. In v1, these observations remain reference-only display data.

**Cold-start behavior:** when no competitor observations exist for a merchant, the merchant detail panel shows "no competitor data yet." The recommendation is unchanged because v1 recommendations are eBay-only.

---

## 5. Output computation

For each merchant on each refresh, the algorithm computes four channel recommendations: `online_sell`, `in_mail_buy`, `in_store_buy`, `electronic_buy`. Each is a fraction of card face value (e.g. 0.78 = 78% = pay $78 on a $100 card).

**v1 behavior:** for every merchant, `ebay_weight` is fixed at 1.0 and the recommendation is computed via the eBay-only path described in §5.1-§5.5. Competitor data is collected per §7 and displayed on the merchant detail page (per `architecture.md` §7.2), but does not feed the recommendation.

**Engine structure:** the Phase 1 engine implements three computation paths — eBay-only, competitor-only, and blending — and unit tests cover all three. In v1 the competitor-only and blending outputs are computed but not surfaced to the operator. v2 introduces a per-merchant `ebay_weight` slider that exposes the blending output as the recommendation. The engine code does not change between v1 and v2; the difference is purely in the UI.

Read §5.1-§5.5 as v1's recommendation logic. §5.7 documents the engine's full structure for v2 reference.

### 5.1 Online Sell

```
if online_sell_override is not None:
    online_sell = online_sell_override
elif ebay_sell_pct is None:
    online_sell = "No Data"
else:
    online_sell = ebay_sell_pct - ebay_differential
```

`online_sell_override` is set for "Pattern A" merchants (~25 local NC-tier merchants where eBay has no useful sold-listing data and the operator manually sets a storefront price). When set, the eBay path is bypassed entirely.

Otherwise, for normal merchants: take eBay's market price and subtract the `ebay_differential` from the merchant's config. The differential exists because Zeal's online store does not pay eBay fees, so Zeal can list slightly cheaper than eBay net while still capturing more margin. Two values exist in practice: 4.5% (competitive/T24) and 2.5% (Zen-Only/NoComp). In v1 every merchant carries its own value.

### 5.2 In-Mail Buy

```
if not in_mail_eligible:
    in_mail_buy = "No"
elif online_sell == "No Data":
    in_mail_buy = "No Data"
else:
    in_mail_buy = (
        online_sell
        - in_mail_margin
        - paypal_sell_costs
        - in_mail_bad_debt
        - online_store_postage_costs
    )
```

When eligible and source data is present: take the price Zeal can sell at, subtract the operator's chosen profit cushion, subtract the cost to process the sale (PayPal), subtract expected fraud loss on mailed-in cards, subtract postage to ship the resulting sale.

### 5.3 In-Store Buy

```
if not in_store_eligible:
    in_store_buy = "No"
elif online_sell == "No Data":
    in_store_buy = "No Data"
else:
    in_store_buy = (
        online_sell
        - in_store_margin
        - paypal_sell_costs
        - online_store_postage_costs
        - in_store_bad_debt
    )
```

Same structure as in-mail buy, but uses the in-store margin and the in-store bad-debt rate. Bad debt is higher for in-store (4.8%) than in-mail (2.0%), reflecting that walk-in customers present a higher fraud rate than mail-in customers in Zeal's experience.

### 5.4 Electronic Buy

```
if not electronic_eligible:
    electronic_buy = "No"
elif electronic_buy_override is not None:
    electronic_buy = electronic_buy_override
elif in_mail_buy in ("No", "No Data"):
    electronic_buy = "No Data"
else:
    assert e_bonus is not None
    electronic_buy = in_mail_buy - e_bonus
```

The override path supports Home Depot eStore Credit, which is electronic-only with a hardcoded 0.65 payout. The override is checked **before** the in-mail dependency because eStore Credit has `in_mail_eligible = False` — without the override-first ordering, the merchant would never get an electronic price.

The e-bonus is *subtracted* from in-mail buy, meaning the customer is paid *less* for electronic redemption than for mailing in the card. This is a deliberate channel-mix incentive: the operator wants customers to mail cards in (lower fraud, higher conversion in his experience) and prices electronic less attractively to nudge them. The "bonus" naming in the spreadsheet refers to it being a bonus *to Zeal's margin*, not to the customer.

Spreadsheet uses three e-bonus values:
- `0.08` — competition exists (B19)
- `0.13` — no competition (B20)
- `0.17` — special: local/NC merchants in rows 250-294 (B21)

In v1 every merchant carries its own value.

### 5.5 Edge cases

- **Channel ineligibility** (`*_eligible = False`): produces `"No"` sentinel. The recommendation is `"No"`.
- **Missing eBay data with no override:** returns `"No Data"`. Competitor observations may still be displayed as reference-only material, but they do not create a v1 recommendation.
- **Pattern A merchants** (`online_sell_override` set): uses the override directly.
- **Pattern B merchants** (`electronic_buy_override` set, currently Home Depot eStore Credit): uses the override directly.
- **Low eBay confidence** (`ebay_sample_size < 10` or `ebay_data_freshness_days > 90`): prices are still computed but flagged. Display rule unchanged.

### 5.6 Formula breakdown

The pricing engine returns, alongside each channel's final value, a structured breakdown communicating how the final value was reached. The breakdown is a sequence of `(label, value, sign)` tuples representing the components of the formula, in computation order.

In v1, the breakdown for a normal recommendation includes: the eBay sell percentage, the per-channel margin subtraction, fees, bad-debt rate, postage, and the final value. For sentinel results (`"No"`, `"No Data"`), the breakdown communicates the reason rather than a numeric formula.

The dashboard renders breakdowns on the merchant detail page as the worked formula shown in §9. v2 may extend the breakdown to include competitor-path components and the blending step; the engine's `BreakdownStep` type is structured to accommodate this without a schema change.

### 5.7 Engine structure (v2-relevant)

This subsection documents engine paths that exist in code (with passing unit tests) but are not surfaced to the operator in v1. They are specified for completeness and to clarify the v1-to-v2 evolution.

**Competitor-only online sell:**

```
if competitor_online_sell_pct is None:
    online_sell_competitor = None
else:
    online_sell_competitor = competitor_online_sell_pct
```

**Competitor-only in-mail buy:**

```
if not in_mail_eligible:
    in_mail_buy_competitor = "No"
elif competitor_in_mail_buy_pct is None:
    in_mail_buy_competitor = None
else:
    in_mail_buy_competitor = competitor_in_mail_buy_pct
```

**Competitor-only electronic buy:**

```
if not electronic_eligible:
    electronic_buy_competitor = "No"
elif electronic_buy_override is not None:
    electronic_buy_competitor = electronic_buy_override
elif competitor_electronic_buy_pct is not None:
    electronic_buy_competitor = competitor_electronic_buy_pct
elif competitor_in_mail_buy_pct is not None:
    electronic_buy_competitor = competitor_in_mail_buy_pct - competitor_electronic_markdown
else:
    electronic_buy_competitor = None
```

The `in_store_buy` channel has no competitor analogue and remains eBay-derived.

**Blending rule:**

```
if ebay_value in ("No", "No Data"):
    final_value = ebay_value
elif competitor_value is None:
    final_value = ebay_value
else:
    final_value = ebay_weight * ebay_value + (1 - ebay_weight) * competitor_value
```

With `ebay_weight = 1.0`, this is mathematically identical to the eBay-only path regardless of competitor input. v1 depends on that property.

---

## 6. eBay sell percentage computation

The spreadsheet's rule (RFP §I) is: average the 10 most recent valid sold listings within the last 3 months. Compute `sum(value) / sum(price)` across the 10. Report the result.

v1 implements this rule faithfully, with extended validity filters and several housekeeping clarifications.

### 6.1 Data source

eBay **Marketplace Insights API**, sold listings, US location only, sorted by end date descending. This is the correct API surface for sold-listing data. The Browse API — which is sometimes confused for this purpose — returns active (live) listings only and does not expose completed or sold listing data; it is not suitable for computing the eBay sell %.

Access to the Marketplace Insights API is a Phase 3 prerequisite. It is a separately gated program beyond the general eBay developer program and requires a distinct business-case application. The general developer application has been submitted; the specific tier and whether Marketplace Insights will be approved is pending. See `architecture.md` §12 Q1 for current access status and decisions_log.md 2026-05-05 for fallback contingencies.

### 6.2 Validity filters

A sold listing is valid for the average when *all* of the following hold:

- Sale date <= 90 days ago
- Card has non-zero loaded value
- Listing is a standalone gift card (not a bundle, not a coupon, not a collectible)
- Card matches the target merchant (resolution rules in §6.5)
- Total price (winning bid + shipping) is positive
- Listing is for a regular gift card or merchandise/store credit (per RFP, both are in scope)
- Computed sell percentage falls in the range `[0.30, 1.10]`
- Listing title does not contain suspicious keywords: `coupon`, `coupons`, `bundle`, `lot`, `lots`, `collectible`, `collectibles`, `empty`, `zero balance`, `partial`, `not full balance`

Listings that fail any check are stored in `ebay_observations` with `validity_status = 'excluded'` and a populated `exclusion_reason` field naming the failed check. They are visible in the merchant detail page's excluded-observations table for operator review and debugging.

**Partial-balance handling:** v1 handles partial-balance cards by exclusion, not by parsing. Listings whose titles match partial-balance keyword patterns are excluded with `exclusion_reason = 'partial_balance_suspected'`. Parsing partial balances and including these observations in the average is deferred to v2 (§11).

### 6.3 Aggregation

For the most recent N valid listings (N <= 10):

```
ebay_sell_pct = sum(price_with_shipping_i) / sum(face_value_i)
```

This is the spreadsheet's exact formula. Note this is *not* the simple average of per-listing percentages — it is volume-weighted by face value. A $500 card sale at 90% counts more than a $25 card sale at 90%.

### 6.4 Confidence

| Sample size | Freshness (most recent listing) | Confidence |
|---|---|---|
| >= 10 | <= 30 days | High |
| >= 10 | 31-90 days | Medium |
| 5-9 | <= 90 days | Medium |
| 1-4 | <= 90 days | Low |
| 0 valid in 90 days | — | None (report "No Data") |

### 6.5 Merchant resolution

eBay listing titles are unstructured. Resolving "did this listing sell a Michael Kors card or a Michaels card" is a known hazard the original RFP calls out. v1 uses:
- A per-merchant **inclusion regex** (must match in title) and **exclusion regex** (must not match)
- Both stored on the merchant config row
- Fallback to manual review when match confidence is low

Default regexes are seeded from the merchant display name. Refining them through a UI is v2 work.

---

## 7. Competitor data collection and aggregation

Competitor signal is computed independently per source, then aggregated across sources to produce well-defined reference material for the merchant detail page. v1 surfaces aggregated competitor data as reference-only material. The aggregation logic exists end-to-end in v1 (per-source filtering, cross-source weighting per §7.4) so the merchant detail display is well-defined; v2 connects the aggregation output to the §5 blending path.

### 7.1 Data sources

v1 ships with one active competitor source: CardCash. Additional sources are tracked in §11.

Each source has its own ingestion path. In v1, that means the CardCash scraper. The algorithm consumes competitor observations from `competitor_observations` rows regardless of how they got there.

### 7.2 Refresh cadence

Competitor data is collected during the on-demand refresh, after the eBay refresh completes. CardCash requests sleep roughly 500-1000ms between requests to keep the scraper visibly polite.

### 7.3 Per-source aggregation

For a given merchant, channel, and source: the competitor observation displayed in v1 is the most recent valid observation for that merchant/channel/source within the last 30 days. If no observation in that window exists, the source contributes nothing for that merchant/channel.

A "valid" observation has:
- `availability = 'available'`
- `confidence != 'none'`
- `price_pct` in the range `[0.20, 1.20]` — wider than the eBay range because competitor sources occasionally list very low buy-side prices for low-demand merchants

Observations failing validity are retained in the database for audit but excluded from the aggregation.

### 7.4 Cross-source aggregation

When multiple sources produce valid observations for the same merchant and channel, the engine can aggregate them as a confidence-weighted average:

```
weights = {high: 1.0, medium: 0.5, low: 0.25}
competitor_pct = sum(weight_i * price_pct_i) / sum(weight_i)
```

In v1, CardCash is the only source, so the aggregate usually equals the latest valid CardCash observation. Keeping the cross-source shape now makes additional sources a v2 parser/config addition instead of a schema change.

### 7.5 Confidence

Per-observation confidence is set by the ingestion path:

- **High:** scraped successfully within the last 7 days from a source that returned a current `available` status.
- **Medium:** scraped 7-30 days ago, or scraped within 7 days but the source returned partial or stale-flagged data.
- **Low:** scraped 30+ days ago, or scraped but the source returned conflicting/ambiguous data.
- **None:** the observation cannot be used (parse failure, source unreachable, source explicitly returns no-data status).

Per-source confidence in the dashboard summarizes the highest-confidence currently-valid observation for that merchant from that source.

### 7.6 Cold-start and missing data

When no valid competitor observations exist for a merchant — no source has yet produced data, or all sources have produced only invalid observations — the merchant detail panel shows "no competitor data yet." The v1 recommendation is unaffected.

---

## 8. Confidence and operator review

For every merchant on every refresh, the algorithm produces:
- The four channel prices (or "No" / "No Data" sentinels)
- An overall confidence score: `min(ebay_confidence, config_completeness)`
- A delta vs. the most recent prior recommendation (computed at display time from the `price_recommendations` table)
- A max absolute delta over the last N recommendations (default N=5; computed at display time)

The dashboard sorts merchants by `delta_last_run` descending by default, with `max_abs_delta_over_n` as a secondary sortable column. Other sortable columns include merchant name, eBay confidence, and tier.

The operator scans the list, drills into individual merchants for detailed context, and applies prices outside the tool. The tool does not track which prices the operator chose to apply, nor when. The system of record for "what the algorithm recommended on date X" is the `price_recommendations` table; the system of record for "what prices were actually published" remains outside this tool in v1.

---

## 9. Worked example

### 9.1 Home Depot, v1 eBay-only recommendation (`ebay_weight = 1.0`)

Home Depot, March 2022 inputs:
- `ebay_sell_pct` = 0.92 (assumed for example)
- `ebay_differential` = 0.045 (Competitive default)
- `in_store_margin` = 0.25 (T24 row — Home Depot's actual config)
- `in_mail_margin` = 0.07 (Competitive row)
- `e_bonus` = 0.08
- `electronic_eligible` = true
- `ebay_weight = 1.0` (locked in v1)

Step-by-step:
- `online_sell = 0.92 - 0.045 = 0.875` -> list at **87.5%**
- `in_mail_buy = 0.875 - 0.07 - 0.03 - 0.02 - 0.03 = 0.725` -> pay **72.5%** for mail-in
- `in_store_buy = 0.875 - 0.25 - 0.03 - 0.03 - 0.048 = 0.517` -> pay **51.7%** for in-store
- `electronic_buy = 0.725 - 0.08 = 0.645` -> pay **64.5%** for electronic redemption

A customer with a $100 Home Depot card receives:
- $72.50 if mailed in
- $64.50 if redeemed electronically
- $51.70 if walked into a storefront

Zeal then resells at $87.50 on its storefront or routes to eBay at ~$92 net of fees.

### 9.2 Home Depot, CardCash reference data

Suppose CardCash's most recent observation for Home Depot:
- `competitor_in_mail_buy_pct` = 0.74
- `competitor_electronic_buy_pct` = 0.68
- `competitor_online_sell_pct` = null

In v1, these values appear on the merchant detail page as reference-only context. They do not change the recommendation above. In v2, exposing a non-1.0 `ebay_weight` would allow the existing blending path in §5.7 to incorporate these observations.

---

## 10. What v1 explicitly does *not* do

- **Does not pull data from competitor sites beyond CardCash.** Raise, Cardpool, and GiftCardGranny ingestion are deferred.
- **Does not use competitor observations in recommendations.** Competitor data is reference-only in v1.
- **Does not auto-publish prices anywhere.** All algorithm output is read-only display in the dashboard.
- **Does not track operator decisions.** No record of which recommendations the operator applied to the storefront and when. The `price_recommendations` table records what the algorithm output; what the operator did with it is outside this tool's scope in v1.
- **Does not run on a schedule.** Refresh is on-demand only. The operator clicks a button when he wants new pricing data.
- **Does not edit merchant configuration in-app.** Merchant config is seeded from the spreadsheet on initial install; changes in v1 require direct database edit. v2 introduces a config editor.
- **Does not surface `ebay_weight` to the operator.** The field exists in the schema and the engine reads it, but v1 always operates at 1.0. v2 adds the per-merchant slider.
- **Does not flag merchants for risk.** No `risk_status` field in v1. v2 reintroduces it once a config editor exists.
- **Does not change the operator's tier assignments.** Tier is descriptive metadata.
- **Does not use Zeal's internal sale history.** That's a v2 input.
- **Does not parse partial-balance cards.** Suspected partial-balance listings are excluded from the eBay average. v2 may parse them.
- **Does not handle non-USD currencies.** All values in USD.

---

## 11. v2 improvement roadmap (out of scope for v1)

Tracked here so they're not lost. Priority is approximate — each is a separately scoped project.

**High priority — small unlocks on infrastructure already in place:**

1. **Per-merchant `ebay_weight` slider** — surface the existing engine parameter in the merchant detail UI. Lets the operator dial in competitor influence per merchant. The engine code already supports this; v2 work is purely UI.
2. **Competitor-aware recommendations** — the same UI change as item 1; the algorithmic effect is that competitor data flows into the recommendation via the existing blending path.
3. **Operator action logging** — reintroduce `published_prices` and `operator_actions` tables (or equivalents) once the operator's workflow proves stable enough to know what's worth logging. Probably tied to the website integration, since "published" means something concrete in that context.
4. **Risk / watchlist flag** — `risk_status` field with an editor UI. Operator-curated metadata for merchants requiring extra attention.
5. **Config editor** — first-class UI for editing per-merchant config (margins, e-bonus, regexes, eBay differential). Currently only seeding-from-spreadsheet supports this.

**Medium priority — algorithmic improvements:**

6. **Recency-weighted eBay average** — exponential decay over the 90-day window so recent sales count more.
7. **Outlier removal beyond range checks** — median absolute deviation filter to drop statistically anomalous listings before averaging.
8. **Partial-balance parsing** — parse the face value from partial-balance eBay listings and include them in the average rather than excluding them.
9. **Override reason codes** — structured dropdown of common override reasons alongside free-text notes (depends on item 3).
10. **Internal sale history as input** — Zeal's own buy/sell history as a stronger signal than eBay for high-volume merchants.

**Lower priority — operational and ecosystem:**

11. **Additional competitor sources** — Raise, Cardpool, GiftCardGranny ingestion paths. Each follows the `CompetitorSource` protocol; new sources are a config and a parser, not an architectural change.
12. **Per-source `competitor_electronic_markdown`** — per-source tuning if observed competitor behavior diverges materially across sources.
13. **Automated risk / bankruptcy monitoring** — alert when a merchant's eBay price drops abnormally fast (early warning of retailer trouble).
14. **Tier intent vs. drift audit** — one-time review of every merchant's per-merchant config against tier defaults; corrections logged. See `spreadsheet_recon.md` §11.
15. **Drift-audit dashboard** — surface the tier-vs-margin-row drift in the UI for interactive review.

**Architectural North Star (out of scope, but the design protects feasibility):**

16. **Website integration** — the rebuilt Zeal Cards storefront imports the engine directly and runs scheduled price refreshes. The pure-function engine boundary in `pricing/` is preserved in v1 specifically so this remains a small project rather than a rewrite.
17. **Auto-publish for high-confidence small changes** — once item 16 lands, low-stakes updates can bypass operator review entirely.

---

## 12. Open questions (to be resolved before/during build)

These do not block writing the spec but should be tracked:

- **Q1.** Is the March 2022 `InputsandMargins` snapshot still current, or have any of the global constants (eBay fees, PayPal, postage, bad-debt rates) changed? *Owner: ask the operator.*
- **Q2.** What is the current full merchant list at Zeal? The spreadsheet has ~225 active rows but the project goal is exhaustive coverage. *Owner: pull from Zeal systems.*
- **Q3.** Are the per-merchant margin choices in the spreadsheet deliberate or drift? Answer informs whether the v2 audit (§11.14) is high or low priority. The recon confirmed drift exists (Home Depot row 11 mixes T24 and Competitive margin rows; bankrupt rows 280-283 reference stale tier rows). *Owner: ask the operator, but does not block v1.*
- **Q4.** ~~What identifier scheme should `merchant_id` use?~~ **Resolved:** lowercase ASCII slug of `merchant[_subtype][_qualifier]` form. See decisions_log.md 2026-05-02.
- **Q5.** ~~Should the dashboard display prices as percentages (e.g. 87.5%) or dollar amounts (e.g. "$0.875 per $1 face")?~~ **Resolved:** operator confirmed percentages are fine. No dollar-amount conversion layer needed in v1. See decisions_log.md 2026-05-03.

---

## 13. Acceptance criteria for v1

The v1 algorithm is considered correct when:

1. For every merchant in the golden test fixture (`tests/fixtures/spreadsheet_baseline.json`), given the spreadsheet's eBay sell % input and the per-merchant config extracted from the spreadsheet, the v1 system produces output prices matching the spreadsheet to within +/-0.001 (rounding tolerance). Faithful-port property holds.
2. All edge cases in §5.5 produce the documented sentinels (`"No"`, `"No Data"`).
3. The engine accepts a `CompetitorAggregate` argument and a per-merchant `ebay_weight`; with `ebay_weight = 1.0` the engine output is mathematically equivalent to the eBay-only path regardless of the competitor input. (Verified by tests; the v2 unlock is purely UI.)
4. A regression test suite exercises at least one merchant per tier x per electronic-eligibility x per merch-credit-variant combination.
