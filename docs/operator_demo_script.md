# Operator Demo Script

Use this script to walk through the dashboard while eBay Marketplace Insights credentials are still pending.

## What the dashboard does today

The dashboard is a read-only pricing review tool. It shows one active merchant per row, the latest recommendation for each pricing channel, confidence, recommendation history, formula breakdowns, and reference panels for future live-market data.

The tool does not publish prices. The operator still decides what to use and applies prices outside this app.

## Synthetic mode

Synthetic mode shows seeded spreadsheet-baseline recommendations. These are demo recommendations generated from the validated legacy spreadsheet fixture so the operator can review layout, labels, drill-downs, and formulas before live eBay access is approved.

Refresh is disabled in synthetic mode. That keeps the seeded baseline from being replaced by empty "No Data" rows from a synthetic client that has no real sold listings.

## What live eBay mode will add

Live eBay mode will use the eBay Marketplace Insights API to collect sold listings, filter them, compute the eBay sell percentage, score confidence, and append a new recommendation row for each active merchant during an on-demand refresh.

After credentials are approved, the refresh button will run the live pipeline and the dashboard will show recent valid and excluded eBay observations on merchant detail pages.

## Reading the pricing list

Start with the status strip:

- Active merchants: active merchant rows in the dashboard.
- Mode: Synthetic or Live eBay.
- Last completed refresh: most recent completed or partial run.
- With recommendation: merchants whose latest row has usable recommendation values.
- With No Data: merchants whose latest row could not produce a data-backed recommendation.
- With live eBay observations: active merchants with at least one valid sold-listing observation stored.

Then scan the table:

- eBay sell is the market input from sold listings, or "No eBay data" when unavailable.
- Online sell is the recommended storefront sell percentage.
- In-mail, in-store, and electronic buy are customer payout recommendations by channel.
- "Not offered" means the channel is ineligible for that merchant.
- Source shows whether the latest row came from the synthetic baseline, live eBay, a manual override, or a No Data state.
- Rows with No Data or manual overrides get a subtle visual tint so they are easier to spot while scanning.
- Delta columns need at least two comparable runs. "No change" means a comparable value exists and did not move.
- Confidence "No eBay data" means no valid eBay signal was available for that row.

## Reading merchant detail

The merchant page starts with the latest recommendation cards and a compact source badge. The two most important cards are Online sell and In-mail buy, followed by the other channel values, eBay sell, and Confidence.

The "Why this recommendation?" strip explains the source in one sentence, repeats confidence, and shows when the latest row was computed. Use it to confirm whether the recommendation is Synthetic baseline, Manual override, Live eBay, or No Data before reading the full formula.

Formula Breakdown shows the worked recommendation logic for each channel. Normal rows show percentage inputs, fees, margins, and the final value. Status rows explain why a channel is Not offered, No Data, or override-based. It is intentionally below the summary so the operator can scan first and audit second.

Recent eBay Observations will show valid sold listings after live refresh is enabled. Excluded eBay Observations will show listings filtered out by the validity rules, with reasons such as suspected partial balance or wrong merchant match.

Competitor Reference is read-only v1 context. It does not feed the recommendation.

Recommendation History shows prior recommendation rows so the operator can see movement over time.

## Formula breakdown

The v1 recommendation is eBay-only unless a merchant has a manual override. For a normal merchant:

- Online sell = eBay sell percentage minus the merchant's eBay differential.
- In-mail buy = online sell minus in-mail margin, PayPal cost, bad debt, and postage.
- In-store buy = online sell minus in-store margin, PayPal cost, postage, and in-store bad debt.
- Electronic buy = in-mail buy minus the merchant's electronic markdown, unless an electronic override applies.

All percentages are stored and computed as fractions, then displayed as percentages.

## Confidence

Confidence summarizes the eBay signal:

- High: at least 10 valid recent listings, with the newest listing within 30 days.
- Medium: enough usable listings or moderately fresh data.
- Low: very small but still usable eBay sample.
- No eBay data: no valid sold-listing signal for the merchant.

Low confidence does not block a recommendation. It tells the operator to review more carefully.

## What v1 does not do

V1 does not auto-publish prices, track accept/override/skip decisions, edit merchant config in the app, run scheduled refreshes, export CSVs, blend competitor data into recommendations, expose an eBay-weight control, or use internal sale history.

## Things to ask the operator during demo

- Which columns help you decide what to review first?
- Can you tell quickly which rows need attention?
- Are any labels unclear or too technical?
- Does the merchant detail page explain a recommendation quickly enough?
- Are the No Data and Not offered states distinct enough?
- Which eBay observation or excluded-listing details would help you trust the data?
- What would you want to see before applying a recommended price outside the tool?
