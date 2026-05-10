# Credential Day Runbook

Exact, copy-paste procedure for the day eBay grants production Marketplace
Insights API access. Execute steps in order. Stop at any kill criterion and
follow the rollback procedure in §8.

**Context:**
- The sandbox keyset already has `buy.marketplace.insights`.
- The production keyset does not yet have `buy.marketplace.insights`.
- This runbook applies to the production keyset only.
- Do NOT use Browse API at any point; Browse returns active listings and is not
  a valid sold-listing source.

---

## §0. Before credential day: confirm the runbook is ready

Confirm each item is true **before eBay notifies you that access is granted:**

- [ ] `uv run ruff check . && uv run mypy src && uv run pytest` all pass on current `main`.
- [ ] A known-good `data/zeal.db` is backed up to a separate location (OneDrive
  or local copy). The backup file path: ________________.
- [ ] `.env` exists (not just `.env.example`). Run `git status --short .env`
  and confirm it is **not** staged.
- [ ] The dashboard is **stopped** before starting this runbook.

---

## §1. Pre-flight: confirm the scope is live on the production keyset

**Do this step before editing `.env`.**

1. Open [eBay Developer Portal](https://developer.ebay.com/my/keys)
2. Select your **Production** application (not Sandbox).
3. Under **OAuth Scopes** → **Client Credential Grant Type**, confirm
   `buy.marketplace.insights` appears in the scope list.
4. If it does NOT appear, do not proceed. The access has not been granted yet.
   Contact eBay support with your case reference number.

---

## §2. Update `.env`

Open `.env` in a text editor. Change exactly these values:

```dotenv
ZEAL_EBAY_MODE=live
EBAY_CLIENT_ID=<production_client_id_from_ebay_portal>
EBAY_CLIENT_SECRET=<production_client_secret_from_ebay_portal>
EBAY_ENVIRONMENT=production
```

Do NOT change `ZEAL_DB_PATH` unless you are intentionally using a different DB
file. Do NOT commit `.env` to git.

Save the file. Do not start the dashboard yet.

---

## §3. Home Depot smoke test (Stage 0)

Run in the repo root directory:

```powershell
uv run python -m zeal.cli smoke-ebay --merchant home_depot --limit 10
```

### Expected success output

```
Merchant: Home Depot (home_depot)
Inclusion regex: <regex value>
Raw listings returned: N    ← must be > 0
First listings:
- <listing_id> | <title> | sale_price=NN.NN | face_value=NNN.NN | sold_at=<ISO date>
- ...
Valid listings: M           ← must be >= 1
Excluded listings: K
Exclusion reasons:
- <reason>: N
```

### Pass criteria (ALL must be true)

- [ ] No line begins with `Warning: ZEAL_EBAY_MODE=synthetic`
- [ ] No line begins with `EbayAuthError`, `EbayNetworkError`, `EbayServerError`, or `EbayRateLimitError`
- [ ] `Raw listings returned:` shows a number greater than 0
- [ ] `Valid listings:` shows a number greater than 0
- [ ] At least one title in "First listings" contains words related to Home Depot or gift cards
- [ ] Exit code is 0: confirm by running `Write-Host $LASTEXITCODE` immediately after

### Kill criteria — STOP here and follow §8 rollback

| Output | Diagnosis | Action |
|---|---|---|
| `Configuration error: Missing required live eBay credential(s)` | `.env` not fully filled | Fix `.env`, retry §3 |
| `EbayAuthError: <msg containing "invalid_scope">` | Production keyset lacks MI scope | Do not proceed. Revert `.env`, contact eBay support (see §9) |
| `EbayAuthError: <other msg>` | Wrong credentials or revoked key | Double-check `.env` values against portal; revert if unsure |
| `EbayNetworkError` | Network failure | Check internet. Retry once after 30 seconds. If still failing, revert |
| `EbayServerError` | eBay server error | Retry once after 60 seconds. If still failing, revert |
| `EbayRateLimitError` | Quota exceeded before even starting | Check Retry-After from the error message. Wait, then retry. If repeating, revert and contact eBay |
| `Merchant not found: home_depot` | DB not seeded | Run `uv run python -m zeal.cli seed` then retry §3 |
| `Raw listings returned: 0` | Possible cold-start or query issue | Try one more Stage 1 merchant. If all show 0, treat as kill criterion |

---

## §4. Stage 1 — First-five pilot

Run each command. Confirm pass criteria for each before continuing.

```powershell
uv run python -m zeal.cli smoke-ebay --merchant target            --limit 10
uv run python -m zeal.cli smoke-ebay --merchant walmart           --limit 10
uv run python -m zeal.cli smoke-ebay --merchant amazon            --limit 10
uv run python -m zeal.cli smoke-ebay --merchant best_buy          --limit 10
```

### Pass criteria for Stage 1

- At least 4 of the 5 merchants (including Home Depot from §3) return
  `Valid listings: >= 1`.
- No `invalid_scope` errors on any merchant.
- No systematic face-value parsing defect (all face values zero or obviously wrong).
- Listing titles are recognizable for each merchant.

### Inspection for each merchant

For each `smoke-ebay` run, check:
- Title contains the merchant name or a plausible gift-card description.
- `face_value` is a plausible dollar amount for the card (e.g., $25, $50, $100).
- `sale_price` is plausible (50%–110% of face value).
- `sold_at` dates are within the last 90 days.

### Kill criteria for Stage 1

- Any merchant returns `invalid_scope` → stop immediately, revert, contact eBay.
- Fewer than 3 of 5 merchants return any valid listings → stop, document which
  merchants failed, proceed to §8 rollback.
- All face values are 0 or all titles are unrelated merchants → systematic
  parsing issue; do not proceed to a full refresh; document and contact support.

---

## §5. Stage 2 — Remaining pilot merchants

Run each command:

```powershell
uv run python -m zeal.cli smoke-ebay --merchant mastercard                     --limit 10
uv run python -m zeal.cli smoke-ebay --merchant visa                           --limit 10
uv run python -m zeal.cli smoke-ebay --merchant home_depot_merch_credit_no_id  --limit 10
uv run python -m zeal.cli smoke-ebay --merchant home_depot_estore_credit       --limit 10
uv run python -m zeal.cli smoke-ebay --merchant apple                          --limit 10
uv run python -m zeal.cli smoke-ebay --merchant starbucks                      --limit 10
uv run python -m zeal.cli smoke-ebay --merchant disney                         --limit 10
uv run python -m zeal.cli smoke-ebay --merchant tj_maxx_homegoods_marshalls    --limit 10
uv run python -m zeal.cli smoke-ebay --merchant delta                          --limit 10
uv run python -m zeal.cli smoke-ebay --merchant safeway_albertsons             --limit 10
```

Note any merchant with:
- `Raw listings returned: 0` → log as needing regex review; not a kill criterion
  if fewer than 3 merchants hit this.
- `Valid listings: 0` with nonzero raw → exclusion-reason histogram explains why;
  review if systematic.
- Prepaid-card merchants (Mastercard, Visa): titles should match prepaid cards,
  not bank products or credit cards.
- Grouped merchants (TJ Maxx / Homegoods / Marshalls): titles should match at
  least one member brand.

### Kill criteria for Stage 2

- Any merchant returns `invalid_scope` → stop, revert.
- More than 4 merchants return 0 valid listings without explanation → stop,
  document, do not proceed to a full refresh.

---

## §6. Dashboard startup and inspection

**Prerequisites:** Stages 0–2 passed.

```powershell
uv run python -m zeal.cli serve
```

Open `http://127.0.0.1:8000` in a browser.

### Verify the dashboard is in live mode

- [ ] The mode/status banner does NOT say "Synthetic baseline mode"
- [ ] The "Refresh now" button is visible and enabled (it was returning 409 in
  synthetic mode)
- [ ] Source badge area is not showing "Synthetic baseline" for recent rows

---

## §7. One controlled full live refresh

**Prerequisites:** Dashboard is running and confirmed in live mode (§6).

**WARNING:** This makes ~300 eBay API requests, one per active merchant. Confirm
your eBay API quota is sufficient before starting. If in doubt, run Stage 2 for
a few more merchants to estimate quota usage per merchant, then calculate total.

1. Click **"Refresh now"** in the dashboard.
2. Watch the progress bar. It shows `processed / total` merchants.
3. Wait for completion (status changes to "Completed" or "Partial").

### Expected completion

- Status: `completed` (all merchants OK) or `partial` (some errored — acceptable
  for first live run; check which merchants errored).
- The list view refreshes and shows updated recommendations sorted by delta.

### Post-refresh inspection

Inspect 3–5 merchant detail pages, choosing a mix of:
- High-volume merchants (Home Depot, Target, Walmart)
- At least one config-override merchant (if any exist)
- At least one "No Data" or low-confidence merchant

For each detail page, verify:
- [ ] "Why this recommendation?" section shows "Live eBay sold listings produced
  this recommendation" (not synthetic language).
- [ ] "Recent eBay Observations" section has rows (not the synthetic empty-state
  message).
- [ ] Source badge shows "Live eBay".
- [ ] Recommendation values are plausible (not "No Data" for high-volume merchants).
- [ ] Price history chart shows at least one data point (from the seeded baseline
  plus the new live recommendation).

### Kill criteria for §7

- Refresh completes with `failed` status → check logs in terminal window for the
  exception; if `invalid_scope` appears, revert to synthetic.
- Most high-volume merchants show "No Data" after a full refresh → suspicious;
  check the `recent_ebay_observations` section for each to see whether the issue
  is filtering or no raw listings returned.

---

## §8. Rollback procedure

**Use when any kill criterion is hit or when in doubt.**

1. Stop the dashboard: press `Ctrl+C` in the terminal window.
2. Open `.env`. Set `ZEAL_EBAY_MODE=synthetic`.
3. Leave `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` in `.env` (they are harmless
   in synthetic mode; do not accidentally commit them if you clear them).
4. Restart the dashboard:
   ```powershell
   uv run python -m zeal.cli serve
   ```
5. Open `http://127.0.0.1:8000` and confirm the mode banner says
   "Synthetic baseline mode."
6. The tool is now back to its pre-credential-day state. All recommendations in
   `data/zeal.db` are intact.
7. Document what failed (see §9).

---

## §9. What to capture and share with eBay support

If Stage 0 or Stage 1 fails due to `invalid_scope`:

**Do NOT share:**
- `EBAY_CLIENT_SECRET`
- Any credential values

**DO share:**
- Your production `EBAY_CLIENT_ID` (the ID, not the secret)
- The full error message printed to the terminal, which includes the scope string
  and diagnostic text
- Confirmation that `buy.marketplace.insights` is NOT listed under Production →
  Client Credential Grant Type in the Developer Portal
- Confirmation that the sandbox keyset DOES have the scope (to rule out an
  account-level issue)
- The specific API endpoint: `/buy/marketplace_insights/v1_beta/item_sales/search`
- The OAuth token endpoint: `https://api.ebay.com/identity/v1/oauth2/token`
- The scope string: `https://api.ebay.com/oauth/api_scope/buy.marketplace.insights`

---

## §10. After a successful full refresh

- [ ] Verify `data/zeal.db` is backed up again (it now contains live observations).
- [ ] Document which merchants returned 0 valid listings (candidates for regex tuning).
- [ ] Document any merchants where exclusion-reason counts seem high.
- [ ] Note the total refresh runtime and per-merchant call count for quota planning.
- [ ] Update `docs/decisions_log.md` with a new entry dated today describing:
  the first successful live refresh, any merchants needing follow-up, and
  the observed eBay API quota behavior.
