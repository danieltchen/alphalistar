-- ETF/fund support: raw yfinance quoteType on TICKER, fund metrics on FUNDAMENTALS.

ALTER TABLE TICKER
    ADD COLUMN IF NOT EXISTS quote_type VARCHAR(32),
    ADD COLUMN IF NOT EXISTS type_disp VARCHAR(32),
    ADD COLUMN IF NOT EXISTS legal_type TEXT,
    ADD COLUMN IF NOT EXISTS fund_family VARCHAR(128),
    ADD COLUMN IF NOT EXISTS category VARCHAR(128),
    ADD COLUMN IF NOT EXISTS fund_inception_date DATE;

ALTER TABLE FUNDAMENTALS
    ADD COLUMN IF NOT EXISTS nav_price DECIMAL(15,4),
    ADD COLUMN IF NOT EXISTS total_assets BIGINT,
    ADD COLUMN IF NOT EXISTS net_assets DECIMAL(20,2),
    ADD COLUMN IF NOT EXISTS net_expense_ratio DECIMAL(8,5),
    ADD COLUMN IF NOT EXISTS yield_pct DECIMAL(10,6),
    ADD COLUMN IF NOT EXISTS trailing_annual_dividend_rate DECIMAL(15,6),
    ADD COLUMN IF NOT EXISTS trailing_annual_dividend_yield DECIMAL(15,6),
    ADD COLUMN IF NOT EXISTS ytd_return DECIMAL(15,6),
    ADD COLUMN IF NOT EXISTS beta_three_year DECIMAL(15,6),
    ADD COLUMN IF NOT EXISTS three_year_average_return DECIMAL(15,6),
    ADD COLUMN IF NOT EXISTS five_year_average_return DECIMAL(15,6),
    ADD COLUMN IF NOT EXISTS trailing_three_month_returns DECIMAL(15,6),
    ADD COLUMN IF NOT EXISTS trailing_three_month_nav_returns DECIMAL(15,6);

COMMENT ON COLUMN TICKER.quote_type IS 'Raw yfinance quoteType (e.g. EQUITY, ETF, MUTUALFUND)';
COMMENT ON COLUMN TICKER.type_disp IS 'Display type from yfinance typeDisp';
COMMENT ON COLUMN TICKER.legal_type IS 'Legal structure from yfinance legalType';
COMMENT ON COLUMN TICKER.fund_family IS 'Fund family from yfinance fundFamily';
COMMENT ON COLUMN TICKER.category IS 'Fund category from yfinance category';
COMMENT ON COLUMN TICKER.fund_inception_date IS 'Fund inception date from yfinance fundInceptionDate';

COMMENT ON COLUMN FUNDAMENTALS.nav_price IS 'Net asset value per share from yfinance navPrice';
COMMENT ON COLUMN FUNDAMENTALS.total_assets IS 'Total assets under management from yfinance totalAssets';
COMMENT ON COLUMN FUNDAMENTALS.net_assets IS 'Net assets from yfinance netAssets';
COMMENT ON COLUMN FUNDAMENTALS.net_expense_ratio IS 'Net expense ratio from yfinance netExpenseRatio';
COMMENT ON COLUMN FUNDAMENTALS.yield_pct IS 'Fund yield from yfinance yield';
COMMENT ON COLUMN FUNDAMENTALS.trailing_annual_dividend_rate IS 'Trailing annual dividend rate from yfinance trailingAnnualDividendRate';
COMMENT ON COLUMN FUNDAMENTALS.trailing_annual_dividend_yield IS 'Trailing annual dividend yield from yfinance trailingAnnualDividendYield';
COMMENT ON COLUMN FUNDAMENTALS.ytd_return IS 'Year-to-date return from yfinance ytdReturn';
COMMENT ON COLUMN FUNDAMENTALS.beta_three_year IS 'Three-year beta from yfinance beta3Year';
COMMENT ON COLUMN FUNDAMENTALS.three_year_average_return IS 'Three-year average return from yfinance threeYearAverageReturn';
COMMENT ON COLUMN FUNDAMENTALS.five_year_average_return IS 'Five-year average return from yfinance fiveYearAverageReturn';
COMMENT ON COLUMN FUNDAMENTALS.trailing_three_month_returns IS 'Trailing three-month returns from yfinance trailingThreeMonthReturns';
COMMENT ON COLUMN FUNDAMENTALS.trailing_three_month_nav_returns IS 'Trailing three-month NAV returns from yfinance trailingThreeMonthNavReturns';
