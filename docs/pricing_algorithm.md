# Zeal Cards Pricing Algorithm — v1 Specification

**Status:** Draft for review — v1 scope expanded 2026-05-04
**Owner:** [your name]
**Last updated:** 2026-05-04
**Source of truth:** `GiftCardPricingData_2025.xlsx` (PricingSheet, InputsandMargins) — March 2022 baseline

---

## 1. Purpose

This document specifies the v1 pricing algorithm for the Zeal Cards pricing tool. The tool is a decision-support dashboard used by one operator (the owner) to set buy and sell prices for gift cards. It is not an automated pricing system; the operator retains full pricing authority and the algorithm produces *recommendations*.

v1 has two design properties that work together:

**Faithful port at default configuration.** Given the same eBay sell input, the same per-merchant configuration, and the default `ebay_weight = 1.0`, the v1 system produces the same Buy and Sell prices the spreadsheet produces. Phase 1 golden tests verify this property over 281 baseline merchant records. The faithful-port property exists to anchor operator trust: the system on day one behaves exactly like the workflow being replaced.

**Extension via competitor blending and improved data hygiene.** When the operator dials `ebay_weight` below 1.0 for a given merchant, that merchant's recommendation incorporates competitor-derived signal alongside the eBay-derived signal. v1 also extends the eBay validity filters beyond the original spreadsheet rules (§6.2), adds operator-controlled risk flagging at the merchant level (§4.1), and exposes a structured formula breakdown for every recommendation (§5.6).

Improvements that materially change the algorithm beyond the above are tracked in §11 and explicitly out of v1 scope.

---

## 2. Glossary

| Term | Meaning |
|---|---|
| **Face value** | The dollar value loaded on the gift card (e.g. a $100 Home Depot card has $100 face value). |
| **eBay Sell %** | The fraction of face value at which a card sells on eBay, computed from sold listings. The market price ground truth. A merchant trading at 92% means a $100 card sells for $92 on eBay. |
| **Online Sell %** | The fraction Zeal lists the card for on its own storefront. Computed from eBay-derived signal, optionally blended with competitor-derived signal per the merchant's `ebay_weight`. See §5 and §7. |
| **In-Store Buy %** | The fraction Zeal pays a customer who walks into a physical location with a card. |
| **In-Mail Buy %** | The fraction Zeal pays a customer who mails the card in. |
| **Electronic Buy %** | The fraction Zeal pays a customer who submits the card code online (no physical card transfer). |
| **Margin** | Zeal's gross-profit cushion on a transaction, expressed as a fraction of face value. Set per merchant by the operator. |
| **Tier** | A merchant grouping label (T24 / C / Z / NC) used as a default suggester. Not a hard rule — see §3. |
| **Channel** | One of the four price types: in-store buy, in-mail buy, electronic buy, online sell. |
| **Competitor Sell %** | The fraction at which a competitor is currently buying or selling a card, expressed as a fraction of face value. Per-source, refreshed less frequently than eBay. See §7. |
| **Blended recommendation** | A channel price computed as a weighted combination of the eBay-derived recommendation and the competitor-derived recommendation, weighted by the merchant's `ebay_weight`. When `ebay_weight = 1.0`, the blended recommendation equals the eBay-only recommendation. |
| **eBay Weight** | A per-merchant float in `[0, 1]` controlling how much of the recommendation comes from eBay vs competitor signal. Default 1.0 (eBay-only). Operator-tunable. |

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

The intent is that more competition → tighter margin (compete on price), less competition → wider margin (capture more profit per card).

**Important finding from analysis of the spreadsheet:** In practice, formulas do not strictly follow the tier label. Within the same tier, individual merchants reference different margin rows in `InputsandMargins`. For example, in the Competitive tier:
- Home Depot uses the **T24 in-store margin** (25%)
- Lowe's uses the **Competitive in-store margin** (25%)
- Disney uses the **Zen-Only in-store margin** (29%)
- Massage Envy uses the **No-Competition in-store margin** (30%)

This pattern recurs across the in-mail margin, e-bonus, and eBay differential as well.

**Decision for v1:** Configuration is **per-merchant**, not per-tier. Each merchant carries its own margin configuration. The tier label is preserved as a descriptive field used to suggest defaults when adding a new merchant, but the algorithm reads margins from the merchant's own row.

