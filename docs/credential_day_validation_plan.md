# Credential-Day Validation Plan

This runbook is for the first day real eBay Marketplace Insights credentials are
available. It is procedural and intentionally narrow: validate live eBay access,
inspect sold-listing quality, and decide whether the dashboard is ready for an
operator demo.

Sources:

- `docs/pricing_algorithm.md`
- `docs/architecture.md`
- `docs/historical_pricing_findings.md`
- `zeal_pricing_handoff_after_codex_prompt6.md`

Note: `zeal_pricing_handoff_dashboard_polish_2026-05-06.md` was not present in
this checkout when this plan was written.

## 2026-05-07 Production Scope Finding

Credential-day testing found an entitlement mismatch:

- The sandbox keyset has `buy.marketplace.insights`.
- The production keyset does not have `buy.marketplace.insights`.
- Production `smoke-ebay` fails during OAuth token minting with `invalid_scope`.
- Base production OAuth still succeeds, so the production keyset is valid but
  cannot mint the Marketplace Insights scope.

Conclusion: production Marketplace Insights entitlement is not active for the
production keyset. Do not run the first-five pilot and do not fall back to Browse
API. Sold-listing validation remains blocked until eBay enables
`buy.marketplace.insights` for the production Client Credential Grant Type
scopes.

## 1. Pre-Credential Assumptions And Scope

Assumptions:

- eBay has approved access specifically to Marketplace Insights item-sales search,
  not only Browse API access.
- Real credentials are available from the eBay developer account.
- The local SQLite DB exists and has been seeded from the current baseline fixture.
- The operator and developer can review command output and dashboard pages together.
- Historical spreadsheet prices are not current market data and are not used to
  judge whether live recommendations are correct.

In scope:

- Verify OAuth and Marketplace Insights access.
- Verify that live sold listings are returned for known merchants.
- Manually inspect listing title matching, face-value parsing, valid/excluded
  listing split, and recommendation plausibility.
- Capture evidence for the operator demo decision.
- Apply only narrow fixes required to make live validation trustworthy.

Out of scope:

- Dashboard feature changes.
- Production pricing algorithm changes.
- DB schema changes.
- Golden baseline test changes.
- Competitor blending or any use of CardCash in recommendations.
- Scheduled refresh, auto-publishing, operator workflow, config UI, or new v1 UI.

## 2. Environment Setup

Run from the repo root.

1. Confirm dependencies are installed:

```powershell
uv sync
```

2. Create `.env` from the example if it does not already exist:

```powershell
Copy-Item .env.example .env
```

3. Edit `.env` and set:

```dotenv
ZEAL_EBAY_MODE=live
EBAY_CLIENT_ID=<real client id>
EBAY_CLIENT_SECRET=<real client secret>
EBAY_ENVIRONMENT=production
# ZEAL_DB_PATH=data/zeal.db
```

Use `EBAY_ENVIRONMENT=sandbox` only if the credentials and Marketplace Insights
approval are explicitly for sandbox validation. Production is the expected
credential-day path.

4. Make sure `.env` is not staged or committed:

```powershell
git status --short
```

5. Ensure the local DB is initialized and seeded if needed:

```powershell
uv run python -m zeal.cli init-db
uv run python -m zeal.cli seed
```

If preserving an existing validation DB matters, back it up before reseeding.

## 3. Exact Smoke-eBay Command Sequence

Start with configuration and mode sanity:

```powershell
uv run python -m zeal.cli smoke-ebay --merchant home_depot --limit 10
```

Expected live-mode behavior:

- It should not print `ZEAL_EBAY_MODE=synthetic`.
- It should print `Merchant: Home Depot (home_depot)`.
- It should print raw listing count, first listings, valid listing count, excluded
  listing count, and exclusion reasons.

If Home Depot passes the basic access test, run the first five high-volume checks:

```powershell
uv run python -m zeal.cli smoke-ebay --merchant home_depot --limit 10
uv run python -m zeal.cli smoke-ebay --merchant target --limit 10
uv run python -m zeal.cli smoke-ebay --merchant walmart --limit 10
uv run python -m zeal.cli smoke-ebay --merchant amazon --limit 10
uv run python -m zeal.cli smoke-ebay --merchant best_buy --limit 10
```

If those pass, run the remaining historical pilot merchants:

```powershell
uv run python -m zeal.cli smoke-ebay --merchant mastercard --limit 10
uv run python -m zeal.cli smoke-ebay --merchant visa --limit 10
uv run python -m zeal.cli smoke-ebay --merchant home_depot_merch_credit_no_id --limit 10
uv run python -m zeal.cli smoke-ebay --merchant home_depot_estore_credit --limit 10
uv run python -m zeal.cli smoke-ebay --merchant apple --limit 10
uv run python -m zeal.cli smoke-ebay --merchant starbucks --limit 10
uv run python -m zeal.cli smoke-ebay --merchant disney --limit 10
uv run python -m zeal.cli smoke-ebay --merchant tj_maxx_homegoods_marshalls --limit 10
uv run python -m zeal.cli smoke-ebay --merchant delta --limit 10
uv run python -m zeal.cli smoke-ebay --merchant safeway_albertsons --limit 10
```

