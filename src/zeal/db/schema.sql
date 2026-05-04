CREATE TABLE IF NOT EXISTS merchants (
    merchant_id              TEXT PRIMARY KEY,
    display_name             TEXT NOT NULL,
    tier                     TEXT NOT NULL CHECK (tier IN ('T24','C','Z','NC')),
    in_store_margin          REAL NOT NULL,
    in_mail_margin           REAL NOT NULL,
    e_bonus                  REAL,
    ebay_differential        REAL NOT NULL,
    in_store_eligible        INTEGER NOT NULL CHECK (in_store_eligible IN (0,1)),
    in_mail_eligible         INTEGER NOT NULL CHECK (in_mail_eligible IN (0,1)),
    electronic_eligible      INTEGER NOT NULL CHECK (electronic_eligible IN (0,1)),
    online_sell_override     REAL,
    electronic_buy_override  REAL,
    ebay_weight              REAL NOT NULL DEFAULT 1.0 CHECK (ebay_weight >= 0.0 AND ebay_weight <= 1.0),
    risk_status              TEXT NOT NULL DEFAULT 'normal' CHECK (risk_status IN ('normal','watch','paused','no_buy')),
    risk_note                TEXT,
    merch_credit_variant     INTEGER NOT NULL CHECK (merch_credit_variant IN (0,1)),
    inclusion_regex          TEXT NOT NULL,
    exclusion_regex          TEXT,
    notes                    TEXT,
    is_active                INTEGER NOT NULL DEFAULT 1,
    created_at               TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at               TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS merchant_config_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_id  TEXT NOT NULL REFERENCES merchants(merchant_id),
    field_name   TEXT NOT NULL,
    old_value    TEXT,
    new_value    TEXT,
    reason       TEXT,
    changed_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_config_history_merchant
    ON merchant_config_history(merchant_id, changed_at);

CREATE TABLE IF NOT EXISTS global_constants (
    key           TEXT PRIMARY KEY,
    value         REAL NOT NULL,
    description   TEXT,
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS global_constants_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    key          TEXT NOT NULL,
    old_value    REAL,
    new_value    REAL NOT NULL,
    reason       TEXT,
    changed_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ebay_observations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_id   TEXT NOT NULL REFERENCES merchants(merchant_id),
    listing_id    TEXT NOT NULL UNIQUE,
    sold_at       TEXT NOT NULL,
    face_value    REAL NOT NULL,
    sale_price    REAL NOT NULL,
    title         TEXT NOT NULL,
    validity_status TEXT NOT NULL DEFAULT 'valid' CHECK (validity_status IN ('valid','excluded','suspicious')),
    exclusion_reason TEXT,
    raw_payload   TEXT,
    fetched_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_obs_merchant_date
    ON ebay_observations(merchant_id, sold_at DESC);

CREATE INDEX IF NOT EXISTS idx_obs_merchant_validity
    ON ebay_observations(merchant_id, validity_status);

CREATE TABLE IF NOT EXISTS ebay_summary (
    merchant_id              TEXT NOT NULL REFERENCES merchants(merchant_id),
    summary_date             TEXT NOT NULL,
    ebay_sell_pct            REAL,
    sample_size              INTEGER NOT NULL,
    most_recent_observation  TEXT,
    confidence               TEXT NOT NULL CHECK (confidence IN ('high','medium','low','none')),
    PRIMARY KEY (merchant_id, summary_date)
);

CREATE TABLE IF NOT EXISTS competitor_sources (
    source_name                TEXT PRIMARY KEY,
    is_active                  INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    collection_method          TEXT NOT NULL CHECK (collection_method IN ('scraper','manual','csv_import')),
    refresh_interval_days      INTEGER NOT NULL,
    last_successful_refresh    TEXT,
    last_attempted_refresh     TEXT,
    notes                      TEXT
);

CREATE TABLE IF NOT EXISTS competitor_observations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_id    TEXT NOT NULL REFERENCES merchants(merchant_id),
    source_name    TEXT NOT NULL REFERENCES competitor_sources(source_name),
    channel        TEXT NOT NULL CHECK (channel IN ('buy_mail','buy_electronic','sell','marketplace_sell')),
    price_pct      REAL,
    availability   TEXT NOT NULL CHECK (availability IN ('available','unavailable','no_data')),
    confidence     TEXT NOT NULL CHECK (confidence IN ('high','medium','low','none')),
    observed_at    TEXT NOT NULL,
    source_url     TEXT,
    raw_payload    TEXT,
    notes          TEXT
);

CREATE INDEX IF NOT EXISTS idx_competitor_obs_merchant_source_date
    ON competitor_observations(merchant_id, source_name, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_competitor_obs_observed_at
    ON competitor_observations(observed_at DESC);

CREATE TABLE IF NOT EXISTS price_recommendations (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_id                 TEXT NOT NULL REFERENCES merchants(merchant_id),
    computed_at                 TEXT NOT NULL DEFAULT (datetime('now')),
    online_sell                 REAL,
    in_mail_buy                 REAL,
    in_store_buy                REAL,
    electronic_buy              REAL,
    electronic_buy_sentinel     TEXT,
    no_data                     INTEGER NOT NULL DEFAULT 0,
    confidence                  TEXT NOT NULL,
    ebay_sell_pct_used          REAL,
    snapshot_config_json        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_recs_merchant_date
    ON price_recommendations(merchant_id, computed_at DESC);

CREATE TABLE IF NOT EXISTS published_prices (
    merchant_id                  TEXT PRIMARY KEY REFERENCES merchants(merchant_id),
    online_sell                  REAL,
    in_mail_buy                  REAL,
    in_store_buy                 REAL,
    electronic_buy               REAL,
    electronic_buy_sentinel      TEXT,
    published_at                 TEXT NOT NULL,
    based_on_recommendation_id   INTEGER REFERENCES price_recommendations(id),
    operator_action              TEXT NOT NULL CHECK (operator_action IN ('accept','override','skip')),
    operator_note                TEXT
);

CREATE TABLE IF NOT EXISTS operator_actions (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_id                 TEXT NOT NULL REFERENCES merchants(merchant_id),
    recommendation_id           INTEGER REFERENCES price_recommendations(id),
    action                      TEXT NOT NULL CHECK (action IN ('accept','override','skip')),
    override_online_sell        REAL,
    override_in_mail_buy        REAL,
    override_in_store_buy       REAL,
    override_electronic_buy     REAL,
    reason                      TEXT,
    actioned_at                 TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_actions_merchant
    ON operator_actions(merchant_id, actioned_at DESC);

CREATE TABLE IF NOT EXISTS refresh_runs (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at             TEXT NOT NULL,
    completed_at           TEXT,
    status                 TEXT NOT NULL CHECK (status IN ('running','completed','failed','partial')),
    merchants_processed    INTEGER,
    merchants_with_data    INTEGER,
    error_summary          TEXT
);
