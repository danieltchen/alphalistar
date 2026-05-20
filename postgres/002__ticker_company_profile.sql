-- Ticker company profile from yfinance company.info (static fields, UPDATE by id).

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'ticker'
          AND column_name = 'exchange'
    ) THEN
        ALTER TABLE TICKER RENAME COLUMN exchange TO full_exchange_name;
    END IF;
END $$;

ALTER TABLE TICKER ALTER COLUMN full_exchange_name TYPE VARCHAR(64);

ALTER TABLE TICKER
    ADD COLUMN IF NOT EXISTS long_name TEXT,
    ADD COLUMN IF NOT EXISTS display_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS address_line_1 TEXT,
    ADD COLUMN IF NOT EXISTS city VARCHAR(128),
    ADD COLUMN IF NOT EXISTS state VARCHAR(64),
    ADD COLUMN IF NOT EXISTS zip VARCHAR(32),
    ADD COLUMN IF NOT EXISTS country VARCHAR(128),
    ADD COLUMN IF NOT EXISTS phone VARCHAR(64),
    ADD COLUMN IF NOT EXISTS website TEXT,
    ADD COLUMN IF NOT EXISTS industry TEXT,
    ADD COLUMN IF NOT EXISTS industry_key VARCHAR(128),
    ADD COLUMN IF NOT EXISTS industry_disp TEXT,
    ADD COLUMN IF NOT EXISTS sector TEXT,
    ADD COLUMN IF NOT EXISTS sector_key VARCHAR(128),
    ADD COLUMN IF NOT EXISTS sector_disp TEXT,
    ADD COLUMN IF NOT EXISTS full_time_employees INTEGER,
    ADD COLUMN IF NOT EXISTS long_business_summary TEXT,
    ADD COLUMN IF NOT EXISTS audit_risk SMALLINT,
    ADD COLUMN IF NOT EXISTS board_risk SMALLINT,
    ADD COLUMN IF NOT EXISTS compensation_risk SMALLINT,
    ADD COLUMN IF NOT EXISTS shareholder_rights_risk SMALLINT,
    ADD COLUMN IF NOT EXISTS overall_risk SMALLINT,
    ADD COLUMN IF NOT EXISTS ir_website TEXT,
    ADD COLUMN IF NOT EXISTS currency VARCHAR(16),
    ADD COLUMN IF NOT EXISTS corporate_actions JSONB;

ALTER TABLE FUNDAMENTALS DROP COLUMN IF EXISTS fulltimeemployees;

COMMENT ON COLUMN TICKER.name IS 'Company short name (yfinance shortName)';
COMMENT ON COLUMN TICKER.long_name IS 'Company long name (yfinance longName)';
COMMENT ON COLUMN TICKER.display_name IS 'Display name (yfinance displayName)';
COMMENT ON COLUMN TICKER.full_exchange_name IS 'Full exchange name (yfinance fullExchangeName)';
COMMENT ON COLUMN TICKER.address_line_1 IS 'Street address line 1 (yfinance address1)';
COMMENT ON COLUMN TICKER.city IS 'City (yfinance city)';
COMMENT ON COLUMN TICKER.state IS 'State or province (yfinance state)';
COMMENT ON COLUMN TICKER.zip IS 'Postal code (yfinance zip)';
COMMENT ON COLUMN TICKER.country IS 'Country (yfinance country)';
COMMENT ON COLUMN TICKER.phone IS 'Phone number (yfinance phone)';
COMMENT ON COLUMN TICKER.website IS 'Company website URL (yfinance website)';
COMMENT ON COLUMN TICKER.industry IS 'Industry label (yfinance industry)';
COMMENT ON COLUMN TICKER.industry_key IS 'Industry key slug (yfinance industryKey)';
COMMENT ON COLUMN TICKER.industry_disp IS 'Industry display label (yfinance industryDisp)';
COMMENT ON COLUMN TICKER.sector IS 'Sector label (yfinance sector)';
COMMENT ON COLUMN TICKER.sector_key IS 'Sector key slug (yfinance sectorKey)';
COMMENT ON COLUMN TICKER.sector_disp IS 'Sector display label (yfinance sectorDisp)';
COMMENT ON COLUMN TICKER.full_time_employees IS 'Full-time employee count (yfinance fullTimeEmployees)';
COMMENT ON COLUMN TICKER.long_business_summary IS 'Long business summary (yfinance longBusinessSummary)';
COMMENT ON COLUMN TICKER.audit_risk IS 'Audit risk score 1-10 (yfinance auditRisk)';
COMMENT ON COLUMN TICKER.board_risk IS 'Board risk score 1-10 (yfinance boardRisk)';
COMMENT ON COLUMN TICKER.compensation_risk IS 'Compensation risk score 1-10 (yfinance compensationRisk)';
COMMENT ON COLUMN TICKER.shareholder_rights_risk IS 'Shareholder rights risk score 1-10 (yfinance shareHolderRightsRisk)';
COMMENT ON COLUMN TICKER.overall_risk IS 'Overall governance risk score 1-10 (yfinance overallRisk)';
COMMENT ON COLUMN TICKER.ir_website IS 'Investor relations website (yfinance irWebsite)';
COMMENT ON COLUMN TICKER.currency IS 'Reporting currency (yfinance currency)';
COMMENT ON COLUMN TICKER.corporate_actions IS 'Recent corporate actions JSON array (yfinance corporateActions)';