After smoke commands look healthy, start the dashboard:

```powershell
uv run python -m zeal.cli serve
```

Open `http://127.0.0.1:8000`, click refresh once, and inspect the pilot merchants
from the dashboard detail pages.

## 4. Staged Pilot Plan

Stage 0: Home Depot only.

- Purpose: prove credentials, OAuth scope, API endpoint, merchant lookup, and basic
  filtering work with a high-volume known merchant.
- Stop immediately if this fails due to auth/access, endpoint, or parsing exceptions.

Stage 1: first five obvious high-volume merchants.

| Order | Merchant ID | Display name | Why |
|---:|---|---|---|
| 1 | `home_depot` | Home Depot | High-volume, known canonical merchant |
| 2 | `target` | Target | Core merchant with merch-credit sibling risk |
| 3 | `walmart` | Walmart | Broad eBay supply, all-year history |
| 4 | `amazon` | Amazon | High-volume/high-price row, fraud/noise risk |
| 5 | `best_buy` | Best Buy | Electronics merchant, title/face-value variety |

Stage 2: remaining historical pilot merchants.

| Merchant ID | Display name | Why |
|---|---|---|
| `mastercard` | Mastercard | Prepaid-card row, generic title risk |
| `visa` | Visa | Prepaid-card row, generic title risk |
| `home_depot_merch_credit_no_id` | Home Depot Merch Credit (No ID) | Merchandise-credit title matching |
| `home_depot_estore_credit` | Home Depot eStore Credit | Electronic-only override edge case |
| `apple` | Apple | High-demand merchant with ambiguous titles |
| `starbucks` | Starbucks | Small-denomination listing variety |
| `disney` | Disney | High-demand merchant, historical tier move |
| `tj_maxx_homegoods_marshalls` | TJ Maxx / Homegoods / Marshalls | Noisy grouped merchant |
| `delta` | Delta | Newer travel merchant |
| `safeway_albertsons` | Safeway / Albertsons | 2025-only cold-start case |

## 5. Manual Inspection Checklist

For each merchant, inspect the `smoke-ebay` output first, then the dashboard detail
page after a refresh.

Listing quality:

- Listing titles clearly match the merchant.
- Grouped merchants match an intended member brand and do not overmatch unrelated
  brands.
- Merchandise-credit or store-credit rows match the intended variant where possible.
- Prepaid-card rows do not accidentally match unrelated prepaid products.

Value parsing:

- Face values look correctly parsed from titles.
- Face values are non-zero.
- Sale prices are non-zero.
- Computed sell percentages would be plausible under the valid range `[0.30, 1.10]`.
- Partial-balance listings are excluded rather than parsed into valid observations.

Recency and sample quality:

- Sold dates are within the expected 90-day window.
- The most recent sold date supports the displayed confidence.
- Valid sample count is acceptable:
  - `>= 10`: good pilot signal.
  - `5-9`: usable but inspect carefully.
  - `1-4`: weak signal; note as low confidence.
  - `0`: fail for that merchant unless the merchant is expected to be sparse.
- Excluded listings make sense and have understandable exclusion reasons.

Recommendation sanity:

- Recommendation direction feels plausible relative to the live eBay sell percentage.
- Sentinel behavior remains correct: ineligible channels show `No`, missing eBay
  data without override shows `No Data`, and overrides behave per spec.
- No competitor data changes the recommendation in v1.

## 6. Pass/Fail Criteria

Overall pass:

- Home Depot live smoke succeeds.
- At least four of the first five high-volume merchants return usable valid listings.
- No auth/access errors remain.
- No systematic face-value parsing defect appears across the first five merchants.
- Dashboard refresh completes without manual intervention beyond clicking refresh.
- Merchant detail pages show recent valid and excluded observations coherently.
- No v1 scope changes are needed to make the operator demo understandable.

Merchant-level pass:

- Raw listings are returned, or a no-result outcome is explainable for that merchant.
- At least five valid listings are available, or the low sample is explicitly noted.
- Exclusion reasons are sensible.
- Face values and sale prices look credible.
- Recommendation output follows the v1 algorithm and sentinel rules.

Overall fail:

- Marketplace Insights access is denied or Browse-only.
- OAuth cannot be completed with the provided credentials.
- Most high-volume merchants return no results.
- Face-value parsing is systematically wrong.
- Title matching is systematically overbroad or underbroad.
- Dashboard refresh cannot complete in live mode.

## 7. Failure Triage

