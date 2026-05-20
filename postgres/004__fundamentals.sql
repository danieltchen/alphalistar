CREATE TABLE IF NOT EXISTS FUNDAMENTALS (
    id SERIAL PRIMARY KEY,
    tickerId INTEGER NOT NULL,
    date DATE NOT NULL,
    
    -- Valuation metrics
    trailingPE DECIMAL(15,6),
    forwardPE DECIMAL(15,6),
    marketCap BIGINT,
    enterpriseValue BIGINT,
    priceToBook DECIMAL(15,6),
    trailingPegRatio DECIMAL(15,6),
    priceToSalesTrailing12Months DECIMAL(15,6),
    
    -- Dividend metrics
    dividendYield DECIMAL(15,6),
    dividendRate DECIMAL(15,6),
    payoutRatio DECIMAL(15,6),
    fiveYearAvgDividendYield DECIMAL(15,6),
    
    -- Risk and trading metrics
    beta DECIMAL(15,6),
    volume BIGINT,
    regularMarketVolume BIGINT,
    averageVolume BIGINT,
    
    -- Price ranges and averages
    fiftyTwoWeekLow DECIMAL(15,4),
    fiftyTwoWeekHigh DECIMAL(15,4),
    fiftyTwoWeekRange VARCHAR(50),
    fiftyTwoWeekChange DECIMAL(15,6),
    fiftyTwoWeekChangePercent DECIMAL(15,6),
    fiftyTwoWeekLowChange DECIMAL(15,4),
    fiftyTwoWeekLowChangePercent DECIMAL(15,6),
    fiftyTwoWeekHighChange DECIMAL(15,4),
    fiftyTwoWeekHighChangePercent DECIMAL(15,6),
    fiftyDayAverage DECIMAL(15,4),
    fiftyDayAverageChange DECIMAL(15,4),
    fiftyDayAverageChangePercent DECIMAL(15,6),
    twoHundredDayAverage DECIMAL(15,4),
    twoHundredDayAverageChange DECIMAL(15,4),
    twoHundredDayAverageChangePercent DECIMAL(15,6),
    
    -- Share metrics
    floatShares BIGINT,
    sharesOutstanding BIGINT,
    sharesShort BIGINT,
    bookValue DECIMAL(15,4),
    
    -- Earnings metrics
    trailingEps DECIMAL(15,6),
    forwardEps DECIMAL(15,6),
    epsForward DECIMAL(15,6),
    earningsQuarterlyGrowth DECIMAL(15,6),
    earningsGrowth DECIMAL(15,6),
    
    -- Enterprise and revenue metrics
    enterpriseToRevenue DECIMAL(15,6),
    enterpriseToEbitda DECIMAL(15,6),
    totalRevenue BIGINT,
    revenueGrowth DECIMAL(15,6),
    revenuePerShare DECIMAL(15,6),
    
    -- Cash and debt metrics
    totalCash BIGINT,
    totalCashPerShare DECIMAL(15,6),
    ebitda BIGINT,
    totalDebt BIGINT,
    netIncomeToCommon BIGINT,
    debtToEquity DECIMAL(15,6),
    
    -- Liquidity ratios
    quickRatio DECIMAL(15,6),
    currentRatio DECIMAL(15,6),
    
    -- Profitability metrics
    returnOnAssets DECIMAL(15,6),
    returnOnEquity DECIMAL(15,6),
    profitMargins DECIMAL(15,6),
    grossMargins DECIMAL(15,6),
    ebitdaMargins DECIMAL(15,6),
    operatingMargins DECIMAL(15,6),
    grossProfits BIGINT,
    
    -- Cash flow metrics
    freeCashflow BIGINT,
    operatingCashflow BIGINT,
    
    -- Analyst and target metrics
    averageAnalystRating VARCHAR(50),
    recommendationMean DECIMAL(15,6),
    recommendationKey VARCHAR(50),
    numberOfAnalystOpinions INTEGER,
    targetHighPrice DECIMAL(15,4),
    targetLowPrice DECIMAL(15,4),
    targetMeanPrice DECIMAL(15,6),
    targetMedianPrice DECIMAL(15,6),
    
    FOREIGN KEY (tickerId) REFERENCES TICKER(id),
    UNIQUE(tickerId, date)
);


