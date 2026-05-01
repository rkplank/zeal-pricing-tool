# Zeal Cards Pricing Algorithm — v1 Specification

**Status:** Draft for review
**Owner:** [your name]
**Last updated:** 2026-05-01
**Source of truth:** `GiftCardPricingData_2025.xlsx` (PricingSheet, InputsandMargins) — March 2022 baseline

---

## 1. Purpose

This document specifies the v1 pricing algorithm for the Zeal Cards pricing tool. The tool is a decision-support dashboard used by one operator (the owner) to set buy and sell prices for gift cards. It is not an automated pricing system; the operator retains full pricing authority and the algorithm produces *recommendations*.

v1 is a **faithful port** of the existing spreadsheet logic. The intent is that for any merchant, given the same eBay sell input and the same per-merchant configuration, the v1 system produces the same Buy and Sell prices the spreadsheet produces. Improvements are tracked separately in §10 and explicitly out of v1 scope.

---

## 2. Glossary

| Term | Meaning |
|---|---|
| **Face value** | The dollar value loaded on the gift card (e.g. a $100 Home Depot card has $100 face value). |
| **eBay Sell %** | The fraction of face value at which a card sells on eBay, computed from sold listings. The market price ground truth. A merchant trading at 92% means a $100 card sells for $92 on eBay. |
| **Online Sell %** | The fraction Zeal lists the card for on its own storefront. Slightly above eBay net (after eBay fees) — see §5. |
| **In-Store Buy %** | The fraction Zeal pays a customer who walks into a physical location with a card. |
| **In-Mail Buy %** | The fraction Zeal pays a customer who mails the card in. |
| **Electronic Buy %** | The fraction Zeal pays a customer who submits the card code online (no physical card transfer). |
| **Margin** | Zeal's gross-profit cushion on a transaction, expressed as a fraction of face value. Set per merchant by the operator. |
| **Tier** | A merchant grouping label (T24 / C / Z / NC) used as a default suggester. Not a hard rule — see §3. |
| **Channel** | One of the four price types: in-store buy, in-mail buy, electronic buy, online sell. |

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
| `e_bonus` | float \| null | Fraction added back when customer chooses electronic redemption. `null` = electronic not offered. |
| `ebay_differential` | float | Difference between Zeal's online sell and eBay sell — see §5 |
| `electronic_eligible` | bool | If false, Electronic Buy = "No" regardless of inputs |
| `merch_credit_variant` | bool | True for merchant credit / store credit / no-receipt cards (priced separately) |
| `notes` | string | Free-text operator notes |

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
| `in_store_bad_debt` | 0.048 | B8 | Fraction of face value lost to fraud/empty cards on in-store buys |
| `in_mail_bad_debt` | 0.02 | B9 | Same for in-mail buys |
| `online_bad_debt` | 0.05 | B10 | Same for online (electronic) buys |

All constants are operator-editable through the tool. Changes are versioned with timestamp and operator note.

---

## 5. Output computation

For each merchant on each refresh, the algorithm computes four values: `online_sell`, `in_mail_buy`, `in_store_buy`, `electronic_buy`. All are fractions of card face value (e.g. 0.78 = 78% = pay $78 on a $100 card).

### 5.1 Online Sell

```
online_sell = ebay_sell_pct − ebay_differential
```

Where `ebay_differential` is from the merchant's config. The differential exists because Zeal's online store doesn't pay eBay fees, so Zeal can list slightly cheaper than eBay net while still capturing more margin. Spreadsheet uses two values:
- `0.045` — competitive merchants
- `0.025` — Zen-Only and No-Competition merchants

In v1 every merchant carries its own value; the two above are defaults for new merchants.

### 5.2 In-Mail Buy

```
in_mail_buy = online_sell − in_mail_margin − paypal_sell_costs − in_mail_bad_debt − online_store_postage_costs
```

Reading the formula: take the price Zeal can sell at, subtract the operator's chosen profit cushion, subtract the cost to process the sale (PayPal), subtract expected fraud loss on mailed-in cards, subtract postage to ship the resulting sale.