Auth/access failure:

- Symptoms: `EbayAuthError`, invalid client, invalid scope, 401/403, or Marketplace
  Insights endpoint denied.
- Check `.env` values, `ZEAL_EBAY_MODE=live`, `EBAY_ENVIRONMENT`, client ID/secret,
  and whether Marketplace Insights access is actually granted.
- If production OAuth fails with `invalid_scope` for
  `buy.marketplace.insights`, the production keyset cannot mint the Marketplace
  Insights scope. Check the eBay Developer Portal under Production -> Client
  Credential Grant Type scopes and confirm `buy.marketplace.insights` is assigned
  to the production keyset.
- A sandbox keyset showing `buy.marketplace.insights` is not sufficient for
  production validation. Production must have the same Marketplace Insights
  entitlement.
- Do not run the first-five pilot while `invalid_scope` is present.
- Do not fall back to Browse API for sold-listing validation.

Rate limit failure:

- Symptoms: `EbayRateLimitError`, 429, quota-exceeded messaging.
- Stop broad testing. Record the quota message and reset time if present.
- Continue only with single-merchant smoke commands after the reset window.
- Any pacing change must be narrow and live-validation-driven.

No results:

- Symptoms: raw listings returned is zero, or all listings excluded.
- Check merchant inclusion/exclusion regex.
- Try Home Depot and another first-five merchant to distinguish merchant-specific
  query weakness from account/API failure.
- If isolated, add the merchant to the query-tuning list rather than changing broad
  filtering behavior immediately.

Bad title matching:

- Symptoms: unrelated merchants, coupons, bundles, collectibles, or wrong grouped
  brands appear as valid listings.
- First inspect whether the listing should have been excluded by existing filters.
- Allowed fix: narrow merchant inclusion/exclusion regex or query construction for
  the affected merchant class.
- Not allowed: weakening validity filters to increase sample size.

Bad face-value parsing:

- Symptoms: face value is missing, zero, pulled from the wrong dollar amount, or
  confused by partial-balance wording.
- First confirm whether the listing should be excluded as partial balance.
- Allowed fix: narrow title/face-value heuristic only if the live issue is clear.
- Defer broad partial-balance parsing to v2.

Noisy merchant grouping:

- Symptoms: grouped rows like `tj_maxx_homegoods_marshalls` match too narrowly or
  too broadly.
- Decide whether the group needs multiple inclusion terms or stricter exclusions.
- Record the issue for operator review if the right grouping behavior is ambiguous.

## 8. Allowed Fixes Before Operator Demo

Allowed:

- Narrow fixes required by real live validation.
- Credential/config documentation corrections.
- Merchant-specific regex/query tuning when smoke output proves the current rule is
  wrong.
- Small parsing fixes for clear Marketplace Insights payload shape mismatches.
- Error-message improvements that make credential-day diagnosis clearer.

Not allowed without explicit scope change:

- New dashboard features.
- Dashboard expansion beyond existing validation display.
- Production pricing algorithm changes.
- DB schema changes.
- Golden baseline changes or tolerance changes.
- Competitor blending.
- `ebay_weight` UI.
- Scheduled refresh.
- Automated price publishing.
- CSV export.
- In-app merchant/global config editor.

## 9. Evidence To Capture

For each stage, save enough evidence to explain the go/no-go decision:

- Command output from each `smoke-ebay` run.
- Screenshot of the dashboard list after live refresh.
- Screenshot of each inspected merchant detail page.
- Notes on listing titles that looked wrong or ambiguous.
- Notes on face-value parsing concerns.
- Count of raw, valid, and excluded listings by pilot merchant.
- Exclusion-reason summary by pilot merchant.
- List of merchants needing query tuning.
- Any eBay error payloads, rate-limit headers/messages, or access-denied text.

Do not capture or commit real credentials.

## 10. Post-Validation Decision Tree

Proceed to operator demo when:

- Home Depot passes.
- The first five high-volume merchants mostly pass.
- Remaining pilot issues are isolated and documented.
- Dashboard refresh and detail inspection work in live mode.
- No live issue requires a v1 scope expansion.

Tune merchant query rules when:

- Auth and API access work.
- Most merchants behave well.
- A small set has bad/noisy title matches or no results.
- The fix can stay merchant-specific or narrowly query-related.

Revisit face-value parsing when:

- Multiple unrelated merchants show the same parsing error.
- Valid listings are excluded or mispriced because face value is read from the wrong
  title amount.
- The issue is not limited to partial-balance listings that v1 intentionally excludes.

Pause if Marketplace Insights access is insufficient when:

- Credentials only allow Browse API.
- The item-sales endpoint is denied.
- The account has no usable quota for sold-listing validation.
- eBay access terms prevent the intended local validation workflow.

If paused, do not retrofit v1 around a different data source without a new scope
decision.
