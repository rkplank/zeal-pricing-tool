# Historical Pricing Findings

Generated from:

- `docs/generated/historical_pricing_rows.json`
- `docs/generated/historical_workbook_inventory.json`
- `docs/historical_pricing_analysis.md`

This document is analysis only. It does not revise the v1 pricing algorithm, dashboard,
database schema, or golden baseline tests. Historical spreadsheet prices are operator
history, not current market data.

## Method Notes

The row artifact contains both `GiftCardPricingData_2025.xls` and
`GiftCardPricingData_2025.xlsx`. For year-level findings below, 2025 rows were
deduplicated by `(year, merchant_id)` with the `.xlsx` row preferred over the `.xls`
row. That gives 1,675 unique year/merchant rows across six available years:
2017, 2018, 2021, 2022, 2023, and 2025.

Important limitations:

- `.xls` files were read as cached cell values only. Formula references, margin-row
  provenance, and e-bonus provenance are not available without converting those files
  to `.xlsx` or using Excel automation.
- Merchant continuity is slug-based. Renames, punctuation changes, and grouped brands
  can look like adds/removes.
- Competitor data in this artifact is column/tab reconnaissance, not a validated
  competitor-history dataset.
- None of the historical values should be used as current eBay, CardCash, or Raise
  market data.

## Cross-Year Merchants

After deduping 2025, 212 normalized merchants appear in every available year:
2017, 2018, 2021, 2022, 2023, and 2025.

This stable set is useful for historical policy review because it avoids most
new-merchant and retired-merchant noise. Examples include Amazon, Apple, Best Buy,
Home Depot, Lowe's, Target, Walmart, Disney, Starbucks, Applebee's, Chipotle,
CVS, Kroger, Shell, Trader Joe's, Walgreens, Nike, Sephora, TJ Maxx-era rows where
the slug stayed continuous, and many restaurant/retail merchants.

Year-level unique merchant counts:

| Year | Unique merchants | Tier distribution |
|---:|---:|---|
| 2017 | 262 | T24 31, C 154, Z 57, NC 20 |
| 2018 | 264 | T24 30, C 161, Z 57, NC 16 |
| 2021 | 286 | T24 12, C 37, Z 174, NC 63 |
| 2022 | 286 | T24 12, C 38, Z 174, NC 62 |
| 2023 | 288 | T24 12, C 39, Z 175, NC 62 |
| 2025 | 289 | T24 12, C 39, Z 176, NC 62 |

The big structural break is between 2018 and 2021. Counts rise, but tier composition
changes much more than merchant count does.

## Added And Removed Merchants

2017 to 2018:

- Added 6: Adidas, Andiamo, Athleta, Loft, Ruth's Chris Steakhouse, Tropical
  Smoothie Cafe.
- Removed 4: Biggby Coffee, Goodrich Quality Theaters, Lone Star Steakhouse,
  Massage Green.

2018 to 2021:

- Added 70. This includes true additions plus many grouped or renamed rows:
  Mastercard, Visa, American Express, Ann Taylor / Loft, Athleta / BR / Gap / ON,
  Bass Pro Shops / Cabelas, Darden / Olive Garden / Longhorn Steakhouse, Foot
  Locker / Champs Sports, Office Depot / OfficeMax, Pottery Barn / Williams-Sonoma,
  Speedway - Food and Merch, Speedway - Fuel, TJ Maxx / Homegoods / Marshalls,
  Home Depot merch-credit variants, Lowe's merch-credit variant, Target Merch
  Credit, Menards Rebate, local merchants, and several restaurant groups.
- Removed 48. Many removals are probably replaced by grouped rows rather than true
  merchant exits: Mastercard variants, Visa variants, Bass Pro Shops/Cabela's as
  separate rows, Office Depot/Office Max as separate rows, Darden brands as separate
  rows, and similar patterns.

2021 to 2022:

- Added 0, removed 0.

2022 to 2023:

- Added 2: Delta, Uber.
- Removed 0.

2023 to 2025:

- Added 1: Safeway / Albertsons.
- Removed 0.

## Naming And Slug Continuity Issues

The 2018 to 2021 transition has the most continuity risk. Likely rename/grouping
examples:

