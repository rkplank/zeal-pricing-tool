# CardCash Fixture Capture Guide

Operator checklist for capturing the three static fixtures required before Prompt 2
(Phase 2 — Scraper against fixtures) can begin. All captures are browser-only; no
scraper code exists yet. Complete all three before starting Prompt 2.

Fixture directory: `tests/fixtures/cardcash/` (create it before saving files).

---

## 1. `tests/fixtures/cardcash/buy_catalog.html`

**What it is:** the raw HTML of any CardCash buy-gift-cards page. One GET of any slug
returns the full `INITIAL_STATE` catalog covering every merchant CardCash carries. This
is the primary fixture for all buy-side blob tests.

**Capture steps:**

1. Open a browser and navigate to:
   `https://www.cardcash.com/buy-gift-cards/discount-home-depot-cards`
   (Home Depot is a reliable anchor merchant; any valid slug works.)
2. Wait for the page to finish loading.
3. View the raw page source: press **Ctrl+U** (Chrome/Firefox) or use the browser menu
   → View Page Source. This opens the unexecuted server-sent HTML in a new tab.
4. Select all (`Ctrl+A`), copy (`Ctrl+C`).
5. Open a plain-text editor (Notepad, VS Code, etc.) and paste. Do **not** use Word or
   any editor that modifies encoding or line endings.
6. Save as `tests/fixtures/cardcash/buy_catalog.html` with **UTF-8** encoding, no BOM.
   Save verbatim — do not reformat or trim.

> Do **not** use "Save Page As" from the browser — it rewrites relative URLs and
> inlines external resources. View Source → copy/paste is the correct path.

**Local verify command** (run from the repo root):

```powershell
python -c "
import json
html = open('tests/fixtures/cardcash/buy_catalog.html', encoding='utf-8').read()
assert '<script id=\"injected-variables\">' in html, 'MISSING: script id=injected-variables'
assert 'window.INITIAL_STATE' in html, 'MISSING: window.INITIAL_STATE assignment'
idx = html.index('{', html.index('window.INITIAL_STATE'))
data, _ = json.JSONDecoder().raw_decode(html, idx)
entries = data['merchantsBuy']['sortedByName']
ids = {e['id'] for e in entries}
print(f'{len(entries)} entries; id 27 (Home Depot) present: {27 in ids}; id 54 (Starbucks) present: {54 in ids}')
assert len(entries) > 100, f'Only {len(entries)} entries — likely a truncated or broken response'
assert 27 in ids, 'Anchor merchant Home Depot (id=27) not found — wrong page or broken parse'
assert 54 in ids, 'Anchor merchant Starbucks (id=54) not found — wrong page or broken parse'
print('buy_catalog.html OK')
"
```

Expected output: entry count > 100, both ids present, line `buy_catalog.html OK`.

---

## 2. `tests/fixtures/cardcash/cart_create_response.json`

**What it is:** the raw 201 JSON response body from `POST production-api.cardcash.com/v3/carts`,
which creates an anonymous sell cart and returns a `cartId`. This is used in sell-flow tests
to mock the cart-create step.

**Capture steps:**

1. In Chrome, open DevTools (`F12`) and click the **Network** tab.
2. Navigate to `https://www.cardcash.com/sell-gift-cards` (or any page that starts the
   sell flow).
3. Begin the sell-a-card flow: enter a gift card brand and balance as prompted. You do
   not need to complete the transaction.
4. In the Network tab, filter by XHR/Fetch. Look for a `POST` request to
   `production-api.cardcash.com/v3/carts` (no path suffix — the cart-create endpoint).
5. Click that request row. In the right panel, click the **Response** tab.
6. Right-click the response body → **Copy response** (or select all and copy manually).
7. Paste into a plain-text editor and save as
   `tests/fixtures/cardcash/cart_create_response.json` with UTF-8 encoding.

The response body should look like:
```json
{"cart": {"customerId": "...", "sellCart": {"cartId": "...", "cards": []}, "buyCart": {}}}
```

**Local verify command:**

```powershell
python -c "
import json
data = json.load(open('tests/fixtures/cardcash/cart_create_response.json', encoding='utf-8'))
cid = data['cart']['sellCart']['cartId']
assert cid, 'cartId is empty or missing'
print(f'cartId: {cid}')
print('cart_create_response.json OK')
"
```

Expected output: a non-empty `cartId` string and line `cart_create_response.json OK`.

---

## 3. `tests/fixtures/cardcash/card_add_response.json`

**What it is:** the raw 201 JSON response body from
`POST production-api.cardcash.com/v3/carts/{cartId}/cards`, which adds one card to the
sell cart and returns the full updated `cards` array including a `percentage` field
(the per-merchant sell rate). This is used in sell-flow tests to mock the card-add step.

**Capture steps:**

1. Continue the same DevTools session from step 2 above (same sell flow, same Network tab).
2. After the cart is created, CardCash will POST to
   `production-api.cardcash.com/v3/carts/{cartId}/cards` as you proceed through the flow.
   Look for that request in the Network tab — it has a path like `/v3/carts/abc123/cards`.
3. Click that request row. In the right panel, click the **Response** tab.
4. Right-click the response body → **Copy response** (or select all and copy manually).
5. Paste into a plain-text editor and save as
   `tests/fixtures/cardcash/card_add_response.json` with UTF-8 encoding.

The response body should look like:
```json
{
  "cartId": "...",
  "cards": [
    {
      "id": "...", "merchant": 27, "merchantName": "Home Depot",
      "enterValue": 100, "cashValue": "83.00", "percentage": 83,
      "number": null, "pin": null, "refId": "...",
      "magStrip": null, "balanceVerified": false
    }
  ]
}
```

The `merchant` field is an **integer** (the CardCash numeric merchant id). The
`percentage` field is the sell-side payout rate as a plain integer or float
(e.g. `83` means 83% of face value). Both fields are required by the scraper.

**Local verify command:**

```powershell
python -c "
import json
data = json.load(open('tests/fixtures/cardcash/card_add_response.json', encoding='utf-8'))
cards = data['cards']
assert len(cards) > 0, 'cards array is empty'
first = cards[0]
assert isinstance(first['merchant'], int), f'merchant field is {type(first[\"merchant\"]).__name__}, expected int'
assert 'percentage' in first, 'percentage field missing from card entry'
print(f'{len(cards)} card(s); first: merchant={first[\"merchant\"]} ({type(first[\"merchant\"]).__name__}), percentage={first[\"percentage\"]}')
print('card_add_response.json OK')
"
```

Expected output: at least one card, `merchant` shown as `int`, `percentage` present,
line `card_add_response.json OK`.

---

## After capturing all three fixtures

Confirm the directory looks like this:
```
tests/fixtures/cardcash/
    buy_catalog.html
    cart_create_response.json
    card_add_response.json
```

Run all three verify commands above. When all three print `OK`, the fixtures are ready
for Prompt 2 (Phase 2 — Scraper against fixtures).

The `tests/fixtures/cardcash/` directory is not gitignored; commit the fixtures as part
of the Phase 2 branch so scraper tests are reproducible without a live network.
