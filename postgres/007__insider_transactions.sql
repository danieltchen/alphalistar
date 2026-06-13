-- Insider transactions: SEC Forms 3, 4, 5 (initial ownership, changes, annual catch-up).
-- Star schema: insider dimension, insider_filing header, insider_transaction ledger,
-- insider_transaction_code reference, insider_position_current view.

CREATE TABLE IF NOT EXISTS insider (
    id SERIAL PRIMARY KEY,
    cik TEXT UNIQUE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_insider_name ON insider (name);

COMMENT ON TABLE insider IS 'Reporting insiders (officers, directors, 10%+ owners) deduplicated by SEC CIK when available';
COMMENT ON COLUMN insider.cik IS 'SEC CIK of the reporting person; unique when present';
COMMENT ON COLUMN insider.name IS 'Full name of the reporting insider';

CREATE TABLE IF NOT EXISTS insider_transaction_code (
    code VARCHAR(2) PRIMARY KEY,
    label TEXT NOT NULL,
    description TEXT NOT NULL
);

COMMENT ON TABLE insider_transaction_code IS 'SEC Form 4/5 transaction code reference for LLM-friendly joins';
COMMENT ON COLUMN insider_transaction_code.code IS 'Single-letter SEC transaction code (e.g. P, S, M, A)';
COMMENT ON COLUMN insider_transaction_code.label IS 'Short human-readable label';
COMMENT ON COLUMN insider_transaction_code.description IS 'Full description of the transaction type';

INSERT INTO insider_transaction_code (code, label, description)
VALUES
    ('P', 'Purchase', 'Open market or private purchase of securities'),
    ('S', 'Sale', 'Open market or private sale of securities'),
    ('A', 'Grant/Award', 'Grant, award, or other acquisition from the issuer'),
    ('D', 'Disposition to issuer', 'Disposition to the issuer (forfeiture, cancellation, etc.)'),
    ('M', 'Option exercise', 'Exercise or conversion of derivative security'),
    ('F', 'Tax withholding', 'Payment of exercise price or tax liability using shares'),
    ('G', 'Gift', 'Bona fide gift of securities'),
    ('C', 'Conversion', 'Conversion of derivative security'),
    ('V', 'Voluntary', 'Voluntary transaction with the issuer'),
    ('J', 'Other', 'Other acquisition or disposition'),
    ('K', 'Equity swap', 'Transaction in equity swap or similar instrument'),
    ('L', 'Small acquisition', 'Small acquisition under Rule 16a-6'),
    ('U', 'Tender offer', 'Disposition pursuant to tender offer in Rule 14d-1(b)'),
    ('W', 'Will acquisition', 'Acquisition or disposition by will or laws of descent'),
    ('X', 'In-the-money exercise', 'Exercise of in-the-money derivative'),
    ('Z', 'Deposit/withdrawal', 'Deposit into or withdrawal from voting trust')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS insider_filing (
    id SERIAL PRIMARY KEY,
    ticker_id INTEGER NOT NULL REFERENCES ticker(id) ON DELETE CASCADE,
    insider_id INTEGER NOT NULL REFERENCES insider(id) ON DELETE RESTRICT,
    accession_no TEXT NOT NULL UNIQUE,
    form_type VARCHAR(8) NOT NULL
        CHECK (form_type IN ('3', '4', '5', '3/A', '4/A', '5/A')),
    is_amendment BOOLEAN NOT NULL DEFAULT FALSE,
    filing_date DATE NOT NULL,
    reporting_period DATE,
    insider_name TEXT NOT NULL,
    issuer_name TEXT,
    position TEXT,
    is_director BOOLEAN,
    is_officer BOOLEAN,
    is_ten_pct_owner BOOLEAN,
    officer_title TEXT,
    primary_activity TEXT,
    net_change BIGINT,
    net_value NUMERIC(20, 2),
    remaining_shares BIGINT,
    has_10b5_1_plan BOOLEAN,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_insider_filing_ticker_date
    ON insider_filing (ticker_id, filing_date DESC);

CREATE INDEX IF NOT EXISTS idx_insider_filing_insider
    ON insider_filing (insider_id);

CREATE INDEX IF NOT EXISTS idx_insider_filing_accession
    ON insider_filing (accession_no);

COMMENT ON TABLE insider_filing IS 'One row per SEC Form 3, 4, or 5 insider ownership filing';
COMMENT ON COLUMN insider_filing.accession_no IS 'SEC EDGAR accession number; unique dedup key';
COMMENT ON COLUMN insider_filing.form_type IS 'Form type: 3 (initial), 4 (changes), 5 (annual catch-up), or amendment variants';
COMMENT ON COLUMN insider_filing.is_amendment IS 'True when form_type ends with /A';
COMMENT ON COLUMN insider_filing.reporting_period IS 'Transaction or reporting period date from the filing';
COMMENT ON COLUMN insider_filing.primary_activity IS 'Computed summary: Purchase, Sale, Grant/Award, Option Exercise, Mixed, etc.';
COMMENT ON COLUMN insider_filing.net_change IS 'Net shares acquired minus disposed in this filing (positive = net buy)';
COMMENT ON COLUMN insider_filing.net_value IS 'Net dollar value of transactions in this filing';
COMMENT ON COLUMN insider_filing.remaining_shares IS 'Insider position after all transactions in this filing';
COMMENT ON COLUMN insider_filing.has_10b5_1_plan IS 'True if trade under Rule 10b5-1 plan; False if discretionary; NULL if unknown';
COMMENT ON COLUMN insider_filing.completed IS 'True when all transaction lines have been extracted';

CREATE TABLE IF NOT EXISTS insider_transaction (
    id SERIAL PRIMARY KEY,
    insider_filing_id INTEGER NOT NULL REFERENCES insider_filing(id) ON DELETE CASCADE,
    ticker_id INTEGER NOT NULL REFERENCES ticker(id) ON DELETE CASCADE,
    insider_id INTEGER NOT NULL REFERENCES insider(id) ON DELETE RESTRICT,
    transaction_date DATE,
    security_title TEXT,
    transaction_code VARCHAR(2) REFERENCES insider_transaction_code(code) ON DELETE SET NULL,
    acquired_disposed CHAR(1) CHECK (acquired_disposed IS NULL OR acquired_disposed IN ('A', 'D')),
    shares NUMERIC(20, 4),
    price_per_share NUMERIC(20, 4),
    transaction_value NUMERIC(20, 2),
    ownership CHAR(1) CHECK (ownership IS NULL OR ownership IN ('D', 'I')),
    ownership_nature TEXT,
    shares_owned_following NUMERIC(20, 4),
    is_derivative BOOLEAN NOT NULL DEFAULT FALSE,
    exercise_price NUMERIC(20, 4),
    expiration_date DATE,
    underlying_security_title TEXT,
    underlying_shares NUMERIC(20, 4),
    is_10b5_1 BOOLEAN,
    footnotes TEXT,
    line_number INTEGER NOT NULL,
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_insider_transaction_grain UNIQUE (insider_filing_id, is_derivative, line_number)
);

CREATE INDEX IF NOT EXISTS idx_insider_transaction_ticker_date
    ON insider_transaction (ticker_id, transaction_date DESC);

CREATE INDEX IF NOT EXISTS idx_insider_transaction_insider
    ON insider_transaction (insider_id);

CREATE INDEX IF NOT EXISTS idx_insider_transaction_code
    ON insider_transaction (transaction_code);

CREATE INDEX IF NOT EXISTS idx_insider_transaction_filing
    ON insider_transaction (insider_filing_id);

COMMENT ON TABLE insider_transaction IS 'Transaction-level ledger: one row per line item in a Form 3/4/5 filing';
COMMENT ON COLUMN insider_transaction.transaction_code IS 'SEC code: P=purchase, S=sale, M=option exercise, A=grant, etc.';
COMMENT ON COLUMN insider_transaction.acquired_disposed IS 'A=acquired, D=disposed';
COMMENT ON COLUMN insider_transaction.ownership IS 'D=direct, I=indirect';
COMMENT ON COLUMN insider_transaction.is_derivative IS 'True for options, RSUs, and other derivative securities';
COMMENT ON COLUMN insider_transaction.shares_owned_following IS 'Shares held after this transaction line';
COMMENT ON COLUMN insider_transaction.is_10b5_1 IS 'True when this line was executed under a 10b5-1 plan';
COMMENT ON COLUMN insider_transaction.footnotes IS 'Resolved footnote text for price, share count, or plan context';

CREATE OR REPLACE VIEW insider_position_current AS
SELECT DISTINCT ON (
    t.ticker_id,
    t.insider_id,
    COALESCE(t.security_title, ''),
    t.is_derivative
)
    t.ticker_id,
    t.insider_id,
    t.security_title,
    t.is_derivative,
    t.shares_owned_following AS shares_held,
    t.transaction_date AS as_of_date,
    t.insider_filing_id,
    t.ownership,
    t.ownership_nature
FROM insider_transaction t
INNER JOIN insider_filing f ON f.id = t.insider_filing_id AND f.completed = TRUE
WHERE t.shares_owned_following IS NOT NULL
ORDER BY
    t.ticker_id,
    t.insider_id,
    COALESCE(t.security_title, ''),
    t.is_derivative,
    t.transaction_date DESC NULLS LAST,
    t.insider_filing_id DESC,
    t.line_number DESC;

COMMENT ON VIEW insider_position_current IS 'Latest known position per insider/security: most recent shares_owned_following from completed filings';

-- Allow insider_transactions in process run state
ALTER TABLE process_run_state DROP CONSTRAINT IF EXISTS chk_process_name;
ALTER TABLE process_run_state ADD CONSTRAINT chk_process_name CHECK (
    process_name IN ('stocks', 'financials', 'press_releases', 'insider_transactions')
);