| Earlier row | Later row | Interpretation |
|---|---|---|
| Mastercard variants | Mastercard | Multiple prepaid-card variants consolidated |
| Visa variants | Visa | Multiple prepaid-card variants consolidated |
| American Express (mygiftcard) | American Express | Brand cleanup |
| Ann Taylor, Loft | Ann Taylor / Loft | Grouped related brands |
| Athleta, Banana Republic, Gap, Old Navy | Athleta / BR / Gap / ON | Grouped Gap-family brands |
| Bass Pro Shops, Cabela's | Bass Pro Shops / Cabelas | Grouped related brands |
| Carrabba's, Flemings, Outback | Carrabba's Italian Grill / Flemings / Outback | Grouped restaurant brands |
| Darden, Olive Garden, Longhorn Steakhouse | Darden / Olive Garden / Longhorn Steakhouse | Grouped restaurant brands |
| Foot Locker, Champs Sports | Foot Locker / Champs Sports | Grouped related brands |
| Office Depot, Office Max | Office Depot / OfficeMax | Grouped related brands |
| Pottery Barn, Williams-Sonoma | Pottery Barn / Williams-Sonoma | Grouped related brands |
| Speedway | Speedway - Food and Merch; Speedway - Fuel | Split into product categories |
| TJ Maxx | TJ Maxx / Homegoods / Marshalls | Grouped related brands |
| Ulta Beauty | Ulta | Name cleanup |

Recommended treatment: build a manual `historical_merchant_aliases` analysis file
before any serious longitudinal trend work. Do not add aliases to the production DB
for v1.

## Tier Changes Over Time

There are 160 merchants with at least one tier change. Most are not one-off moves;
they reflect a broad reclassification after 2018.

First-observed to latest-observed transition counts:

| Transition | Count |
|---|---:|
| C to Z | 89 |
| C to NC | 19 |
| NC to Z | 11 |
| T24 to C | 10 |
| Z to C | 8 |
| Z to NC | 5 |
| NC to C | 4 |
| C to T24 | 4 |
| T24 to Z | 1 |

Notable examples:

- T24 to C: Home Depot, Lowe's, Target, Walmart, Best Buy, Kohl's, Nordstrom,
  Victoria's Secret, Bed Bath & Beyond.
- C to T24: Kroger, Shell, Trader Joe's, Jimmy John's.
- Z to C: Disney and iTunes are prominent examples.
- C to NC: AMC Theaters, Subway, Marriott, Brooks Brothers, Carter's, Cinemark,
  Fandango, Lane Bryant, Regal Entertainment Group, Ticketmaster.
- Z to NC: Family Dollar and Verizon.

Finding: tier is historical/operator metadata, not a reliable formula driver. This
supports the existing v1 decision to use per-merchant config rather than deriving
pricing behavior from tier labels.

## Channel Price Movement

For the 212 all-year merchants, comparing 2017 to deduped 2025:

| Channel | Merchants with values | Average change | Median change | Range |
|---|---:|---:|---:|---|
| eBay sell | 200 | -0.026 | -0.021 | -0.360 to +0.290 |
| online sell | 200 | +0.006 | +0.013 | -0.325 to +0.300 |
| in-mail buy | 200 | -0.047 | -0.044 | -0.344 to +0.267 |
| in-store buy | 200 | -0.034 | -0.032 | -0.372 to +0.293 |
| electronic buy | 126 | -0.069 | -0.062 | -0.324 to +0.187 |

Largest absolute movers by channel include:

- eBay sell: Jimmy John's, Spencer's Gifts, Old Country Buffet, Potbelly,
  Christopher & Banks, Mac, Arby's, Logan's Roadhouse, New York & Company, GNC.
- online sell: Jimmy John's, Old Country Buffet, Potbelly, Spencer's Gifts,
  Logan's Roadhouse, Christopher & Banks, Dollar Tree, Mac, Arby's.
- in-mail buy: Old Country Buffet, Spencer's Gifts, Jimmy John's, Potbelly, GNC,
  Mac, Arby's, New York & Company, Orvis, Tiffany.
- in-store buy: Jimmy John's, Spencer's Gifts, Old Country Buffet, Potbelly, Mac,
  Arby's, Christopher & Banks, New York & Company, GNC.
- electronic buy: Spencer's Gifts, Jimmy John's, GNC, Bravo! Cucina Italiana,
  movietickets.com, Mac, Lane Bryant, Brooks Brothers, Ticketmaster.

Interpretation: these changes show historical policy and cached spreadsheet state,
not live market truth. They are useful for picking pilot merchants that exercise
large-movement and edge-case behavior.

## Competitor Column Availability

Detected competitor structure:

| Year | Competitor columns/tabs detected | Usable merchant-level values in normalized rows |
|---:|---|---|
| 2017 | None | None |
| 2018 | `CardPoolCash` tab with merchant, CardCash buy, and in-mail buy-like columns | Not normalized into row artifact |
| 2021 | None | None |
| 2022 | None | None |
| 2023 | None | None |
| 2025 | `CC Sell` and `CC Buy` columns on `PricingSheet` | Only two `cardcash_sell` zero values; no non-null `cardcash_buy` |

