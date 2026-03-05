CREATE TABLE IF NOT EXISTS realms (
    id BIGSERIAL PRIMARY KEY,
    region TEXT NOT NULL,
    realm_slug TEXT NOT NULL,
    connected_realm_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (region, realm_slug)
);

CREATE TABLE IF NOT EXISTS snapshots (
    id BIGSERIAL PRIMARY KEY,
    realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    fetched_at TIMESTAMPTZ NOT NULL,
    source_file TEXT NOT NULL,
    auctions_count INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auctions (
    snapshot_id BIGINT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    auction_id BIGINT NOT NULL,
    item_id BIGINT,
    quantity INTEGER,
    bid BIGINT,
    buyout BIGINT,
    unit_price BIGINT,
    time_left TEXT,
    PRIMARY KEY (snapshot_id, auction_id)
);

CREATE TABLE IF NOT EXISTS daily_snapshots_avg (
    id BIGSERIAL PRIMARY KEY,
    realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    item_id BIGINT,
    fetched_at TIMESTAMPTZ NOT NULL,
    avg_buyout BIGINT,
    avg_bid BIGINT,
    avg_unit_price BIGINT,
    count_auctions BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (realm_id, item_id, fetched_at)
);

CREATE TABLE IF NOT EXISTS windowed_snapshots_avg (
    id BIGSERIAL PRIMARY KEY,
    realm_id BIGINT NOT NULL REFERENCES realms(id) ON DELETE CASCADE,
    item_id BIGINT NOT NULL,
    target_date DATE NOT NULL,
    "window" TEXT NOT NULL CHECK ("window" IN ('morning', 'day', 'evening', 'night')),
    fetched_at TIMESTAMPTZ NOT NULL,
    avg_buyout BIGINT,
    avg_bid BIGINT,
    avg_unit_price BIGINT,
    count_auctions BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (realm_id, item_id, target_date, "window")
);

CREATE INDEX IF NOT EXISTS idx_daily_snapshots_avg_realm_id ON daily_snapshots_avg(realm_id);
CREATE INDEX IF NOT EXISTS idx_daily_snapshots_avg_item_id ON daily_snapshots_avg(item_id);
CREATE INDEX IF NOT EXISTS idx_daily_snapshots_avg_fetched_at ON daily_snapshots_avg(fetched_at DESC);

CREATE INDEX IF NOT EXISTS idx_windowed_snapshots_avg_realm_id ON windowed_snapshots_avg(realm_id);
CREATE INDEX IF NOT EXISTS idx_windowed_snapshots_avg_item_id ON windowed_snapshots_avg(item_id);
CREATE INDEX IF NOT EXISTS idx_windowed_snapshots_avg_target_date ON windowed_snapshots_avg(target_date DESC);
CREATE INDEX IF NOT EXISTS idx_windowed_snapshots_avg_window ON windowed_snapshots_avg("window");

CREATE INDEX IF NOT EXISTS idx_auctions_item_id ON auctions(item_id);
CREATE INDEX IF NOT EXISTS idx_auctions_snapshot_id ON auctions(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_realm_id ON snapshots(realm_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_fetched_at ON snapshots(fetched_at DESC);
