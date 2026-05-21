-- Seed schema + sample data for the DashML demo stack.
-- Auto-run by Postgres at first container init.

CREATE TABLE IF NOT EXISTS startup_funding (
    company_name    TEXT,
    industry        TEXT,
    country         TEXT,
    city            TEXT,
    stage           TEXT,
    funding_date    DATE,
    funding_amount  NUMERIC(10, 2),
    valuation       NUMERIC(12, 2),
    employees       INTEGER,
    founded_year    INTEGER
);

COPY startup_funding
    FROM '/tmp/startup_funding.csv'
    WITH (FORMAT CSV, HEADER TRUE);

-- Useful indexes for the demo dashboards.
CREATE INDEX IF NOT EXISTS idx_startup_industry ON startup_funding (industry);
CREATE INDEX IF NOT EXISTS idx_startup_country  ON startup_funding (country);
CREATE INDEX IF NOT EXISTS idx_startup_stage    ON startup_funding (stage);
CREATE INDEX IF NOT EXISTS idx_startup_date     ON startup_funding (funding_date);
