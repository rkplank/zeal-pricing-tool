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

The dashboard shows saved tool recommendations only. It does not publish prices,
track which prices the operator applied outside the tool, track accept/override
decisions, export CSVs, blend CardCash into recommendations, or expose an
`ebay_weight` control. The merchant config editor changes formula inputs only;
it is not price publishing or operator action tracking.

Synthetic baseline mode uses seeded spreadsheet-baseline recommendations. These
rows are useful for reviewing layout, labels, formula explanations, and
drill-down flow. They are not current live market prices.

Live validation should wait until eBay enables `buy.marketplace.insights` for
the production keyset. Browse API provides active listings only; it is not a
valid source for sold listings.

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

The merchant detail page is structured top to bottom in this order:

1. **Header** — merchant name, tier badge, source badge (Synthetic baseline /
   Live eBay / Config override / No Data), "Edit config" button
2. **Latest recommendation cards** — Online sell, In-mail buy, In-store buy,
   Electronic buy, eBay sell, Confidence
3. **"Why this recommendation?"** — one-line source summary, confidence, computed
   timestamp
4. **Price History chart** — server-rendered SVG of saved tool recommendation
   history; explicitly labeled as recommendation history, not prices published or
   applied outside the tool
5. **Formula Breakdown** — per-channel step-by-step formula audit
6. **Recent eBay Observations** — valid listings used in the average (empty in
   synthetic mode with explanation)
7. **Excluded eBay Observations** — filtered listings with exclusion reasons
   (empty in synthetic mode)
8. **Competitor Reference** — reference-only; not used in recommendations
9. **Recommendation History** — audit table of all saved recommendation rows
10. **Recent Refresh Status** — last 10 refresh runs for this merchant

### Header and recommendation cards

Ask:

- Are Online sell and In-mail buy prominent enough?
- Are In-store buy, Electronic buy, eBay sell, and Confidence in the right place?
- Can you quickly tell whether the row is synthetic, live eBay, No Data, or
  config-override-based?

### "Why this recommendation?"

Ask:

- Is this easy to find?
- Does it explain the recommendation source before you inspect formulas?
- Does the synthetic-mode note prevent accidental trust in old market data?

### Price History chart

Ask:

- Is it clear the chart uses saved tool recommendations only?
- Is it clear the chart does not show prices Zeal actually used, published, or
  applied outside the tool?
- Are Online sell, In-mail buy, and eBay sell the right default lines?
- Should In-store buy or Electronic buy be emphasized differently?
- Should competitor/reference lines remain separate for now?

### Formula Breakdown

Ask:

- Are the labels understandable without developer context?
- Do "eBay differential", "In-mail margin", "PayPal cost", "bad debt", and
  "postage" match how you think about the pricing math?
- Is the step-by-step breakdown useful, or would a shorter summary be better?
- For ineligible channels, is "Not offered" the right wording?

### Edit config

Ask:

- Do the field groups match how the spreadsheet acted as a control surface?
- Is the percentage helper text clear?
- Is it clear blank override fields use the formula?
- Is it clear edits affect future recommendations/config only, not published
  prices or any record of past pricing decisions?

### eBay observations

Ask:

- Is the pending/synthetic empty state honest enough while live access is blocked?
- Once live data exists, which listing fields matter most for trust: title, sold
  date, face value, sale price, sell percentage, exclusion reason?
- Would excluded listings help you diagnose bad eBay matches?

### Competitor Reference panel

Ask:

- Is it clear this panel is reference-only in v1?
- Is it clear CardCash/competitor data does not feed the recommendation?
- Which competitor fields are useful before any future blending work?

### Recommendation History table

Ask:

- Does the history table help you understand movement?
- Does keeping the audit table below the chart feel useful?
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
- Price history is understood as saved tool recommendation history only, not
  published or accepted prices.
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
