# Dashboard Usability Review Plan

## Purpose

Use synthetic mode to review whether the Zeal Pricing dashboard is clear,
scannable, and useful for the operator before production eBay Marketplace
Insights access is available.

This review is about the dashboard experience, not live market correctness.
Synthetic recommendations are seeded from the validated spreadsheet baseline and
do not represent current live eBay sold-listing prices.

## What Can Be Reviewed Before Live eBay Access

- Top-of-page mode/status messaging.
- Pricing list scannability, column order, row spacing, and percentage alignment.
- Source/status labels: Synthetic baseline, Live eBay, No Data, Not offered, and
  Config override.
- Confidence badge wording and placement.
- Delta-column wording that explains at least two comparable runs are required.
- Merchant detail layout and whether latest recommendation cards are prominent.
- "Why this recommendation?" copy and placement.
- Price history chart clarity and whether it is understood as recommendation
  history only.
- Formula breakdown label clarity for a non-developer operator.
- Merchant config editor usability and whether it feels like the old
  spreadsheet's control surface.
- Synthetic empty states for Recent eBay Observations and Excluded eBay
  Observations.
- Competitor Reference wording that keeps competitor data reference-only in v1.
- Whether the list-to-detail-to-list workflow matches the operator's real review
  habits.

## What Cannot Be Validated Yet

- Whether live eBay sold listings return for production credentials.
- Marketplace Insights quota, pacing, or endpoint behavior in production.
- Listing title quality from the production API.
- Face-value parsing quality against real Marketplace Insights payloads.
- Valid/excluded listing split for real sold listings.
- Recommendation plausibility against current live market conditions.
- Full live refresh runtime and failure behavior.
- Any comparison against actual Zeal published prices, because the tool does not
  track prices used or published outside the dashboard.

Production validation must wait until `buy.marketplace.insights` is enabled for
the production keyset. Browse API fallback is not allowed because Browse does not
provide sold-listing data.

## Operator Walkthrough Checklist

- Confirm the dashboard says synthetic baseline mode and awaiting production
  Marketplace Insights access.
- Ask whether the banner prevents confusion between seeded baseline data and live
  market data.
- Scan the pricing list for 2-3 minutes without clicking and note what draws
  attention first.
- Ask whether Online sell, In-mail buy, In-store buy, Electronic buy, eBay sell,
  Source, Delta, Confidence, and Last refresh are in the right order.
- Ask whether No Data and Not offered are distinct enough.
- Ask whether config overrides are clear without making the row feel like an
  error.
- Click a normal merchant, a config-override merchant, and any No Data merchant
  present in the seeded data.
- On each detail page, ask whether the latest recommendation cards answer the
  first question quickly.
- Review "Why this recommendation?", the price history chart, and formula
  breakdown labels.
- Open Edit config and ask whether the field groups feel like the spreadsheet's
  control surface without implying pricing decisions are tracked here.
- Confirm percentage helper text and blank override behavior are clear.
- Review eBay observation empty states and ask what fields the operator will want
  once live observations exist.
- Review Competitor Reference and confirm it is understood as reference-only.
- Ask the operator to describe the next action he would take outside the tool.

## UI Issues To Watch For

- Any wording that implies synthetic data is current market data.
- Badges that are too similar to distinguish while scanning.
- Percentage columns that are hard to compare across rows.
- Delta columns that look broken before a second comparable run exists.
- Formula labels that use implementation language instead of operator language.
- Config editor copy that makes a formula-input edit sound like a published
  pricing decision.
- Price history copy that implies actual Zeal prices are tracked.
- Empty eBay sections that look like a data failure instead of expected
  pre-access state.
- Competitor reference copy that implies CardCash affects v1 recommendations.
- Detail pages that bury the recommendation below diagnostic information.

## Success Criteria

The synthetic-mode review is successful when:

- The operator can explain what synthetic mode means.
- The operator can identify which rows deserve attention from the list view.
- Source/status labels are understood without developer explanation.
- Detail pages make the recommendation, source, and formula easy to audit.
- Price history is understood as saved recommendation history, not actual or
  published Zeal prices.
- Config editor feels like a narrow control surface for merchant formula inputs.
- Pending eBay and competitor sections are honest about what is and is not
  connected.
- The operator confirms the dashboard can support a real review session once live
  sold-listing data is available.

## Converting Findings Into Small PRs

Turn findings into focused PRs:

- One PR per usability theme.
- Prefer copy, spacing, badge, and table improvements before adding new surfaces.
- Add or update template/context tests for changed behavior.
- Do not bundle algorithm, schema, live eBay client, smoke-test, credential, or
  `.env` changes with usability work.
- Keep v1 non-publishing and keep competitor data reference-only.
- Save live-data quality fixes for credential-day validation after Marketplace
  Insights production entitlement is enabled.