Raise sell was not detected in any inspected year.

Conclusion: the generated artifacts do not contain enough usable competitor history
to draw merchant-level competitor conclusions. The 2018 `CardPoolCash` tab is the
best candidate for a separate competitor-history extraction pass, but it should be
treated as analysis tooling, not production ingestion.

## Merchants With Useful Competitor History

No merchant has useful competitor history in the normalized row artifact.

Reasons:

- 2018 has a separate `CardPoolCash` tab, but those rows were inventoried rather
  than normalized into `historical_pricing_rows.json`.
- 2025 has CardCash columns, but the normalized values are effectively empty:
  no `cardcash_buy` values and only zero `cardcash_sell` values for Target Merch
  Credit and Uber.

Useful next analysis would be a targeted parser for the 2018 `CardPoolCash` tab,
with tests around header/percentage normalization. That should remain outside the
production CardCash ingestion path.

## Sparse Or Missing Historical Data

Merchant year coverage:

| Number of available years | Merchant count |
|---:|---:|
| 6 | 212 |
| 5 | 6 |
| 4 | 68 |
| 2 | 48 |
| 1 | 5 |

Sparse one-year merchants:

- Athleta
- Loft
- Lone Star Steakhouse
- Massage Green
- Safeway / Albertsons

Two-year merchants are mostly renamed, grouped, or newly added rows rather than
necessarily weak merchants: old Mastercard/Visa variants, old Darden and Gap-family
brand rows, Delta, Uber, and several pre-2021 rows that were later grouped.

Common missing-data patterns:

- Electronic buy is often absent by design. In 2025, 77 merchants have no electronic
  buy value.
- eBay sell is missing for many local/manual-price rows. In 2025, 29 merchants lack
  eBay sell values in the artifact.
- Bankrupt/broken rows such as Avenue, Bebe, and Carson's remain visible as sparse
  or missing channel values and should not be used for live pilot validation.

## Recommended eBay Pilot Merchant Set

This set is for credential-day Marketplace Insights smoke validation and operator
review. It is not a recommendation to change v1 prices.

| Merchant | Rationale |
|---|---|
| Mastercard | T24 prepaid-card row; high face-value parsing and generic title risk |
| Visa | T24 prepaid-card row; similar to Mastercard but distinct title matching |
| Home Depot | High-volume core merchant; T24 to C historical tier change |
| Home Depot Merch Credit (No ID) | Merchandise-credit variant; should exercise title inclusion/exclusion caution |
| Home Depot eStore Credit | Electronic-only override pattern; confirms v1 edge handling stays separate from eBay discovery |
| Target | Core merchant; merch-credit sibling exists; useful for title disambiguation |
| Walmart | Core merchant; broad eBay supply and stable all-year history |
| Amazon | High-volume, high-price row; likely abundant sold listings but fraud/noise risk |
| Best Buy | Core electronics merchant; all-year history and T24 to C tier change |
| Apple | High-demand merchant with brand/title ambiguity risk |
| Starbucks | Common merchant with many small-denomination listings likely to test face-value extraction |
| Disney | Historical Z to C tier change; good test of high-demand entertainment/travel-adjacent listings |
| TJ Maxx / Homegoods / Marshalls | Grouped merchant; title matching should cover multiple brands without overmatching |
| Delta | Newer 2023 row; travel merchant and sparse history relative to all-year rows |
| Safeway / Albertsons | 2025-only row; useful cold-start/new-merchant pilot case |

Keep the pilot small enough to inspect manually. A good credential-day sequence is:
first run 5 obvious high-volume rows, inspect observations/exclusions, then run the
remaining 10 if title matching and face-value parsing look sane.

## v1, v2, Or Neither

Findings that should affect v1:

- None to the algorithm, DB schema, or dashboard behavior.
- Operationally, the pilot list above can inform credential-day smoke testing.

Findings that should affect v2:

- Build a manual historical alias map before trend analysis or config-drift review.
- Consider a separate analysis parser for the 2018 `CardPoolCash` tab if competitor
  history becomes useful for operator review.
- Use tier-change history to prioritize the v2 tier intent vs. drift audit, especially
  broad C-to-Z/C-to-NC moves and T24-to-C moves.
- Use sparse-history markers when designing any future config editor or merchant
  onboarding workflow.

Findings that should affect neither:

- Historical channel percentages should not change current recommendations.
- Historical eBay sell values should not seed live eBay observations.
- Empty or zero CardCash columns should not be interpreted as current competitor data.
- Renames/grouped rows should not become production merchant aliases until separately
  reviewed and approved.
