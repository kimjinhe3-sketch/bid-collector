CREATE TABLE IF NOT EXISTS bid_announcements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT    NOT NULL,
    bid_no          TEXT    NOT NULL,
    title           TEXT    NOT NULL,
    org_name        TEXT,
    region          TEXT,
    contract_method TEXT,
    estimated_price INTEGER,
    open_date       TEXT,
    close_date      TEXT,
    bid_type        TEXT,
    detail_url      TEXT,
    created_at      TEXT    DEFAULT CURRENT_TIMESTAMP,
    is_notified     INTEGER DEFAULT 0,
    UNIQUE(source, bid_no)
);

-- 기존 SQLite DB 에 컬럼 추가 (idempotent — 이미 있으면 에러 무시)
-- (Python init_db 가 ALTER TABLE 실패 시 무시하도록 처리)

CREATE INDEX IF NOT EXISTS idx_bids_created  ON bid_announcements(created_at);
CREATE INDEX IF NOT EXISTS idx_bids_open     ON bid_announcements(open_date);
CREATE INDEX IF NOT EXISTS idx_bids_notified ON bid_announcements(is_notified);
CREATE INDEX IF NOT EXISTS idx_bids_type     ON bid_announcements(bid_type);