-- ALTER TABLE FUNDAMENTALS
-- -- Add FUNDAMENTALS table comment
-- COMMENT ON TABLE FUNDAMENTALS IS 'Comprehensive fundamental financial data for publicly traded companies, including valuation metrics, financial ratios, trading data, and analyst information. Updated regularly with latest market data.';

-- -- Primary key and foreign key comments
-- COMMENT ON COLUMN FUNDAMENTALS.id IS 'Primary key - unique identifier for each fundamental data record';
-- COMMENT ON COLUMN FUNDAMENTALS.tickerId IS 'Foreign key reference to TICKER table - identifies the company';
-- COMMENT ON COLUMN FUNDAMENTALS.date IS 'Date when this fundamental data was recorded or updated';

-- -- Valuation metrics
-- COMMENT ON COLUMN FUNDAMENTALS.trailingPE IS 'Trailing Price-to-Earnings ratio - current stock price divided by earnings per share over the last 12 months';
-- COMMENT ON COLUMN FUNDAMENTALS.forwardPE IS 'Forward Price-to-Earnings ratio - current stock price divided by expected earnings per share for next 12 months';
-- COMMENT ON COLUMN FUNDAMENTALS.marketCap IS 'Market capitalization - total value of all outstanding shares (shares outstanding x current stock price)';
-- COMMENT ON COLUMN FUNDAMENTALS.enterpriseValue IS 'Enterprise Value - market cap plus total debt minus cash and cash equivalents';
-- COMMENT ON COLUMN FUNDAMENTALS.priceToBook IS 'Price-to-Book ratio - stock price divided by book value per share';
-- COMMENT ON COLUMN FUNDAMENTALS.trailingPegRatio IS 'Price/Earnings to Growth ratio - PE ratio divided by earnings growth rate';
-- COMMENT ON COLUMN FUNDAMENTALS.priceToSalesTrailing12Months IS 'Price-to-Sales ratio - market cap divided by trailing 12-month revenue';

-- -- Dividend metrics
-- COMMENT ON COLUMN FUNDAMENTALS.dividendYield IS 'Annual dividend yield as percentage - annual dividends per share divided by stock price';
-- COMMENT ON COLUMN FUNDAMENTALS.dividendRate IS 'Annual dividend rate per share in dollars';
-- COMMENT ON COLUMN FUNDAMENTALS.payoutRatio IS 'Dividend payout ratio - percentage of earnings paid out as dividends';
-- COMMENT ON COLUMN FUNDAMENTALS.fiveYearAvgDividendYield IS 'Average dividend yield over the past 5 years';

-- -- Risk and trading metrics
-- COMMENT ON COLUMN FUNDAMENTALS.beta IS 'Beta coefficient - measure of stock volatility relative to overall market (1.0 = same as market)';
-- COMMENT ON COLUMN FUNDAMENTALS.volume IS 'Current trading volume - number of shares traded';
-- COMMENT ON COLUMN FUNDAMENTALS.regularMarketVolume IS 'Regular market trading volume during normal trading hours';
-- COMMENT ON COLUMN FUNDAMENTALS.averageVolume IS 'Average daily trading volume over recent period';

-- -- Price ranges and averages
-- COMMENT ON COLUMN FUNDAMENTALS.fiftyTwoWeekLow IS 'Lowest stock price in the past 52 weeks';
-- COMMENT ON COLUMN FUNDAMENTALS.fiftyTwoWeekHigh IS 'Highest stock price in the past 52 weeks';
-- COMMENT ON COLUMN FUNDAMENTALS.fiftyTwoWeekRange IS 'Stock price range over 52 weeks in format "low - high"';
-- COMMENT ON COLUMN FUNDAMENTALS.fiftyTwoWeekChangePercent IS 'Percentage price change over 52-week period';
-- COMMENT ON COLUMN FUNDAMENTALS.fiftyTwoWeekLowChange IS 'Price change from 52-week low to current price';
-- COMMENT ON COLUMN FUNDAMENTALS.fiftyTwoWeekLowChangePercent IS 'Percentage change from 52-week low';
-- COMMENT ON COLUMN FUNDAMENTALS.fiftyTwoWeekHighChange IS 'Price change from 52-week high to current price';
-- COMMENT ON COLUMN FUNDAMENTALS.fiftyTwoWeekHighChangePercent IS 'Percentage change from 52-week high';
-- COMMENT ON COLUMN FUNDAMENTALS.fiftyDayAverage IS '50-day moving average stock price';
-- COMMENT ON COLUMN FUNDAMENTALS.fiftyDayAverageChange IS 'Change from 50-day moving average to current price';
-- COMMENT ON COLUMN FUNDAMENTALS.fiftyDayAverageChangePercent IS 'Percentage change from 50-day moving average';
-- COMMENT ON COLUMN FUNDAMENTALS.twoHundredDayAverage IS '200-day moving average stock price';
-- COMMENT ON COLUMN FUNDAMENTALS.twoHundredDayAverageChange IS 'Change from 200-day moving average to current price';
-- COMMENT ON COLUMN FUNDAMENTALS.twoHundredDayAverageChangePercent IS 'Percentage change from 200-day moving average';