### 5.3 In-Store Buy

```
in_store_buy = online_sell − in_store_margin − paypal_sell_costs − online_store_postage_costs − in_store_bad_debt
```

Same structure as in-mail buy, but uses the in-store margin and the in-store bad-debt rate. Note that bad debt is higher for in-store (4.8%) than in-mail (2.0%) — reflecting that walk-in customers present a higher fraud rate than mail-in customers in Zeal's experience.

### 5.4 Electronic Buy

```
if not electronic_eligible:
    electronic_buy = "No"
else:
    electronic_buy = in_mail_buy − e_bonus
```

The e-bonus is *subtracted* from in-mail buy, meaning the customer is paid *less* for electronic redemption than for mailing in the card. This is counterintuitive at first — why pay less for the cheaper channel? — but it's a deliberate channel-mix incentive: the operator wants customers to mail cards in (lower fraud, higher conversion in his experience) and prices electronic less attractively to nudge them. The "bonus" naming in the spreadsheet refers to it being a bonus *to Zeal's margin*, not to the customer.

Spreadsheet uses three e-bonus values:
- `0.08` — competition exists
- `0.13` — no competition
- `0.17` — special cases (rare)

In v1 every merchant carries its own value.

### 5.5 Edge case: card not electronically redeemable

When `electronic_eligible` is false, Electronic Buy is reported as the literal string `"No"`. The dashboard renders this as a non-numeric badge.

### 5.6 Edge case: missing eBay data

When `ebay_sell_pct` is null (no valid observations), all four output prices are reported as `"No Data"`. The dashboard surfaces this as an alert and the operator must make a judgment call.

