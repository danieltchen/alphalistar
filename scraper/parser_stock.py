from typing import Dict, Tuple, Optional, List, Union, Any, ClassVar
from datetime import date, datetime
import pandas as pd
from pandas import DataFrame, Timestamp, Series
from pydantic import BaseModel, Field
import logging

# Type aliases
MarketDataValue = Union[int, float, date, str, datetime, None]
SQLQuery = str
SQLValues = tuple[MarketDataValue, ...]
SQLInsert = Tuple[SQLQuery, SQLValues]
TableResult = Tuple[SQLQuery, List[SQLInsert]]
ProcessingResult = Dict[str, TableResult]
MarketData = Dict[str, MarketDataValue]
CompanyInfo = Dict[str, Union[str, int, float, list, dict, None]]
TickerProfile = Dict[str, Any]

logger = logging.getLogger(__name__)


class StockPriceDataParser(BaseModel):
    symbol: str = Field(...)
    ticker_id: int = Field(...)

    # yfinance company.info keys -> TICKER column names (snake_case)
    YFINANCE_TO_TICKER_PROFILE: ClassVar[Dict[str, str]] = {
        "address1": "address_line_1",
        "city": "city",
        "state": "state",
        "zip": "zip",
        "country": "country",
        "phone": "phone",
        "website": "website",
        "industry": "industry",
        "industryKey": "industry_key",
        "industryDisp": "industry_disp",
        "sector": "sector",
        "sectorKey": "sector_key",
        "sectorDisp": "sector_disp",
        "fullTimeEmployees": "full_time_employees",
        "longBusinessSummary": "long_business_summary",
        "auditRisk": "audit_risk",
        "boardRisk": "board_risk",
        "compensationRisk": "compensation_risk",
        "shareHolderRightsRisk": "shareholder_rights_risk",
        "overallRisk": "overall_risk",
        "irWebsite": "ir_website",
        "currency": "currency",
        "fullExchangeName": "full_exchange_name",
        "corporateActions": "corporate_actions",
        "shortName": "name",
        "longName": "long_name",
        "displayName": "display_name",
        "quoteType": "quote_type",
        "typeDisp": "type_disp",
        "legalType": "legal_type",
        "fundFamily": "fund_family",
        "category": "category",
    }

    class Config:
        arbitrary_types_allowed = True

    @staticmethod
    def _epoch_seconds_to_date(epoch_value: Any) -> Optional[date]:
        """Convert yfinance fundInceptionDate (epoch seconds) to a date."""
        if epoch_value is None:
            return None
        try:
            epoch_int = int(epoch_value)
        except (TypeError, ValueError):
            return None
        if epoch_int <= 0:
            return None
        return datetime.fromtimestamp(epoch_int).date()

    def build_ticker_profile(self, company_info: Optional[CompanyInfo]) -> Optional[TickerProfile]:
        """Map yfinance company.info fields to TICKER profile column values."""
        if not company_info:
            return None
        profile: TickerProfile = {
            db_col: company_info.get(yf_key)
            for yf_key, db_col in self.YFINANCE_TO_TICKER_PROFILE.items()
        }
        profile["fund_inception_date"] = self._epoch_seconds_to_date(
            company_info.get("fundInceptionDate")
        )
        return profile

    def _convert_to_date(self, dt: Any) -> date:
        if isinstance(dt, date):
            return dt
        if isinstance(dt, (datetime, Timestamp)):
            return dt.date()
        return pd.Timestamp(dt).date()

    def process_price_data(self, price_df: DataFrame) -> TableResult:
        logger.info(f"Processing price data for {self.symbol}")
        create_sql = """
        CREATE TABLE IF NOT EXISTS PRICE (
            id SERIAL PRIMARY KEY,
            tickerId INTEGER NOT NULL,
            date DATE NOT NULL,
            open DECIMAL(10,2),
            high DECIMAL(10,2),
            low DECIMAL(10,2),
            close DECIMAL(10,2),
            volume BIGINT,
            FOREIGN KEY (tickerId) REFERENCES TICKER(id),
            UNIQUE(tickerId, date)
        );
        """

        inserts: List[SQLInsert] = []

        """ 
        Getting the following pandas warning for below: 
        FutureWarning: Calling int on a single element Series is deprecated and will raise a TypeError in the future. 
        Use int(ser.iloc[0]) instead
        
        "open": float(row["Open"]),
        "high": float(row["High"]),
        "low": float(row["Low"]),
        "close": float(row["Close"]),
        "volume": int(row["Volume"]),
        """

        for date_idx, row in price_df.iterrows():
            data: MarketData = {
                "tickerId": self.ticker_id,
                "date": self._convert_to_date(date_idx),
                "open": (
                    float(row["Open"].iloc[0])
                    if isinstance(row["Open"], Series)
                    else float(row["Open"])
                ),
                "high": (
                    float(row["High"].iloc[0])
                    if isinstance(row["High"], Series)
                    else float(row["High"])
                ),
                "low": (
                    float(row["Low"].iloc[0])
                    if isinstance(row["Low"], Series)
                    else float(row["Low"])
                ),
                "close": (
                    float(row["Close"].iloc[0])
                    if isinstance(row["Close"], Series)
                    else float(row["Close"])
                ),
                "volume": (
                    int(row["Volume"].iloc[0])
                    if isinstance(row["Volume"], Series)
                    else int(row["Volume"])
                ),
            }
            query = """
            INSERT INTO PRICE (tickerId, date, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tickerId, date) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume
            """
            values = tuple(data.values())
            inserts.append((query, values))

        return create_sql, inserts

    def process_split_data(self, split_df: DataFrame) -> TableResult:
        logger.info(f"Processing split data for {self.symbol}")
        create_sql = """
        CREATE TABLE IF NOT EXISTS SPLIT (
            id SERIAL PRIMARY KEY,
            tickerId INTEGER NOT NULL,
            date DATE NOT NULL,
            ratio DECIMAL(10,2),
            FOREIGN KEY (tickerId) REFERENCES TICKER(id),
            UNIQUE(tickerId, date)
        );
        """

        inserts: List[SQLInsert] = []
        for date_idx, row in split_df.iterrows():
            data: MarketData = {
                "tickerId": self.ticker_id,
                "date": self._convert_to_date(date_idx),
                "ratio": float(row.iloc[0]),
            }
            query = """
            INSERT INTO SPLIT (tickerId, date, ratio) 
            VALUES (%s, %s, %s)
            ON CONFLICT (tickerId, date) DO UPDATE SET
            ratio = EXCLUDED.ratio
            """
            values = tuple(data.values())
            inserts.append((query, values))

        return create_sql, inserts

    def _get_value_or_default(
        self,
        company_info: CompanyInfo,
        key: str,
        default: Union[int, float, str],
    ) -> Union[int, float, str]:
        """Get value from company_info dict or return default if missing/None."""
        value = company_info.get(key)
        if value is None:
            return default
        if isinstance(value, (int, float, str)):
            return value
        return default

    @staticmethod
    def _get_optional_value(
        company_info: CompanyInfo, key: str
    ) -> Optional[Union[int, float, str]]:
        """Return yfinance value or None when missing (for ETF/fund metrics)."""
        value = company_info.get(key)
        if value is None:
            return None
        if isinstance(value, (int, float, str)):
            return value
        return None

    def process_fundamentals(
        self,
        company_info: CompanyInfo,
        as_of_date: Optional[date] = None,
    ) -> TableResult:
        """
        Process company fundamentals data with comprehensive yfinance field coverage.

        Args:
            company_info: Dictionary containing company information from yfinance
            as_of_date: Optional date for the data (defaults to current date)

        Returns:
            TableResult containing SQL creation statement and insert statements
        """
        logger.info(f"Processing fundamentals for {self.symbol}")

        # CREATE TABLE statement with all yfinance fields
        create_sql = """
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
            
            -- ETF/fund metrics
            nav_price DECIMAL(15,4),
            total_assets BIGINT,
            net_assets DECIMAL(20,2),
            net_expense_ratio DECIMAL(8,5),
            yield_pct DECIMAL(10,6),
            trailing_annual_dividend_rate DECIMAL(15,6),
            trailing_annual_dividend_yield DECIMAL(15,6),
            ytd_return DECIMAL(15,6),
            beta_three_year DECIMAL(15,6),
            three_year_average_return DECIMAL(15,6),
            five_year_average_return DECIMAL(15,6),
            trailing_three_month_returns DECIMAL(15,6),
            trailing_three_month_nav_returns DECIMAL(15,6),
            
            FOREIGN KEY (tickerId) REFERENCES TICKER(id),
            UNIQUE(tickerId, date)
        );
        """

        # Process the data directly from yfinance output
        processing_date = (
            as_of_date if as_of_date is not None else datetime.now().date()
        )

        data: MarketData = {
            "tickerId": self.ticker_id,
            "date": processing_date,
            # Valuation metrics
            "trailingPE": self._get_value_or_default(company_info, "trailingPE", 0.0),
            "forwardPE": self._get_value_or_default(company_info, "forwardPE", 0.0),
            "marketCap": self._get_value_or_default(company_info, "marketCap", 0),
            "enterpriseValue": self._get_value_or_default(
                company_info, "enterpriseValue", 0
            ),
            "priceToBook": self._get_value_or_default(company_info, "priceToBook", 0.0),
            "trailingPegRatio": self._get_value_or_default(
                company_info, "trailingPegRatio", 0.0
            ),
            "priceToSalesTrailing12Months": self._get_value_or_default(
                company_info, "priceToSalesTrailing12Months", 0.0
            ),
            # Dividend metrics
            "dividendYield": self._get_value_or_default(
                company_info, "dividendYield", 0.0
            ),
            "dividendRate": self._get_value_or_default(
                company_info, "dividendRate", 0.0
            ),
            "payoutRatio": self._get_value_or_default(company_info, "payoutRatio", 0.0),
            "fiveYearAvgDividendYield": self._get_value_or_default(
                company_info, "fiveYearAvgDividendYield", 0.0
            ),
            # Risk and trading metrics
            "beta": self._get_value_or_default(company_info, "beta", 0.0),
            "volume": self._get_value_or_default(company_info, "volume", 0),
            "regularMarketVolume": self._get_value_or_default(
                company_info, "regularMarketVolume", 0
            ),
            "averageVolume": self._get_value_or_default(
                company_info, "averageVolume", 0
            ),
            # Price ranges and averages
            "fiftyTwoWeekLow": self._get_value_or_default(
                company_info, "fiftyTwoWeekLow", 0.0
            ),
            "fiftyTwoWeekHigh": self._get_value_or_default(
                company_info, "fiftyTwoWeekHigh", 0.0
            ),
            "fiftyTwoWeekRange": self._get_value_or_default(
                company_info, "fiftyTwoWeekRange", ""
            ),
            "fiftyTwoWeekChangePercent": self._get_value_or_default(
                company_info, "fiftyTwoWeekChangePercent", 0.0
            ),
            "fiftyTwoWeekLowChange": self._get_value_or_default(
                company_info, "fiftyTwoWeekLowChange", 0.0
            ),
            "fiftyTwoWeekLowChangePercent": self._get_value_or_default(
                company_info, "fiftyTwoWeekLowChangePercent", 0.0
            ),
            "fiftyTwoWeekHighChange": self._get_value_or_default(
                company_info, "fiftyTwoWeekHighChange", 0.0
            ),
            "fiftyTwoWeekHighChangePercent": self._get_value_or_default(
                company_info, "fiftyTwoWeekHighChangePercent", 0.0
            ),
            "fiftyDayAverage": self._get_value_or_default(
                company_info, "fiftyDayAverage", 0.0
            ),
            "fiftyDayAverageChange": self._get_value_or_default(
                company_info, "fiftyDayAverageChange", 0.0
            ),
            "fiftyDayAverageChangePercent": self._get_value_or_default(
                company_info, "fiftyDayAverageChangePercent", 0.0
            ),
            "twoHundredDayAverage": self._get_value_or_default(
                company_info, "twoHundredDayAverage", 0.0
            ),
            "twoHundredDayAverageChange": self._get_value_or_default(
                company_info, "twoHundredDayAverageChange", 0.0
            ),
            "twoHundredDayAverageChangePercent": self._get_value_or_default(
                company_info, "twoHundredDayAverageChangePercent", 0.0
            ),
            # Share metrics
            "floatShares": self._get_value_or_default(company_info, "floatShares", 0),
            "sharesOutstanding": self._get_value_or_default(
                company_info, "sharesOutstanding", 0
            ),
            "sharesShort": self._get_value_or_default(company_info, "sharesShort", 0),
            "bookValue": self._get_value_or_default(company_info, "bookValue", 0.0),
            # Earnings metrics
            "trailingEps": self._get_value_or_default(company_info, "trailingEps", 0.0),
            "forwardEps": self._get_value_or_default(company_info, "forwardEps", 0.0),
            "epsForward": self._get_value_or_default(company_info, "epsForward", 0.0),
            "earningsQuarterlyGrowth": self._get_value_or_default(
                company_info, "earningsQuarterlyGrowth", 0.0
            ),
            "earningsGrowth": self._get_value_or_default(
                company_info, "earningsGrowth", 0.0
            ),
            # Enterprise and revenue metrics
            "enterpriseToRevenue": self._get_value_or_default(
                company_info, "enterpriseToRevenue", 0.0
            ),
            "enterpriseToEbitda": self._get_value_or_default(
                company_info, "enterpriseToEbitda", 0.0
            ),
            "totalRevenue": self._get_value_or_default(company_info, "totalRevenue", 0),
            "revenueGrowth": self._get_value_or_default(
                company_info, "revenueGrowth", 0.0
            ),
            "revenuePerShare": self._get_value_or_default(
                company_info, "revenuePerShare", 0.0
            ),
            # Cash and debt metrics
            "totalCash": self._get_value_or_default(company_info, "totalCash", 0),
            "totalCashPerShare": self._get_value_or_default(
                company_info, "totalCashPerShare", 0.0
            ),
            "ebitda": self._get_value_or_default(company_info, "ebitda", 0),
            "totalDebt": self._get_value_or_default(company_info, "totalDebt", 0),
            "netIncomeToCommon": self._get_value_or_default(
                company_info, "netIncomeToCommon", 0
            ),
            "debtToEquity": self._get_value_or_default(
                company_info, "debtToEquity", 0.0
            ),
            # Liquidity ratios
            "quickRatio": self._get_value_or_default(company_info, "quickRatio", 0.0),
            "currentRatio": self._get_value_or_default(
                company_info, "currentRatio", 0.0
            ),
            # Profitability metrics
            "returnOnAssets": self._get_value_or_default(
                company_info, "returnOnAssets", 0.0
            ),
            "returnOnEquity": self._get_value_or_default(
                company_info, "returnOnEquity", 0.0
            ),
            "profitMargins": self._get_value_or_default(
                company_info, "profitMargins", 0.0
            ),
            "grossMargins": self._get_value_or_default(
                company_info, "grossMargins", 0.0
            ),
            "ebitdaMargins": self._get_value_or_default(
                company_info, "ebitdaMargins", 0.0
            ),
            "operatingMargins": self._get_value_or_default(
                company_info, "operatingMargins", 0.0
            ),
            "grossProfits": self._get_value_or_default(company_info, "grossProfits", 0),
            # Cash flow metrics
            "freeCashflow": self._get_value_or_default(company_info, "freeCashflow", 0),
            "operatingCashflow": self._get_value_or_default(
                company_info, "operatingCashflow", 0
            ),
            # Analyst and target metrics
            "averageAnalystRating": self._get_value_or_default(
                company_info, "averageAnalystRating", ""
            ),
            "recommendationMean": self._get_value_or_default(
                company_info, "recommendationMean", 0.0
            ),
            "recommendationKey": self._get_value_or_default(
                company_info, "recommendationKey", ""
            ),
            "numberOfAnalystOpinions": self._get_value_or_default(
                company_info, "numberOfAnalystOpinions", 0
            ),
            "targetHighPrice": self._get_value_or_default(
                company_info, "targetHighPrice", 0.0
            ),
            "targetLowPrice": self._get_value_or_default(
                company_info, "targetLowPrice", 0.0
            ),
            "targetMeanPrice": self._get_value_or_default(
                company_info, "targetMeanPrice", 0.0
            ),
            "targetMedianPrice": self._get_value_or_default(
                company_info, "targetMedianPrice", 0.0
            ),
            # ETF/fund metrics (NULL when not applicable)
            "nav_price": self._get_optional_value(company_info, "navPrice"),
            "total_assets": self._get_optional_value(company_info, "totalAssets"),
            "net_assets": self._get_optional_value(company_info, "netAssets"),
            "net_expense_ratio": self._get_optional_value(company_info, "netExpenseRatio"),
            "yield_pct": self._get_optional_value(company_info, "yield"),
            "trailing_annual_dividend_rate": self._get_optional_value(
                company_info, "trailingAnnualDividendRate"
            ),
            "trailing_annual_dividend_yield": self._get_optional_value(
                company_info, "trailingAnnualDividendYield"
            ),
            "ytd_return": self._get_optional_value(company_info, "ytdReturn"),
            "beta_three_year": self._get_optional_value(company_info, "beta3Year"),
            "three_year_average_return": self._get_optional_value(
                company_info, "threeYearAverageReturn"
            ),
            "five_year_average_return": self._get_optional_value(
                company_info, "fiveYearAverageReturn"
            ),
            "trailing_three_month_returns": self._get_optional_value(
                company_info, "trailingThreeMonthReturns"
            ),
            "trailing_three_month_nav_returns": self._get_optional_value(
                company_info, "trailingThreeMonthNavReturns"
            ),
        }

        # Generate column names and placeholders dynamically
        columns = list(data.keys())
        placeholders = ", ".join(["%s"] * len(columns))
        columns_str = ", ".join(columns)

        # Create update SET clause for conflict resolution (excluding primary key and unique constraint fields)
        excluded_from_update = {"tickerId", "date"}
        update_columns = [col for col in columns if col not in excluded_from_update]
        update_set_clause = ", ".join(
            [f"{col} = EXCLUDED.{col}" for col in update_columns]
        )

        query = f"""
        INSERT INTO FUNDAMENTALS ({columns_str}) 
        VALUES ({placeholders})
        ON CONFLICT (tickerId, date) DO UPDATE SET
        {update_set_clause}
        """

        values = tuple(data.values())

        logger.info(
            f"Successfully processed {len(columns)} fundamental metrics for {self.symbol}"
        )
        return create_sql, [(query, values)]