-- -- Share metrics
-- COMMENT ON COLUMN FUNDAMENTALS.floatShares IS 'Number of shares available for public trading (excludes restricted shares)';
-- COMMENT ON COLUMN FUNDAMENTALS.sharesOutstanding IS 'Total number of shares currently issued and outstanding';
-- COMMENT ON COLUMN FUNDAMENTALS.sharesShort IS 'Number of shares currently sold short by investors';
-- COMMENT ON COLUMN FUNDAMENTALS.bookValue IS 'Book value per share - total shareholders equity divided by shares outstanding';

-- -- Earnings metrics
-- COMMENT ON COLUMN FUNDAMENTALS.trailingEps IS 'Trailing 12-month earnings per share';
-- COMMENT ON COLUMN FUNDAMENTALS.forwardEps IS 'Forward/expected earnings per share for next 12 months';
-- COMMENT ON COLUMN FUNDAMENTALS.epsForward IS 'Forward-looking earnings per share estimate';
-- COMMENT ON COLUMN FUNDAMENTALS.earningsQuarterlyGrowth IS 'Year-over-year earnings growth for most recent quarter';
-- COMMENT ON COLUMN FUNDAMENTALS.earningsGrowth IS 'Expected earnings growth rate';

-- -- Enterprise and revenue metrics
-- COMMENT ON COLUMN FUNDAMENTALS.enterpriseToRevenue IS 'Enterprise Value to Revenue ratio - EV divided by trailing 12-month revenue';
-- COMMENT ON COLUMN FUNDAMENTALS.enterpriseToEbitda IS 'Enterprise Value to EBITDA ratio - common valuation metric';
-- COMMENT ON COLUMN FUNDAMENTALS.totalRevenue IS 'Total revenue for trailing 12 months';
-- COMMENT ON COLUMN FUNDAMENTALS.revenueGrowth IS 'Year-over-year revenue growth rate';
-- COMMENT ON COLUMN FUNDAMENTALS.revenuePerShare IS 'Revenue per share - total revenue divided by shares outstanding';

-- -- Cash and debt metrics
-- COMMENT ON COLUMN FUNDAMENTALS.totalCash IS 'Total cash and cash equivalents on balance sheet';
-- COMMENT ON COLUMN FUNDAMENTALS.totalCashPerShare IS 'Cash and cash equivalents per share outstanding';
-- COMMENT ON COLUMN FUNDAMENTALS.ebitda IS 'Earnings Before Interest, Taxes, Depreciation, and Amortization';
-- COMMENT ON COLUMN FUNDAMENTALS.totalDebt IS 'Total debt including short-term and long-term debt';
-- COMMENT ON COLUMN FUNDAMENTALS.netIncomeToCommon IS 'Net income available to common shareholders';
-- COMMENT ON COLUMN FUNDAMENTALS.debtToEquity IS 'Debt-to-Equity ratio - total debt divided by shareholders equity';

-- -- Liquidity ratios
-- COMMENT ON COLUMN FUNDAMENTALS.quickRatio IS 'Quick ratio - (current assets - inventory) ÷ current liabilities';
-- COMMENT ON COLUMN FUNDAMENTALS.currentRatio IS 'Current ratio - current assets divided by current liabilities';