This is conservative — the v1 algorithm refuses to extrapolate. v2 may add fallback strategies (use last known price with decay, use a sister merchant's price, etc.).

### 5.7 Edge case: low eBay confidence

When `ebay_sample_size < 10` or `ebay_data_freshness_days > 90`, prices are still computed but flagged as low-confidence. The dashboard renders them with a yellow indicator and the operator is expected to verify. This matches the spreadsheet's "highlight in red" rule for the same condition.

---

## 6. eBay sell percentage computation

The spreadsheet's rule (RFP §I) is: average the 10 most recent valid sold listings within the last 3 months. Compute `sum(value) / sum(price)` across the 10. Report the result.

v1 implements this rule faithfully, with one upgrade and several housekeeping clarifications.

### 6.1 Data source

eBay Browse API, sold listings filter, US location only, sorted by end date descending. Application for API access is a v1 prerequisite (see project plan §3).

### 6.2 Validity filters

A sold listing is valid for the average when:
- Sale date ≤ 90 days ago
- Card has non-zero loaded value
- Listing is a standalone gift card (not a bundle, not a coupon, not a collectible)
- Card matches the target merchant (resolution rules in §6.5)
- Total price (winning bid + shipping) is positive
- Listing is for a regular gift card or merchandise/store credit (per RFP, both are in scope)

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

## 7. Confidence and operator review flow

For every merchant on every refresh, the algorithm produces:
- The four channel prices (or "No" / "No Data" sentinels)
- An overall confidence score: `min(ebay_confidence, config_completeness)`
- A delta vs. the previously recommended price
- A delta vs. the currently published price (if known)

The dashboard sorts merchants by review priority:
1. **High priority** — large delta (>2pp) from current published price, or confidence dropped to low/none, or bankruptcy-risk flag tripped (v2)
2. **Medium priority** — small delta (0.5–2pp) from current published price
3. **Low priority** — no significant change

The operator can accept (publish), override (set a different price with optional reason), or skip (no change). Every action is logged. Override reasons are free-text and become training data for v2.

---

## 8. Worked example

Home Depot, March 2022 inputs:
- `ebay_sell_pct` = 0.92 (assumed for example)
- `ebay_differential` = 0.045 (Competitive default)
- `in_store_margin` = 0.25 (T24 row — Home Depot's actual config)
- `in_mail_margin` = 0.07 (Competitive row)
- `e_bonus` = 0.08
- `electronic_eligible` = true

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

---

## 9. What v1 explicitly does *not* do

- **Does not pull data from CardCash, Raise, or other competitor sites.** The spreadsheet logic is entirely eBay-driven. Competitor data is collected separately as a sanity check but is not an algorithm input in v1.
- **Does not auto-publish prices.** All output is recommendations for the operator dashboard.
- **Does not change the operator's tier assignments.** Tier is descriptive metadata.
- **Does not use Zeal's internal sale history.** That's a v2 input.
- **Does not detect bankruptcy risk or unusual eBay price movements.** v2.
- **Does not handle non-USD currencies.** All values in USD.
- **Does not handle partial-balance cards.** All assumes full face value.
- **Does not learn from operator overrides.** It logs them; learning is v2.

---

## 10. v2 improvement roadmap (out of scope for v1)

Tracked here so they're not lost. Each is a separate scoped project after v1 stabilizes.

1. **Recency-weighted eBay average** — exponential decay over the 90-day window so a sale from yesterday counts more than one from 89 days ago.
2. **Outlier removal** — median absolute deviation filter to drop obvious garbage listings before averaging.
3. **Competitor data integration** — CardCash, Raise, GiftCardGranny scrapers feeding a sanity-check layer and (possibly) the algorithm itself.
4. **Internal sale history as input** — Zeal's own buy/sell transaction history as a stronger signal than eBay for high-volume merchants.
5. **Dynamic tier assignment** — auto-recompute tier based on observed competitor presence and eBay liquidity.
6. **Volume-weighted spreads** — tighter margins for top-revenue merchants, wider for long tail.
7. **Bankruptcy / risk monitoring** — alert when a merchant's eBay price drops abnormally fast (early warning of retailer trouble).
8. **Override-driven learning** — analyze logged operator overrides to identify systematic algorithm gaps and propose config or formula changes.
9. **Auto-publish for high-confidence small changes** — bypass operator review for low-stakes updates, freeing time for the high-stakes ones.
10. **Tier intent vs drift audit** — a one-time review with the operator of every merchant's per-merchant config to identify deliberate choices vs accidental drift, with corrections logged.
11. **Auto-publish to website** — direct integration with the rebuilt Zeal storefront when ready.

---

## 11. Open questions (to be resolved before/during build)

These do not block writing the spec but should be tracked:

- **Q1.** Is the March 2022 `InputsandMargins` snapshot still current, or have any of the global constants (eBay fees, PayPal, postage, bad-debt rates) changed? *Owner: ask the operator.*
- **Q2.** What is the current full merchant list at Zeal? The spreadsheet has ~225 active rows but the project goal is exhaustive coverage. *Owner: pull from Zeal systems.*
- **Q3.** Are the per-merchant margin choices in the spreadsheet deliberate or drift? Answer informs whether the v2 audit (§10.10) is high or low priority. *Owner: ask the operator, but does not block v1.*
- **Q4.** What identifier scheme should `merchant_id` use? Slug from display name is the obvious default; confirm there are no namespace conflicts (e.g. the four Home Depot variants in the spreadsheet).
- **Q5.** Does the operator want override reasons to be free-text or a dropdown of common reasons? Free-text is more flexible; dropdown is faster to fill out daily.

---

## 12. Acceptance criteria for v1

The v1 algorithm is considered correct when:

1. For every merchant in `PricingSheet` rows 3–230 of the source spreadsheet, given the spreadsheet's eBay sell % input and the per-merchant config extracted from the formulas, the v1 system produces output prices matching the spreadsheet to within ±0.001 (rounding tolerance).
2. All edge cases in §5.5–§5.7 produce the documented sentinels.
3. The operator can edit any merchant's configuration through the dashboard without touching code.
4. Every operator action (accept, override, skip) is logged with timestamp.
5. A regression test suite exercises at least one merchant per tier × per electronic-eligibility × per merch-credit-variant combination.
