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
    fetched_at TIMESTAMPTZ,
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
    raw JSONB NOT NULL,
    PRIMARY KEY (snapshot_id, auction_id)
);

CREATE INDEX IF NOT EXISTS idx_auctions_item_id ON auctions(item_id);
CREATE INDEX IF NOT EXISTS idx_auctions_snapshot_id ON auctions(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_realm_id ON snapshots(realm_id);
