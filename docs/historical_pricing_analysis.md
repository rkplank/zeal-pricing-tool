# Historical Pricing Workbook Analysis

Generated: 2026-05-06T23:40:43Z

This is read-only reconnaissance. The extracted JSON artifacts live under `docs/generated/` and are not production database tables.

## Workbook Inventory

| Workbook | Format | Sheets | Likely pricing sheets | Used ranges |
|---|---:|---|---|---|
| GiftCardPricingData_2017.xls | xls | GadgetGift_Plan, PricingSheet, InputsandMargins, TopCards | PricingSheet | GadgetGift_Plan: R1C1:R297C32; PricingSheet: R1C1:R297C8; InputsandMargins: R1C1:R41C3; TopCards: R2C1:R41C6 |
| GiftCardPricingData_2018.xls | xls | GadgetGift_Plan, PricingSheet, CardPoolCash, InputsandMargins, TopCards | PricingSheet | GadgetGift_Plan: R1C1:R297C19; PricingSheet: R1C1:R749C7; CardPoolCash: R3C1:R295C6; InputsandMargins: R1C1:R39C3; TopCards: R2C1:R47C7 |
| GiftCardPricingData_2021.xls | xls | GadgetGift_Plan, PricingSheet, InputsandMargins, TopCards | PricingSheet | GadgetGift_Plan: R1C1:R296C5; PricingSheet: R1C1:R749C7; InputsandMargins: R1C1:R39C3; TopCards: R2C1:R47C7 |
| GiftCardPricingData_2022.xls | xls | GadgetGift_Plan, PricingSheet, InputsandMargins, TopCards | PricingSheet | GadgetGift_Plan: R1C1:R296C5; PricingSheet: R1C1:R749C10; InputsandMargins: R1C1:R39C3; TopCards: R2C1:R47C7 |
| GiftCardPricingData_2023.xls | xls | GadgetGift_Plan, PricingSheet, InputsandMargins, TopCards | PricingSheet | GadgetGift_Plan: R1C1:R296C5; PricingSheet: R1C1:R751C9; InputsandMargins: R1C1:R39C3; TopCards: R2C1:R47C7 |
| GiftCardPricingData_2025.xls | xls | GadgetGift_Plan, PricingSheet, InputsandMargins, TopCards | PricingSheet | GadgetGift_Plan: R1C1:R296C5; PricingSheet: R1C1:R752C9; InputsandMargins: R1C1:R39C3; TopCards: R2C1:R47C7 |
| GiftCardPricingData_2025.xlsx | xlsx | GadgetGift_Plan, PricingSheet, InputsandMargins, TopCards, MarginRefs | PricingSheet | GadgetGift_Plan: R1C1:R296C5; PricingSheet: R1C1:R752C9; InputsandMargins: R1C1:R39C3; TopCards: R2C1:R47C7; MarginRefs: R1C1:R296C7 |

## Merchant Counts By Year

| Year | Merchant rows | Unique normalized merchants | Likely pricing sheets |
|---:|---:|---:|---|
| 2017 | 262 | 262 | PricingSheet |
| 2018 | 264 | 264 | PricingSheet |
| 2021 | 286 | 286 | PricingSheet |
| 2022 | 286 | 286 | PricingSheet |
| 2023 | 288 | 288 | PricingSheet |
| 2025 | 578 | 289 | PricingSheet |

## Columns Available By Year

| Year | eBay sell | Online sell | In-mail buy | In-store buy | Electronic buy | Tier | CardCash buy | CardCash sell | Raise sell |
|---:|---|---|---|---|---|---|---|---|---|
| 2017 | yes | yes | yes | yes | yes | yes | no | no | no |
| 2018 | yes | yes | yes | yes | yes | yes | yes | no | no |
| 2021 | yes | yes | yes | yes | yes | yes | no | no | no |
| 2022 | yes | yes | yes | yes | yes | yes | no | no | no |
| 2023 | yes | yes | yes | yes | yes | yes | no | no | no |
| 2025 | yes | yes | yes | yes | yes | yes | yes | yes | no |

## Common Merchants Across Years

212 normalized merchants appear in every inspected year.

AMC Theaters, Abercrombie, Academy Sports + Outdoors, Ace Hardware, Advance Auto Parts, Aeropostale, Amazon, American Eagle Outfitters, Anthropologie, Apple, Applebee's, Arby's, At Home, AutoZone, Avenue, BD's Mongolian Grill, BP, BW3, Barnes & Noble, Bath & Body Works, Bebe, Bed Bath & Beyond, Benihana, Best Buy, Best Western, Big Boy, Big Lots, Black Angus, Bloomingdale's, Bob Evans, Bravo! Cucina Italiana, Brooks Brothers, Buckle, Build-A-Bear, Burger King, Burlington Coat Factory, CVS, California Pizza Kitchen, Carson's, Carter's, Cato, Charlotte Russe, Cheesecake Factory, Chick-Fil-A, Chico's, Chipotle, Christopher & Banks, Cinemark, Circle K, Citgo, Citi Trends, Claire's, Coach, Cold Stone Creamery, Costco, Cracker Barrel, Crate & Barrel, Culver's, DSW Shoe Warehouse, Dairy Queen, Dave and Buster's, Denny's, Destination XL, Dick's Sporting Goods, Disney, Dollar General, Dollar Tree, Domino's, Dressbarn, Dunham's, Dunkin Donuts, EBay, Eddie Bauer, Einstein Bros Bagels, Express, FYE, Family Dollar, Famous Footwear, Fandango, Five Below ... (132 more)