This decision is conservative: it preserves whatever the operator intended (whether the per-merchant variations were deliberate or accidental drift) and gives him knob-level control going forward. **The question of intent versus drift is out of scope for v1**; the operator can review and correct individual merchant configurations through the tool's UI as he uses it.

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
| `ebay_weight` | float in [0, 1] | Default 1.0. Controls eBay vs competitor blending in §5. At 1.0, blended recommendation equals eBay-only recommendation (faithful-port behavior). At 0.0, blended recommendation is competitor-only. Intermediate values are linearly interpolated. |
| `risk_status` | enum {normal, watch, paused, no_buy} | Default `normal`. Operator-controlled risk flag. `watch` is display-only. `paused` and `no_buy` require explicit operator confirmation before the Accept button publishes a price (see architecture §7.1). Does not affect computation; it is a UI guard. |
| `risk_note` | string \| null | Free-text operator note explaining the risk status. Optional. |

### 4.2 Per-merchant market data (refreshed daily)

| Field | Type | Notes |
|---|---|---|
| `ebay_sell_pct` | float \| null | Fraction of face value at which the card sells on eBay. `null` if no valid data. |
| `ebay_sample_size` | int | Number of valid sold-listing observations used to compute `ebay_sell_pct`. |
| `ebay_data_freshness_days` | int | Days since most recent observation. |
| `ebay_confidence` | enum {high, medium, low, none} | Derived — see §6.4 |

### 4.3 Global constants (from `InputsandMargins`, March 2022)

These are channel costs and bad-debt rates. Stored as a single global config row, editable by the operator.

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
| `competitor_electronic_markdown` | 0.05 | — | Per-source fallback markdown applied when a competitor's electronic-specific buy price is unavailable but mail-side data exists. See §5.4. Provisional; refined as competitor data accumulates. |

