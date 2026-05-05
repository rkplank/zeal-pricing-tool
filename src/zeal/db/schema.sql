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
    collection_method          TEXT NOT NULL CHECK (collection_method IN ('scraper')),
    refresh_interval_days      INTEGER NOT NULL DEFAULT 7,
    last_successful_refresh    TEXT,
    last_attempted_refresh     TEXT,
    notes                      TEXT,
    created_at                 TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at                 TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS competitor_observations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name    TEXT NOT NULL REFERENCES competitor_sources(source_name),
    merchant_id    TEXT NOT NULL REFERENCES merchants(merchant_id),
    channel        TEXT NOT NULL CHECK (channel IN ('buy_mail','buy_electronic','sell','marketplace_sell')),
    price_pct      REAL,
    availability   TEXT NOT NULL CHECK (availability IN ('available','unavailable','no_data')),
    confidence     TEXT NOT NULL CHECK (confidence IN ('high','medium','low','none')),
    observed_at    TEXT NOT NULL,
    source_url     TEXT,
    raw_payload    TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_comp_obs_lookup
    ON competitor_observations(source_name, merchant_id, channel, observed_at DESC);

CREATE TABLE IF NOT EXISTS refresh_runs (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    status                 TEXT NOT NULL CHECK (status IN ('running','completed','partial','failed')),
    started_at             TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at           TEXT,
    processed              INTEGER NOT NULL DEFAULT 0,
    total                  INTEGER NOT NULL DEFAULT 0,
    error                  TEXT
);

CREATE TABLE IF NOT EXISTS price_recommendations (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_id                 TEXT NOT NULL REFERENCES merchants(merchant_id),
    refresh_run_id              INTEGER NOT NULL REFERENCES refresh_runs(id),
    online_sell                 REAL,
    in_mail_buy                 REAL,
    in_store_buy                REAL,
    electronic_buy              REAL,
    ebay_sell_pct               REAL,
    ebay_confidence             TEXT NOT NULL CHECK (ebay_confidence IN ('high','medium','low','none')),
    no_data                     INTEGER NOT NULL DEFAULT 0 CHECK (no_data IN (0,1)),
    formula_breakdown_json      TEXT NOT NULL,
    config_snapshot_json        TEXT NOT NULL,
    computed_at                 TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_price_rec_merchant_time
    ON price_recommendations(merchant_id, computed_at DESC);

CREATE INDEX IF NOT EXISTS idx_price_rec_run
    ON price_recommendations(refresh_run_id);