## Merchants Added/Removed

### 2017 to 2018

Added: 6
Adidas, Andiamo, Athleta, Loft, Ruth's Chris Steakhouse, Tropical Smoothie Café

Removed: 4
Biggby Coffee, Goodrich Quality Theaters, Lone Star Steakhouse, Massage Green

### 2018 to 2021

Added: 70
American Express, Ann Taylor / Loft, Antonio's Cucina Italiana, Athleta / BR / Gap / ON, Aubree's, Bass Pro Shops / Cabelas, Belk, Biggby Coffee, Boscovs, Busch's, Carlyle Grill, Carrabba's Italian Grill / Flemings / Outback, Children's Place, Chili's / Maggiano's / Macaroni Grill / On The Border, Darden / Olive Garden / Longhorn Steakhouse, Detroit Tigers, Detroit Zoo, Emagine Theaters, Foot Locker / Champs Sports, Generic, Goodrich Quality Theaters, Home Depot eStore Credit, Home Depot Merch Credit (No ID), Home Depot Merch Credit (Tied to ID), Ichiban, Ikea Merch Credit, JoAnn, K&G Fashion Super Store, Kay Jewelers, Knight's, Lands End / Kmart / Sears, LaVida Massage, Lewis Jewelers, LL Bean, Lowe's Merch Credit (No ID), M Den, Mainstreet Ventures, Mancino's Pizza & Grinders, Mani Osteria & Bar, Mastercard ... (30 more)

Removed: 48
American Express (mygiftcard), Ann Taylor, Athleta, Banana Republic, Bass Pro Shops, Cabela's, Carrabba's Italian Grill, Champs Sports, Chili's, Darden, Flemings, Foot Locker, Gap, Jo-Ann Fabric, Kmart, L.L.Bean, Land's End, Loft, Longhorn Steakhouse, Mastercard (mybalancenow), Mastercard (mygiftcardsite), Mastercard (Vanilla), Office Depot, Office Max, Old Navy, Olive Garden, Outback, P.F. Chang's, Pier 1 Imports, Pottery Barn, Sears, Speedway, T.G.I. Friday's, The Children's Place, The North Face, The Walking Company, TJ Maxx, Ulta Beauty, Visa (citiprepaid), Visa Gift Card (pncgiftcard) ... (8 more)

### 2021 to 2022

Added: 0
(none)

Removed: 0
(none)

### 2022 to 2023

Added: 2
Delta, Uber

Removed: 0
(none)

### 2023 to 2025

Added: 1
Safeway / Albertsons

Removed: 0
(none)

## Obvious Schema Differences

- The historical `.xls` workbooks expose cached values but not formulas through the reader used here, so formula-reference drift cannot be reconstructed from those files without an Excel/LibreOffice conversion step.
- The 2025 `.xlsx` workbook exposes formulas and includes the known `PricingSheet` and `InputsandMargins` structure used by the live v1 baseline parser.
- 2017: no detected values for cardcash_buy, cardcash_sell, raise_sell.
- 2018: no detected values for cardcash_sell, raise_sell.
- 2021: no detected values for cardcash_buy, cardcash_sell, raise_sell.
- 2022: no detected values for cardcash_buy, cardcash_sell, raise_sell.
- 2023: no detected values for cardcash_buy, cardcash_sell, raise_sell.
- 2025: no detected values for raise_sell.
- Duplicate normalized merchant slugs exist within at least one workbook; see row artifact notes.

## Risks/Unknowns

- Column detection is heuristic for historical sheets; values should be spot-checked before using this for any migration or trend analysis.
- Merchant matching is slug-based. Renames, punctuation changes, and grouped merchants can appear as added/removed even when the business entity is continuous.
- `.xls` formula text is unavailable with the current lightweight reader, so margin-row, differential-row, and e-bonus provenance is unknown for 2017-2025 `.xls` files.
- Extracted percentages are normalized as fractions, but unusual text markers and workbook errors are preserved only as missing values plus notes.

## Recommended Next Analysis Steps

1. Spot-check 10-15 high-volume merchants across all years against the original workbooks.
2. Build a manual rename map for merchant names that changed but represent the same merchant.
3. Convert the `.xls` workbooks to `.xlsx` on a controlled machine if formula-reference history matters.
4. Compare historical channel percentages for stable common merchants to identify broad policy shifts, without changing the live v1 algorithm.
