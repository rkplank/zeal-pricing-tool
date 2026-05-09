# Operator Demo Script

Use this script for a synthetic-mode usability walkthrough while production eBay
Marketplace Insights access is still blocked. The goal is to learn whether the
dashboard supports the operator's real review workflow before live sold listings
are available.

## Setup

Run the dashboard in synthetic mode:

```powershell
uv run python -m zeal.cli serve
```

Open `http://127.0.0.1:8000`.

Confirm the top banner says synthetic baseline mode and that live eBay sold
listings are not connected yet. Confirm the page says the project is awaiting
production Marketplace Insights access.

## What To Say Up Front

The dashboard does not publish prices, track accept/override decisions, export
CSVs, blend CardCash into recommendations, or expose an `ebay_weight` control.
A narrow merchant config editor is now in v1 scope, but this PR only changes
wording/docs and does not add the editor yet.

Synthetic baseline mode uses seeded spreadsheet-baseline recommendations. These
rows are useful for reviewing layout, labels, formula explanations, and drill-down
flow. They are not current live market prices.

Live validation should wait until eBay enables `buy.marketplace.insights` for
the production keyset. Browse API fallback is not allowed because Browse does not
provide sold listings.

## Pricing List Walkthrough

Start at the status strip and ask:

- Does the mode/status banner make it clear that live market data is not current?
- Are "Synthetic baseline" and "Awaiting production Marketplace Insights access"
  clear enough?
- Are the active merchant, No Data, recommendation, and live observation counts
  useful?

Scan the table and ask:

- Which columns do you look at first when deciding what to review?
- Is the row spacing compact enough without feeling cramped?
- Are percentages easy to compare when scanning across a row?
- Are source badges clear: Synthetic baseline, Live eBay, No Data, Config
  override?
- Are "No Data" and "Not offered" visibly and conceptually distinct?
- Do confidence badges help, or would different wording be more useful?
- Do the delta columns explain that they need at least two comparable runs?
- Does any label sound too technical for day-to-day use?

Click a normal high-volume merchant such as Home Depot.

## Merchant Detail Walkthrough

On the detail page, start with the recommendation cards and ask:

- Are Online sell and In-mail buy prominent enough?
- Are In-store buy, Electronic buy, eBay sell, and Confidence in the right place?
- Can you quickly tell whether the row is synthetic, live eBay, No Data, or
  config-override-based?

Move to "Why this recommendation?" and ask:

- Is this easy to find?
- Does it explain the recommendation source before you inspect formulas?
- Does the synthetic-mode warning prevent accidental trust in old market data?

Review the formula breakdown and ask:

- Are the labels understandable without developer context?
- Do "eBay differential", "In-mail margin", "PayPal cost", "bad debt", and
  "postage" match how you think about the pricing math?
- Is the step-by-step breakdown useful, or would a shorter summary be better?
- For ineligible channels, is "Not offered" the right wording?

Review eBay observation sections and ask:

- Is the pending/synthetic empty state honest enough while live access is blocked?
- Once live data exists, which listing fields matter most for trust: title, sold
  date, face value, sale price, sell percentage, exclusion reason?
- Would excluded listings help you diagnose bad eBay matches?

Review Competitor Reference and ask:

- Is it clear this panel is reference-only in v1?
- Is it clear CardCash/competitor data does not feed the recommendation?
- Which competitor fields are useful before any future blending work?

Review Recommendation History and ask:

- Does the history table help you understand movement?
- Would you use this during a normal pricing review?

## Edge-State Checks

Open at least one merchant with each state, if present in the seeded data:

- Synthetic baseline
- Config override
- No Data
- Not offered channel

For each one, ask whether the state is obvious before reading the formula.

## Success Criteria

The synthetic-mode review is successful when:

- The operator understands that live eBay sold listings are not connected yet.
- The operator can scan the list and identify rows worth drilling into.
- Source, confidence, No Data, Not offered, and Config override labels are clear.
- Merchant detail pages explain the recommendation source and formula clearly.
- eBay observation empty states do not imply live data exists.
- Competitor Reference is understood as reference-only and not part of v1
  recommendations.
- The operator can describe how he would use the dashboard in his actual review
  workflow.

## Turning Findings Into PRs

Convert findings into small PRs:

- Keep each PR to one usability theme, such as table labels, detail-page copy, or
  observation table readability.
- Do not change formulas, schema, live eBay client behavior, smoke-test logic, or
  credential handling as part of UI feedback.
- Keep competitor data reference-only and keep v1 non-publishing.
- Use synthetic-mode tests for template/context behavior.
- Save live-data concerns for credential-day validation after Marketplace
  Insights production entitlement is enabled.