> Note: `ebay_differential` (B23 competitive = 4.5%, B24 Zen/NoComp = 2.5%) is itself derived from the constants above:
> - `B23 = ebay_sale_costs + ebay_postage_costs − online_sell_bonus_competitive − online_store_postage_costs`
> - `B24 = ebay_sale_costs + ebay_postage_costs − online_sell_bonus_zen_nocomp − online_store_postage_costs`
>
> v1 stores the differential as a per-merchant value (faithful to the spreadsheet's encoding). v2 may compute it dynamically from the components plus a per-merchant tier choice.

All constants are operator-editable through the tool. Changes are versioned with timestamp and operator note.

### 4.4 Per-merchant competitor data (refreshed less frequently than eBay)

Competitor observations are pulled from each active competitor source on a configurable cadence (default: weekly per source, vs daily for eBay). Each competitor source produces buy and/or sell percentages per merchant.

| Field | Type | Notes |
|---|---|---|
| `source_name` | enum {cardcash, raise, cardpool, gcg, …} | Identifies the competitor source. v1 ships with CardCash; Raise is the second planned scraper. Cardpool and GiftCardGranny are deferred per decisions_log.md 2026-05-04. |
| `merchant_id` | string | The Zeal merchant this observation refers to. |
| `channel` | enum {buy_mail, buy_electronic, sell, marketplace_sell} | Most competitors expose buy-side prices (what they pay sellers). Sell-side prices (what they list at) are less commonly available. |
| `price_pct` | float | Fraction of face value. |
| `availability` | enum {available, unavailable, no_data} | Whether the source is currently buying/selling this merchant. |
| `confidence` | enum {high, medium, low, none} | Per-source, per-observation. Independent of eBay confidence. |
| `observed_at` | timestamp | When the observation was captured. |
| `source_url` | string \| null | Link to the source page, for operator verification. |

**Source-to-channel mapping:** competitor data informs three of the four Zeal channels:

- `online_sell` — informed by competitor sell-side data where available, or competitor buy-side data adjusted by an estimated competitor margin where sell-side is not available.
- `in_mail_buy` — informed by competitor `buy_mail` data directly.
- `electronic_buy` — informed by competitor `buy_electronic` data directly, or by `buy_mail` data with the `competitor_electronic_markdown` constant applied where electronic-specific data is unavailable.

The `in_store_buy` channel has no competitor analogue (no major competitor operates physical storefronts) and is computed from the eBay-derived value only, regardless of `ebay_weight`. The blending formula in §5 reflects this asymmetry.

**Cold-start behavior:** when no competitor observations exist for a merchant, the competitor signal is `null` and the blended recommendation falls back to the eBay-only recommendation regardless of `ebay_weight`. v1 launch behavior is operationally equivalent to the spreadsheet on day one for every merchant; competitor blending becomes meaningful as competitor data accumulates.

---

## 5. Output computation

For each merchant on each refresh, the algorithm computes four channel recommendations: `online_sell`, `in_mail_buy`, `in_store_buy`, `electronic_buy`. Each is a fraction of card face value (e.g. 0.78 = 78% = pay $78 on a $100 card).

The computation has three stages:

1. **eBay-only path** — compute each channel from eBay-derived signal alone, using the spreadsheet's formulas. This is the faithful-port behavior and is the complete recommendation when `ebay_weight = 1.0`.
2. **Competitor-only path** — compute each channel from competitor-derived signal alone, where competitor data is available. The `in_store_buy` channel is excluded from this path (no competitor analogue, per §4.4).
3. **Blending** — combine the two paths using the merchant's `ebay_weight`. When competitor data is unavailable (cold-start, missing source coverage), the blended recommendation falls back to the eBay-only path.

Each channel below is specified as eBay-only path, competitor-only path, and blending rule.

### 5.1 Online Sell

**eBay-only path:**
```
if online_sell_override is not None:
    online_sell_ebay = online_sell_override
elif ebay_sell_pct is None:
    online_sell_ebay = "No Data"
else:
    online_sell_ebay = ebay_sell_pct − ebay_differential
```

`online_sell_override` is set for "Pattern A" merchants (~25 local NC-tier merchants where eBay has no useful sold-listing data and the operator manually sets a storefront price). When set, the eBay path is bypassed entirely.

Otherwise, for normal merchants: take eBay's market price and subtract the `ebay_differential` from the merchant's config. The differential exists because Zeal's online store doesn't pay eBay fees, so Zeal can list slightly cheaper than eBay net while still capturing more margin. Two values exist in practice: 4.5% (competitive/T24) and 2.5% (Zen-Only/NoComp). In v1 every merchant carries its own value.

**Competitor-only path:**
```
if competitor_online_sell_pct is None:
    online_sell_competitor = None
else:
    online_sell_competitor = competitor_online_sell_pct
```

`competitor_online_sell_pct` is the aggregated competitor sell-side signal for this merchant per §7. When no competitor data is available, the competitor path returns `None` and blending falls back to eBay-only.

**Blending:**
```
if online_sell_competitor is None or online_sell_ebay == "No Data":
    online_sell = online_sell_ebay
else:
    online_sell = ebay_weight * online_sell_ebay + (1 − ebay_weight) * online_sell_competitor
```

When the eBay path returns `"No Data"` and competitor data exists, the blended value is not computed from competitor-only — the recommendation remains `"No Data"`. This is conservative: a merchant with no eBay data is one where the operator should be cautious, and substituting a competitor-only number could mislead. v2 may revisit this for merchants where competitor data is high-confidence.

### 5.2 In-Mail Buy

**eBay-only path:**
```
if not in_mail_eligible:
    in_mail_buy_ebay = "No"
elif online_sell_ebay == "No Data":
    in_mail_buy_ebay = "No Data"
else:
    in_mail_buy_ebay = (
        online_sell_ebay
        − in_mail_margin
        − paypal_sell_costs
        − in_mail_bad_debt
        − online_store_postage_costs
    )
```

When eligible and source data is present: take the price Zeal can sell at, subtract the operator's chosen profit cushion, subtract the cost to process the sale (PayPal), subtract expected fraud loss on mailed-in cards, subtract postage to ship the resulting sale.

**Competitor-only path:**
```
if not in_mail_eligible:
    in_mail_buy_competitor = "No"
elif competitor_in_mail_buy_pct is None:
    in_mail_buy_competitor = None
else:
    in_mail_buy_competitor = competitor_in_mail_buy_pct
```

The competitor path uses competitor `buy_mail` data directly — not derived from a competitor `online_sell` minus margin, because what the competitor charges on resale and what they pay on intake are independently observable, and the buy-side number is the more direct comparable.

**Blending:**
```
if in_mail_buy_ebay in ("No", "No Data"):
    in_mail_buy = in_mail_buy_ebay
elif in_mail_buy_competitor is None:
    in_mail_buy = in_mail_buy_ebay
else:
    in_mail_buy = ebay_weight * in_mail_buy_ebay + (1 − ebay_weight) * in_mail_buy_competitor
```

### 5.3 In-Store Buy

The `in_store_buy` channel has no competitor analogue. The eBay-only path is the only path; blending is a no-op. The merchant's `ebay_weight` does not affect this channel.

```
if not in_store_eligible:
    in_store_buy = "No"
elif online_sell_ebay == "No Data":
    in_store_buy = "No Data"
else:
    in_store_buy = (
        online_sell_ebay
        − in_store_margin
        − paypal_sell_costs
        − online_store_postage_costs
        − in_store_bad_debt
    )
```

Same structure as in-mail buy in the eBay-only path, but uses the in-store margin and the in-store bad-debt rate. Bad debt is higher for in-store (4.8%) than in-mail (2.0%), reflecting that walk-in customers present a higher fraud rate than mail-in customers in Zeal's experience.

### 5.4 Electronic Buy

**eBay-only path:**
```
if not electronic_eligible:
    electronic_buy_ebay = "No"
elif electronic_buy_override is not None:
    electronic_buy_ebay = electronic_buy_override
elif in_mail_buy_ebay in ("No", "No Data"):
    electronic_buy_ebay = "No Data"
else:
    assert e_bonus is not None
    electronic_buy_ebay = in_mail_buy_ebay − e_bonus
```

The override path supports Home Depot eStore Credit, which is electronic-only with a hardcoded 0.65 payout. The override is checked **before** the in-mail dependency because eStore Credit has `in_mail_eligible = False` — without the override-first ordering, the merchant would never get an electronic price.

The e-bonus is *subtracted* from in-mail buy, meaning the customer is paid *less* for electronic redemption than for mailing in the card. This is a deliberate channel-mix incentive: the operator wants customers to mail cards in (lower fraud, higher conversion in his experience) and prices electronic less attractively to nudge them. The "bonus" naming in the spreadsheet refers to it being a bonus *to Zeal's margin*, not to the customer.

Spreadsheet uses three e-bonus values:
- `0.08` — competition exists (B19)
- `0.13` — no competition (B20)
- `0.17` — special: local/NC merchants in rows 250–294 (B21)

In v1 every merchant carries its own value. Note that `in_mail_buy_ebay` (eBay-only) is used here, not the blended `in_mail_buy`. The eBay-only path computes from the eBay-only mail price; the competitor path computes from competitor electronic data directly; blending happens once at the end.

**Competitor-only path:**
```
if not electronic_eligible:
    electronic_buy_competitor = "No"
elif electronic_buy_override is not None:
    electronic_buy_competitor = electronic_buy_override
elif competitor_electronic_buy_pct is not None:
    electronic_buy_competitor = competitor_electronic_buy_pct
elif competitor_in_mail_buy_pct is not None:
    electronic_buy_competitor = competitor_in_mail_buy_pct − competitor_electronic_markdown
else:
    electronic_buy_competitor = None
```

When electronic-specific competitor data is unavailable but mail-side data exists, the competitor path falls back to the competitor's mail-side price minus the global `competitor_electronic_markdown` constant (§4.3). This parallels the e_bonus logic on the eBay path but uses observed competitor behavior rather than Zeal's internal channel-mix incentive.

**Blending:**
```
if electronic_buy_ebay in ("No", "No Data"):
    electronic_buy = electronic_buy_ebay
elif electronic_buy_competitor is None:
    electronic_buy = electronic_buy_ebay
else:
    electronic_buy = ebay_weight * electronic_buy_ebay + (1 − ebay_weight) * electronic_buy_competitor
```

### 5.5 Edge cases

All edge cases from the original faithful-port specification carry forward. Each applies to the eBay-only path; the competitor path has its own equivalents handled inline above:

- **Channel ineligibility** (`*_eligible = False`): produces `"No"` sentinel on both paths and blending is skipped. The recommendation is `"No"`.
- **Missing eBay data with no override:** eBay path returns `"No Data"`; blending falls back to `"No Data"` regardless of whether competitor data exists (per §5.1 conservative rule).
- **Pattern A merchants** (`online_sell_override` set): eBay path uses the override directly. Competitor path runs normally. Blending applies.
- **Pattern B merchants** (`electronic_buy_override` set, currently Home Depot eStore Credit): both paths use the override; blending is a no-op.
- **Low eBay confidence** (`ebay_sample_size < 10` or `ebay_data_freshness_days > 90`): prices are still computed but flagged. Display rule unchanged.

A new edge case introduced by competitor blending:

- **Low competitor confidence:** competitor observations have their own per-source confidence (§4.4). Low-confidence competitor observations *do* enter the competitor-only path and the blended recommendation — they are not auto-excluded. The operator sees per-source confidence in the dashboard and can adjust `ebay_weight` if desired. This is the "less magic, more operator control" decision from decisions_log.md 2026-05-04.

### 5.6 Formula breakdown

The pricing engine returns, alongside each channel's final value, a structured breakdown communicating how the final value was reached. The breakdown is a sequence of `(label, value, sign)` tuples representing the components of the formula, in computation order.

For a normal blended recommendation, the breakdown for one channel includes: the eBay-only path components (each margin, fee, bad debt, postage subtraction), the eBay-only subtotal, the competitor-only path components (which competitor source(s) contributed), the competitor-only subtotal, the blending arithmetic, and the final value.

For sentinel results (`"No"`, `"No Data"`), the breakdown communicates the reason rather than a numeric formula. Examples: `channel_ineligible`, `no_ebay_data_and_override_unset`, `ebay_only_due_to_missing_competitor_data`.

The dashboard renders breakdowns on the merchant detail page as the worked formula shown in §9.

---

## 6. eBay sell percentage computation

The spreadsheet's rule (RFP §I) is: average the 10 most recent valid sold listings within the last 3 months. Compute `sum(value) / sum(price)` across the 10. Report the result.

v1 implements this rule faithfully, with extended validity filters and several housekeeping clarifications.

### 6.1 Data source

eBay Browse API, sold listings filter, US location only, sorted by end date descending. Application for API access is a v1 prerequisite (see project plan §3).

### 6.2 Validity filters

A sold listing is valid for the average when *all* of the following hold:

- Sale date ≤ 90 days ago
- Card has non-zero loaded value
- Listing is a standalone gift card (not a bundle, not a coupon, not a collectible)
- Card matches the target merchant (resolution rules in §6.5)
- Total price (winning bid + shipping) is positive
- Listing is for a regular gift card or merchandise/store credit (per RFP, both are in scope)
- Computed sell percentage falls in the range `[0.30, 1.10]`
- Listing title does not contain suspicious keywords: `coupon`, `coupons`, `bundle`, `lot`, `lots`, `collectible`, `collectibles`, `empty`, `zero balance`, `partial`, `not full balance`

Listings that fail any check are stored in `ebay_observations` with `validity_status = 'excluded'` and a populated `exclusion_reason` field naming the failed check. They are visible in the merchant detail page's excluded-observations table for operator review and debugging.

**Partial-balance handling:** v1 handles partial-balance cards by exclusion, not by parsing. Listings whose titles match partial-balance keyword patterns are excluded with `exclusion_reason = 'partial_balance_suspected'`. Parsing partial balances and including these observations in the average is deferred to v2 (§11).

The sell-percentage range and suspicious-keyword exclusions extend the original spreadsheet's filter rules, added per the 2026-05-04 scope expansion. The original spreadsheet relied on the operator's manual review of eBay search results for these classes of bad listing; v1 automates that review.

### 6.3 Aggregation

For the most recent N valid listings (N ≤ 10):
```
ebay_sell_pct = sum(price_with_shipping_i) / sum(face_value_i)
```

This is the spreadsheet's exact formula. Note this is *not* the simple average of per-listing percentages — it's volume-weighted by face value. A $500 card sale at 90% counts more than a $25 card sale at 90%. This is correct: it gives the price the *next* sale is most likely to settle at given recent market activity.

### 6.4 Confidence

| Sample size | Freshness (most recent listing) | Confidence |
|---|---|---|
| ≥ 10 | ≤ 30 days | High |
| ≥ 10 | 31–90 days | Medium |
| 5–9 | ≤ 90 days | Medium |
| 1–4 | ≤ 90 days | Low |
| 0 valid in 90 days | — | None (report "No Data") |

### 6.5 Merchant resolution

eBay listing titles are unstructured. Resolving "did this listing sell a Michael Kors card or a Michaels card" is a known hazard the original RFP calls out. v1 uses:
- A per-merchant **inclusion regex** (must match in title) and **exclusion regex** (must not match)
- Both stored on the merchant config row, editable by operator
- Fallback to manual review when match confidence is low

Default regexes are seeded from the merchant display name. Operator refines as needed. This is the area most likely to need ongoing tuning.

---

## 7. Competitor data aggregation

Competitor signal is computed independently per source, then aggregated across sources to produce the per-channel competitor inputs consumed by §5.

### 7.1 Data sources

v1 ships with one active competitor source: CardCash. Raise is the second planned scraper, integrated after CardCash has been validated against operator judgment for several refresh cycles. Cardpool and GiftCardGranny are deferred per decisions_log.md 2026-05-04.

Each source has its own ingestion path (HTTP scrape, structured CSV import, or manual entry). The ingestion mechanics are specified in `architecture.md`. The algorithm consumes competitor observations from `competitor_observations` rows regardless of how they got there.

### 7.2 Refresh cadence

Default cadence is weekly per source, vs daily for eBay. Competitor catalogs turn over more slowly than eBay listings, so daily refresh would produce mostly identical observations and waste scraper budget. The cadence is per-source and configurable.

Manual entries do not have a cadence; they are inserted whenever the operator adds them.

### 7.3 Per-source aggregation

For a given merchant, channel, and source: the competitor observation used in §5 is the most recent valid observation for that merchant/channel/source within the last 30 days. If no observation in that window exists, the source contributes nothing for that merchant/channel.

A "valid" observation has:
- `availability = 'available'`
- `confidence ≠ 'none'`
- `price_pct` in the range `[0.20, 1.20]` — wider than the eBay range because competitor sources occasionally list very low buy-side prices for low-demand merchants

Observations failing validity are retained in the database for audit but excluded from the aggregation.

### 7.4 Cross-source aggregation

When multiple sources produce valid observations for the same merchant and channel, the algorithm aggregates them as a confidence-weighted average:

```
weights = {high: 1.0, medium: 0.5, low: 0.25}
competitor_pct = sum(weight_i * price_pct_i) / sum(weight_i)
```

The result is a single per-channel competitor input fed into §5's blending. The per-source contributions are preserved in the structured breakdown (§5.6) so the operator can see which sources contributed at what weights.

### 7.5 Confidence

Per-observation confidence is set by the ingestion path:

- **High:** scraped successfully within the last 7 days from a source that returned a current `available` status.
- **Medium:** scraped 7–30 days ago, or scraped within 7 days but the source returned partial or stale-flagged data.
- **Low:** scraped 30+ days ago, or manual entry without a recent verification, or scraped but the source returned conflicting/ambiguous data.
- **None:** the observation cannot be used (parse failure, source unreachable, source explicitly returns no-data status).

Per-source confidence in the dashboard summarizes the highest-confidence currently-valid observation for that merchant from that source.

### 7.6 Cold-start and missing data

When no valid competitor observations exist for a merchant — no source has yet produced data, or all sources have produced only invalid observations — the competitor input is `null` for that merchant. §5's blending rules treat `null` as "fall back to eBay-only," making the recommendation operationally identical to the spreadsheet baseline. This is the expected state for most merchants in the first weeks of v1 operation.

---

## 8. Confidence and operator review flow

For every merchant on every refresh, the algorithm produces:
- The four channel prices (or "No" / "No Data" sentinels)
- An overall confidence score: `min(ebay_confidence, config_completeness)`
- A delta vs. the previously recommended price
- A delta vs. the currently published price (if known)

The dashboard sorts merchants by review priority:
1. **High priority** — large delta (>2pp) from current published price, or confidence dropped to low/none, or `risk_status` is `paused` or `no_buy`
2. **Medium priority** — small delta (0.5–2pp) from current published price, or `risk_status` is `watch`
3. **Low priority** — no significant change

The operator can accept (publish), override (set a different price with optional reason), or skip (no change). Every action is logged. Override reasons are free-text and become training data for v2.

---

## 9. Worked example

### 9.1 Home Depot, eBay-only (default ebay_weight = 1.0)

Home Depot, March 2022 inputs:
- `ebay_sell_pct` = 0.92 (assumed for example)
- `ebay_differential` = 0.045 (Competitive default)
- `in_store_margin` = 0.25 (T24 row — Home Depot's actual config)
- `in_mail_margin` = 0.07 (Competitive row)
- `e_bonus` = 0.08
- `electronic_eligible` = true
- `ebay_weight` = 1.0 (default — eBay-only)

Step-by-step:
- `online_sell = 0.92 − 0.045 = 0.875` → list at **87.5%**
- `in_mail_buy = 0.875 − 0.07 − 0.03 − 0.02 − 0.03 = 0.725` → pay **72.5%** for mail-in
- `in_store_buy = 0.875 − 0.25 − 0.03 − 0.03 − 0.048 = 0.517` → pay **51.7%** for in-store
- `electronic_buy = 0.725 − 0.08 = 0.645` → pay **64.5%** for electronic redemption

A customer with a $100 Home Depot card receives:
- $72.50 if mailed in (most attractive)
- $64.50 if redeemed electronically (next most attractive)
- $51.70 if walked into a storefront (lowest, due to higher fraud risk and immediate cash payout)

Zeal then resells at $87.50 on its storefront or routes to eBay at ~$92 net of fees.

### 9.2 Home Depot, blended (ebay_weight = 0.7)

Same merchant, same eBay inputs, same configuration — but the operator has adjusted `ebay_weight` to 0.7 and CardCash data has accumulated.

Suppose CardCash's most recent observation for Home Depot:
- `competitor_in_mail_buy_pct` = 0.74
- `competitor_electronic_buy_pct` = 0.68
- `competitor_online_sell_pct` = null (CardCash doesn't publish sell-side prices for most merchants)

**eBay-only path** (same as §9.1):
- `online_sell_ebay = 0.875`
- `in_mail_buy_ebay = 0.725`
- `in_store_buy_ebay = 0.517`
- `electronic_buy_ebay = 0.645`

**Competitor-only path:**
- `online_sell_competitor = null` (no sell-side competitor data for this merchant)
- `in_mail_buy_competitor = 0.74`
- `electronic_buy_competitor = 0.68`
- `in_store_buy_competitor` = N/A (no competitor analogue)

**Blending:**
- `online_sell = 0.875` (competitor null → falls back to eBay-only)
- `in_mail_buy = 0.7 × 0.725 + 0.3 × 0.74 = 0.5075 + 0.222 = 0.7295` → **73.0%**
- `in_store_buy = 0.517` (unaffected — no competitor analogue)
- `electronic_buy = 0.7 × 0.645 + 0.3 × 0.68 = 0.4515 + 0.204 = 0.6555` → **65.6%**

The blended recommendation is closer to what CardCash pays on the channels where competitor data exists, while preserving the spreadsheet-derived value where it doesn't.

---

## 10. What v1 explicitly does *not* do

- **Does not pull data from competitor sites beyond CardCash and (planned) Raise.** Cardpool and GiftCardGranny ingestion are deferred. The operator can manually enter observations from those sources via the admin import path if desired.
- **Does not auto-publish prices.** All output is recommendations for the operator dashboard. CSV export produces a file the operator downloads; no website integration.
- **Does not change the operator's tier assignments.** Tier is descriptive metadata.
- **Does not use Zeal's internal sale history.** That's a v2 input.
- **Does not detect bankruptcy risk or unusual eBay price movements automatically.** Manual `risk_status` flagging is supported in v1 (§4.1); automated detection is v2.
- **Does not parse partial-balance cards.** Suspected partial-balance listings are excluded from the eBay average. v2.
- **Does not handle non-USD currencies.** All values in USD.
- **Does not learn from operator overrides.** It logs them; learning is v2.
- **Does not adjust `ebay_weight` automatically based on confidence or any other signal.** Operator-set; the system displays inputs and lets the operator decide.

---

## 11. v2 improvement roadmap (out of scope for v1)

Tracked here so they're not lost. Each is a separate scoped project after v1 stabilizes.

1. **Recency-weighted eBay average** — exponential decay over the 90-day window so a sale from yesterday counts more than one from 89 days ago.
2. **Outlier removal beyond range checks** — median absolute deviation filter to drop statistically anomalous listings before averaging, beyond the keyword-based exclusions in §6.2.
3. **Additional competitor sources** — Cardpool and GiftCardGranny ingestion paths, after CardCash and Raise have been validated against operator judgment.
4. **Per-source `competitor_electronic_markdown`** — v1 uses a single global value; v2 may tune per-source if observed competitor behavior diverges materially.
5. **Internal sale history as input** — Zeal's own buy/sell transaction history as a stronger signal than eBay for high-volume merchants.
6. **Dynamic tier assignment** — auto-recompute tier based on observed competitor presence and eBay liquidity.
7. **Volume-weighted spreads** — tighter margins for top-revenue merchants, wider for long tail.
8. **Automated risk / bankruptcy monitoring** — alert when a merchant's eBay price drops abnormally fast (early warning of retailer trouble). Manual `risk_status` flag is in v1; automated detection is here.
9. **Override reason codes** — structured dropdown of common override reasons (price outlier, data freshness, operator hunch, etc.) alongside the existing free-text note, to enable aggregate analysis.
10. **Drift-audit dashboard** — surface the tier-vs-margin-row drift identified in spreadsheet_recon.md §11 in the UI so the operator can review and correct individual merchant configs interactively.
11. **Override-driven learning** — analyze logged operator overrides to identify systematic algorithm gaps and propose config or formula changes.
12. **Partial-balance parsing** — parse the face value from partial-balance eBay listings and include them in the average rather than excluding them.
13. **Auto-publish for high-confidence small changes** — bypass operator review for low-stakes updates, freeing time for the high-stakes ones.
14. **Tier intent vs drift audit** — a one-time review with the operator of every merchant's per-merchant config to identify deliberate choices vs accidental drift, with corrections logged. See spreadsheet_recon.md §11 for the Phase 1 categorization.
15. **Auto-publish to website** — direct integration with the rebuilt Zeal storefront when ready.

---

## 12. Open questions (to be resolved before/during build)

These do not block writing the spec but should be tracked:

- **Q1.** Is the March 2022 `InputsandMargins` snapshot still current, or have any of the global constants (eBay fees, PayPal, postage, bad-debt rates) changed? *Owner: ask the operator.*
- **Q2.** What is the current full merchant list at Zeal? The spreadsheet has ~225 active rows but the project goal is exhaustive coverage. *Owner: pull from Zeal systems.*
- **Q3.** Are the per-merchant margin choices in the spreadsheet deliberate or drift? Answer informs whether the v2 audit (§11.14) is high or low priority. The recon confirmed drift exists (Home Depot row 11 mixes T24 and Competitive margin rows; bankrupt rows 280–283 reference stale tier rows). *Owner: ask the operator, but does not block v1.*
- **Q4.** ~~What identifier scheme should `merchant_id` use?~~ **Resolved:** lowercase ASCII slug of `merchant[_subtype][_qualifier]` form. See decisions_log.md 2026-05-02.
- **Q5.** Does the operator want override reasons to be free-text or a dropdown of common reasons? Free-text is more flexible; dropdown is faster to fill out daily.
- **Q6.** ~~Should the dashboard display prices as percentages (e.g. 87.5%) or dollar amounts (e.g. "$0.875 per $1 face")?~~ **Resolved:** operator confirmed percentages are fine. No dollar-amount conversion layer needed in v1. See decisions_log.md 2026-05-03.

---

## 13. Acceptance criteria for v1

The v1 algorithm is considered correct when:

1. For every merchant in the golden test fixture (`tests/fixtures/spreadsheet_baseline.json`), given the spreadsheet's eBay sell % input, the per-merchant config extracted from the spreadsheet, and the default `ebay_weight = 1.0`, the v1 system produces output prices matching the spreadsheet to within ±0.001 (rounding tolerance). Faithful-port property holds at default configuration.
2. All edge cases in §5.5 produce the documented sentinels (`"No"`, `"No Data"`).
3. When `ebay_weight < 1.0` and competitor data is available, the blended output equals `ebay_weight * ebay_price + (1 − ebay_weight) * competitor_price` for each applicable channel.
4. When competitor data is absent (null), the blended output equals the eBay-only output regardless of `ebay_weight`.
5. The operator can edit any merchant's configuration through the dashboard without touching code.
6. Every operator action (accept, override, skip) is logged with timestamp.
7. A regression test suite exercises at least one merchant per tier × per electronic-eligibility × per merch-credit-variant combination.