-- -- Profitability metrics
-- COMMENT ON COLUMN FUNDAMENTALS.returnOnAssets IS 'Return on Assets (ROA) - net income divided by total assets';
-- COMMENT ON COLUMN FUNDAMENTALS.returnOnEquity IS 'Return on Equity (ROE) - net income divided by shareholders equity';
-- COMMENT ON COLUMN FUNDAMENTALS.profitMargins IS 'Net profit margin - net income divided by revenue';
-- COMMENT ON COLUMN FUNDAMENTALS.grossMargins IS 'Gross profit margin - gross profit divided by revenue';
-- COMMENT ON COLUMN FUNDAMENTALS.ebitdaMargins IS 'EBITDA margin - EBITDA divided by revenue';
-- COMMENT ON COLUMN FUNDAMENTALS.operatingMargins IS 'Operating margin - operating income divided by revenue';
-- COMMENT ON COLUMN FUNDAMENTALS.grossProfits IS 'Total gross profit - revenue minus cost of goods sold';

-- -- Cash flow metrics
-- COMMENT ON COLUMN FUNDAMENTALS.freeCashflow IS 'Free cash flow - operating cash flow minus capital expenditures';
-- COMMENT ON COLUMN FUNDAMENTALS.operatingCashflow IS 'Cash flow from operating activities';

-- -- Analyst and target metrics
-- COMMENT ON COLUMN FUNDAMENTALS.averageAnalystRating IS 'Average analyst recommendation (e.g., "Strong Buy", "Buy", "Hold")';
-- COMMENT ON COLUMN FUNDAMENTALS.recommendationMean IS 'Mean analyst recommendation score (1=Strong Buy, 5=Strong Sell)';
-- COMMENT ON COLUMN FUNDAMENTALS.recommendationKey IS 'Text description of analyst recommendation consensus';
-- COMMENT ON COLUMN FUNDAMENTALS.numberOfAnalystOpinions IS 'Number of analysts providing recommendations';
-- COMMENT ON COLUMN FUNDAMENTALS.targetHighPrice IS 'Highest analyst price target';
-- COMMENT ON COLUMN FUNDAMENTALS.targetLowPrice IS 'Lowest analyst price target';
-- COMMENT ON COLUMN FUNDAMENTALS.targetMeanPrice IS 'Average/mean analyst price target';
-- COMMENT ON COLUMN FUNDAMENTALS.targetMedianPrice IS 'Median analyst price target';

-- -- Add PRICE table comment
-- COMMENT ON TABLE PRICE IS 'Historical daily stock price data including open, high, low, close prices and trading volume. Contains daily market data for technical analysis, price trends, and trading patterns.';

-- -- Primary key and foreign key comments
-- COMMENT ON COLUMN PRICE.id IS 'Primary key - unique identifier for each daily price record';
-- COMMENT ON COLUMN PRICE.tickerId IS 'Foreign key reference to TICKER table - identifies the company whose stock price this record represents';
-- COMMENT ON COLUMN PRICE.date IS 'Trading date for this price data (market business days only, excludes weekends and holidays)';

-- -- Price data columns
-- COMMENT ON COLUMN PRICE.open IS 'Opening stock price at market open - first traded price of the trading day';
-- COMMENT ON COLUMN PRICE.high IS 'Highest stock price during the trading day - peak intraday price';
-- COMMENT ON COLUMN PRICE.low IS 'Lowest stock price during the trading day - trough intraday price';
-- COMMENT ON COLUMN PRICE.close IS 'Closing stock price at market close - last traded price of the trading day, used for most calculations';
-- COMMENT ON COLUMN PRICE.volume IS 'Total number of shares traded during the trading day - indicates liquidity and investor interest';

-- -- Add SPLIT table comment
-- COMMENT ON TABLE SPLIT IS 'Stock split and stock dividend events that affect share count and price. Records when companies split their shares to adjust stock price levels, making shares more accessible to investors. Essential for accurate historical price analysis.';

-- -- Primary key and foreign key comments
-- COMMENT ON COLUMN SPLIT.id IS 'Primary key - unique identifier for each stock split event';
-- COMMENT ON COLUMN SPLIT.tickerId IS 'Foreign key reference to TICKER table - identifies the company that executed the stock split';
-- COMMENT ON COLUMN SPLIT.date IS 'Effective date when the stock split took place - the date when shares were actually split and trading began at adjusted prices';

-- -- Split ratio column
-- COMMENT ON COLUMN SPLIT.ratio IS 'Stock split ratio indicating how shares were divided. For example: 2.0 = 2-for-1 split (each share becomes 2 shares, price halved), 0.5 = 1-for-2 reverse split (2 shares become 1 share, price doubled). Used to adjust historical prices for accurate analysis.';