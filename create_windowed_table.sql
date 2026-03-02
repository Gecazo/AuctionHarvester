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

CREATE INDEX IF NOT EXISTS idx_windowed_snapshots_avg_realm_id ON windowed_snapshots_avg(realm_id);
CREATE INDEX IF NOT EXISTS idx_windowed_snapshots_avg_item_id ON windowed_snapshots_avg(item_id);
CREATE INDEX IF NOT EXISTS idx_windowed_snapshots_avg_target_date ON windowed_snapshots_avg(target_date DESC);
CREATE INDEX IF NOT EXISTS idx_windowed_snapshots_avg_window ON windowed_snapshots_avg("window");
