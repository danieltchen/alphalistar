-- Canonical financial facts (replaces wide BALANCESHEET / INCOME / CASHFLOW).
-- Includes all financial_line seeds used by scraper/financial_gaap_map.py (single migration).

CREATE TABLE IF NOT EXISTS financial_line (
    line_code TEXT PRIMARY KEY,
    statement VARCHAR(16) NOT NULL
        CHECK (statement IN ('balance', 'income', 'cashflow')),
    display_name TEXT NOT NULL,
    synonyms JSONB NOT NULL DEFAULT '[]'::jsonb,
    us_gaap_tag TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_financial_line_statement
    ON financial_line (statement);

CREATE TABLE IF NOT EXISTS financial_fact (
    id SERIAL PRIMARY KEY,
    ticker_id INTEGER NOT NULL REFERENCES ticker(id) ON DELETE CASCADE,
    fiscal_year INTEGER NOT NULL,
    fiscal_period_end DATE NOT NULL,
    period_type VARCHAR(16) NOT NULL
        CHECK (period_type IN ('annual', 'quarterly')),
    quarter INTEGER CHECK (quarter IS NULL OR quarter BETWEEN 1 AND 4),
    line_code TEXT NOT NULL REFERENCES financial_line(line_code) ON DELETE RESTRICT,
    value BIGINT NOT NULL,
    decimals INTEGER,
    unit TEXT,
    scale INTEGER,
    source_concept TEXT NOT NULL,
    source_standard_concept TEXT,
    filing_accession TEXT,
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_financial_fact_grain UNIQUE (
        ticker_id,
        fiscal_year,
        fiscal_period_end,
        period_type,
        line_code
    )
);

CREATE INDEX IF NOT EXISTS idx_financial_fact_ticker_period
    ON financial_fact (ticker_id, fiscal_period_end DESC);

CREATE INDEX IF NOT EXISTS idx_financial_fact_line
    ON financial_fact (line_code);

INSERT INTO financial_line (line_code, statement, display_name, synonyms, us_gaap_tag, sort_order)
VALUES
    ('revenue', 'income', 'Revenue', '["revenue","sales","top line","total revenue"]'::jsonb, 'Revenues', 10),
    ('cost_of_revenue', 'income', 'Cost of revenue', '["cost of revenue","cost of sales","cogs"]'::jsonb, 'CostOfRevenue', 20),
    ('gross_profit', 'income', 'Gross profit', '["gross profit"]'::jsonb, 'GrossProfit', 30),
    ('operating_expenses', 'income', 'Operating expenses', '["operating expenses","opex"]'::jsonb, 'OperatingExpenses', 40),
    ('operating_income', 'income', 'Operating income', '["operating income","operating profit","op income"]'::jsonb, 'OperatingIncomeLoss', 50),
    ('income_before_tax', 'income', 'Income before tax', '["income before tax","pretax income","ebt"]'::jsonb, 'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItems', 55),
    ('ebit', 'income', 'EBIT', '["ebit","earnings before interest and taxes"]'::jsonb, 'EarningsBeforeInterestAndTaxes', 56),
    ('net_income', 'income', 'Net income', '["net income","net earnings","profit","bottom line"]'::jsonb, 'NetIncomeLoss', 60),
    ('research_and_development', 'income', 'Research and development', '["r&d","research and development"]'::jsonb, 'ResearchAndDevelopmentExpense', 70),
    ('selling_general_administrative', 'income', 'SG&A', '["sg&a","selling general administrative"]'::jsonb, 'SellingGeneralAndAdministrativeExpense', 80),
    ('interest_expense', 'income', 'Interest expense', '["interest expense"]'::jsonb, 'InterestExpense', 90),
    ('interest_income', 'income', 'Interest income', '["interest income"]'::jsonb, 'InterestIncomeExpenseNet', 95),
    ('income_tax_expense', 'income', 'Income tax expense', '["income tax","tax expense"]'::jsonb, 'IncomeTaxExpenseBenefit', 100),
    ('eps_basic', 'income', 'EPS (basic)', '["eps basic","earnings per share basic"]'::jsonb, 'EarningsPerShareBasic', 110),
    ('shares_weighted_avg_basic', 'income', 'Weighted average shares outstanding (basic)', '["wavg basic","basic shares"]'::jsonb, 'WeightedAverageNumberOfSharesOutstandingBasic', 115),
    ('eps_diluted', 'income', 'EPS (diluted)', '["eps diluted","earnings per share diluted"]'::jsonb, 'EarningsPerShareDiluted', 120),
    ('shares_weighted_avg_diluted', 'income', 'Weighted average shares outstanding (diluted)', '["wavg diluted"]'::jsonb, 'WeightedAverageNumberOfDilutedSharesOutstanding', 125),
    ('total_assets', 'balance', 'Total assets', '["total assets","assets"]'::jsonb, 'Assets', 200),
    ('current_assets', 'balance', 'Current assets', '["current assets"]'::jsonb, 'AssetsCurrent', 210),
    ('short_term_investments', 'balance', 'Short-term investments', '["marketable securities","st investments"]'::jsonb, 'MarketableSecuritiesCurrent', 215),
    ('cash_and_equivalents', 'balance', 'Cash and cash equivalents', '["cash","cash and equivalents","cash and cash equivalents"]'::jsonb, 'CashAndCashEquivalentsAtCarryingValue', 220),
    ('prepaid_expenses', 'balance', 'Prepaid expenses', '["prepaid","prepaids"]'::jsonb, 'PrepaidExpenseCurrent', 225),
    ('accounts_receivable', 'balance', 'Accounts receivable', '["accounts receivable","a/r","receivables"]'::jsonb, 'AccountsReceivableNetCurrent', 230),
    ('other_current_assets', 'balance', 'Other current assets', '["other current assets"]'::jsonb, 'OtherAssetsCurrent', 235),
    ('inventory', 'balance', 'Inventory', '["inventory","inventories"]'::jsonb, 'InventoryNet', 240),
    ('ppe_net', 'balance', 'Property, plant and equipment (net)', '["ppe","property plant equipment","pp&e"]'::jsonb, 'PropertyPlantAndEquipmentNet', 250),
    ('noncurrent_assets', 'balance', 'Non-current assets', '["long term assets","noncurrent assets"]'::jsonb, 'AssetsNoncurrent', 252),
    ('other_noncurrent_assets', 'balance', 'Other non-current assets', '["other long term assets"]'::jsonb, 'OtherAssetsNoncurrent', 255),
    ('goodwill', 'balance', 'Goodwill', '["goodwill"]'::jsonb, 'Goodwill', 260),
    ('intangible_assets_other', 'balance', 'Intangible assets (excl. goodwill)', '["intangibles","intangible assets"]'::jsonb, 'IntangibleAssetsNetExcludingGoodwill', 265),
    ('intangible_assets_other_noncurrent', 'balance', 'Intangible assets excl. goodwill (non-current)', '["intangibles noncurrent"]'::jsonb, 'IntangibleAssetsNetExcludingGoodwillNoncurrent', 267),
    ('total_liabilities', 'balance', 'Total liabilities', '["total liabilities","liabilities"]'::jsonb, 'Liabilities', 270),
    ('accounts_payable', 'balance', 'Accounts payable', '["a/p","trade payables"]'::jsonb, 'AccountsPayableCurrent', 275),
    ('current_liabilities', 'balance', 'Current liabilities', '["current liabilities"]'::jsonb, 'LiabilitiesCurrent', 280),
    ('accrued_liabilities', 'balance', 'Accrued and other current liabilities', '["accrued expenses","other current liabilities"]'::jsonb, 'AccruedLiabilitiesCurrent', 285),
    ('long_term_debt', 'balance', 'Long-term debt', '["long term debt","ltd"]'::jsonb, 'LongTermDebtNoncurrent', 290),
    ('deferred_revenue', 'balance', 'Deferred revenue / contract liabilities', '["contract liability","unearned revenue"]'::jsonb, 'ContractWithCustomerLiabilityCurrent', 295),
    ('debt_current', 'balance', 'Current portion of debt', '["short term debt","current debt"]'::jsonb, 'LongTermDebtCurrent', 305),
    ('commercial_paper', 'balance', 'Commercial paper', '["commercial paper","cp"]'::jsonb, 'CommercialPaper', 306),
    ('noncurrent_liabilities', 'balance', 'Non-current liabilities', '["long term liabilities","noncurrent liabilities"]'::jsonb, 'LiabilitiesNoncurrent', 312),
    ('operating_lease_liability', 'balance', 'Operating lease liabilities', '["lease liability","rou"]'::jsonb, 'OperatingLeaseLiability', 315),
    ('other_noncurrent_liabilities', 'balance', 'Other non-current liabilities', '["other long term liabilities"]'::jsonb, 'OtherLiabilitiesNoncurrent', 320),
    ('stockholders_equity', 'balance', 'Stockholders'' equity', '["equity","shareholders equity","stockholders equity"]'::jsonb, 'StockholdersEquity', 300),
    ('retained_earnings', 'balance', 'Retained earnings', '["retained earnings"]'::jsonb, 'RetainedEarningsAccumulatedDeficit', 310),
    ('accumulated_other_comprehensive_income', 'balance', 'Accumulated other comprehensive income (loss)', '["aoci","oci"]'::jsonb, 'AccumulatedOtherComprehensiveIncomeLossNetOfTax', 318),
    ('cashflow_operating', 'cashflow', 'Cash from operating activities', '["operating cash flow","cfo","cash from operations"]'::jsonb, 'NetCashProvidedByUsedInOperatingActivities', 400),
    ('cashflow_investing', 'cashflow', 'Cash from investing activities', '["investing cash flow","cfi"]'::jsonb, 'NetCashProvidedByUsedInInvestingActivities', 410),
    ('cashflow_financing', 'cashflow', 'Cash from financing activities', '["financing cash flow","cff"]'::jsonb, 'NetCashProvidedByUsedInFinancingActivities', 420),
    ('depreciation_amortization', 'cashflow', 'Depreciation and amortization', '["d&a","depreciation amortization"]'::jsonb, 'DepreciationDepletionAndAmortization', 430),
    ('capex', 'cashflow', 'Capital expenditures', '["capex","capital expenditures","pp&e purchases"]'::jsonb, 'PaymentsToAcquirePropertyPlantAndEquipment', 440)
ON CONFLICT (line_code) DO NOTHING;

-- DROP TABLE IF EXISTS balancesheet CASCADE;
-- DROP TABLE IF EXISTS income CASCADE;
-- DROP TABLE IF EXISTS cashflow CASCADE;
