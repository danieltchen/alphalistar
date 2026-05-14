"""
Curated US-GAAP (and common) local-name → (line_code, statement) for financial normalization.

Keys are produced by concept_mapper.normalize_xbrl_name (alphanumeric lowercase, local name only).
"""

from typing import Dict, Tuple

LineMapEntry = Tuple[str, str]  # (line_code, statement)

# (line_code, statement) — statement must match the statement slice (balance|income|cashflow).
GAAP_MAP: Dict[str, LineMapEntry] = {
    # Income — revenue / sales
    "revenues": ("revenue", "income"),
    "revenuefromcontractwithcustomerexcludingassessedtax": ("revenue", "income"),
    "revenuefromcontractwithcustomerincludingsubsidies": ("revenue", "income"),
    "salesrevenuenet": ("revenue", "income"),
    "salesrevenuegoodsnet": ("revenue", "income"),
    "salesrevenueservicesnet": ("revenue", "income"),
    "totalrevenue": ("revenue", "income"),
    "operatingrevenue": ("revenue", "income"),
    # Income — cost / margin
    "costofrevenue": ("cost_of_revenue", "income"),
    "costofgoodssold": ("cost_of_revenue", "income"),
    "costofgoodsandservicessold": ("cost_of_revenue", "income"),
    "costofservicessold": ("cost_of_revenue", "income"),
    "costofsales": ("cost_of_revenue", "income"),
    "grossprofit": ("gross_profit", "income"),
    # Income — operating
    "operatingexpenses": ("operating_expenses", "income"),
    "operatingcostsandexpenses": ("operating_expenses", "income"),
    "operatingincomeloss": ("operating_income", "income"),
    "incomelossfromcontinuingoperationsbeforeincometaxes": ("operating_income", "income"),
    "incomelossfromcontinuingoperationsbeforeincometaxesminorityinterestandincomelossfromequitymethodinvestments": (
        "operating_income",
        "income",
    ),
    "incomelossfromcontinuingoperationsbeforeincometaxesextraordinaryitemsnoncontrollinginterest": (
        "income_before_tax",
        "income",
    ),
    "researchanddevelopmentexpense": ("research_and_development", "income"),
    "sellinggeneralandadministrativeexpense": ("selling_general_administrative", "income"),
    # Income — bottom line
    "netincomeloss": ("net_income", "income"),
    "profitloss": ("net_income", "income"),
    "netincomelossavailabletocommonstockholdersbasic": ("net_income", "income"),
    "netincomelossattributabletocommonstockholdersbasicanddiluted": ("net_income", "income"),
    # Income — interest / tax / EPS
    "interestexpense": ("interest_expense", "income"),
    "interestincomeexpensenet": ("interest_income", "income"),
    "interestincomeexpenseafterprovisionforlosses": ("interest_income", "income"),
    "incometaxexpensebenefit": ("income_tax_expense", "income"),
    "incometaxexpensebenefitcontinuingoperations": ("income_tax_expense", "income"),
    "earningspersharebasic": ("eps_basic", "income"),
    "earningspersharediluted": ("eps_diluted", "income"),
    "weightedaveragenumberofsharesoutstandingbasic": ("shares_weighted_avg_basic", "income"),
    "weightedaveragenumberofdilutedsharesoutstanding": ("shares_weighted_avg_diluted", "income"),
    # Balance — totals
    "assets": ("total_assets", "balance"),
    "assetscurrent": ("current_assets", "balance"),
    "liabilities": ("total_liabilities", "balance"),
    "liabilitiescurrent": ("current_liabilities", "balance"),
    "stockholdersequity": ("stockholders_equity", "balance"),
    "equity": ("stockholders_equity", "balance"),
    "equityattributabletononcontrollinginterest": ("stockholders_equity", "balance"),
    "retainedearningsaccumulateddeficit": ("retained_earnings", "balance"),
    "retainedearnings": ("retained_earnings", "balance"),
    # Balance — working capital / PP&E
    "cashandcashequivalentsatcarryingvalue": ("cash_and_equivalents", "balance"),
    "cashcashequivalentsrestrictedcashandrestrictedcashequivalents": ("cash_and_equivalents", "balance"),
    "accountsreceivablenetcurrent": ("accounts_receivable", "balance"),
    "accountsreceivablenet": ("accounts_receivable", "balance"),
    "inventorynet": ("inventory", "balance"),
    "inventoryfinishedgoodnetofreserves": ("inventory", "balance"),
    "propertyplantandequipmentnet": ("ppe_net", "balance"),
    "goodwill": ("goodwill", "balance"),
    "longtermdebtnoncurrent": ("long_term_debt", "balance"),
    "longtermdebt": ("long_term_debt", "balance"),
    "longtermdebtandcapitalsecurity": ("long_term_debt", "balance"),
    "assetsnoncurrent": ("noncurrent_assets", "balance"),
    "liabilitiesnoncurrent": ("noncurrent_liabilities", "balance"),
    # Cash flow — summary
    "netcashprovidedbyusedinoperatingactivities": ("cashflow_operating", "cashflow"),
    "netcashprovidedbyusedininvestingactivities": ("cashflow_investing", "cashflow"),
    "netcashprovidedbyusedinfinancingactivities": ("cashflow_financing", "cashflow"),
    "depreciationdepletionandamortization": ("depreciation_amortization", "cashflow"),
    "depreciationandamortization": ("depreciation_amortization", "cashflow"),
    "paymentstoacquirepropertyplantandequipment": ("capex", "cashflow"),
    "paymentstoacquireproductivesets": ("capex", "cashflow"),
}

# Additional common US-GAAP local names (normalized) → existing or expanded line_code rows.
GAAP_MAP.update(
    {
        # Income — more revenue / COGS variants
        "revenuesnet": ("revenue", "income"),
        "netsales": ("revenue", "income"),
        "salesandrevenuenet": ("revenue", "income"),
        "revenuefromcontractwithcustomer": ("revenue", "income"),
        "revenuefromservices": ("revenue", "income"),
        "revenuefromgoods": ("revenue", "income"),
        "costofgoodssoldexclusivedepreciationshownseparately": ("cost_of_revenue", "income"),
        "costofservices": ("cost_of_revenue", "income"),
        "costofproductssold": ("cost_of_revenue", "income"),
        "grossprofitloss": ("gross_profit", "income"),
        "incomelossfromcontinuingoperationsbeforeincometaxes": ("operating_income", "income"),
        "incomelossfromcontinuingoperationsbeforeincometaxesextraordinaryitemsandcumulativeeffectofchangeinaccountingprinciple": (
            "operating_income",
            "income",
        ),
        "incomebeforetax": ("income_before_tax", "income"),
        "earningsbeforeinterestandtaxes": ("ebit", "income"),
        "operatingincome": ("operating_income", "income"),
        "nonoperatingincomeexpense": ("net_income", "income"),
        "otheroperatingincome": ("operating_income", "income"),
        "otheroperatingexpense": ("operating_expenses", "income"),
        "othernonoperatingincome": ("net_income", "income"),
        "othernonoperatingexpense": ("net_income", "income"),
        "netincomelossattributabletocommonstockholders": ("net_income", "income"),
        # Balance — cash / investments / receivables / payables
        "cash": ("cash_and_equivalents", "balance"),
        "cashandcashequivalentsatcarryingvalueincludingdiscontinuedoperations": (
            "cash_and_equivalents",
            "balance",
        ),
        "marketablesecuritiescurrent": ("short_term_investments", "balance"),
        "shortterminvestments": ("short_term_investments", "balance"),
        "availableforsalesecuritiescurrent": ("short_term_investments", "balance"),
        "prepaidexpenseandotherassetscurrent": ("prepaid_expenses", "balance"),
        "prepaidexpensecurrent": ("prepaid_expenses", "balance"),
        "otherassetscurrent": ("other_current_assets", "balance"),
        "otherassetsnoncurrent": ("other_noncurrent_assets", "balance"),
        "intangibleassetsnetexcludinggoodwill": ("intangible_assets_other", "balance"),
        "finiteintangibleassetsnet": ("intangible_assets_other", "balance"),
        "indefinitelivedintangibleassetsnet": ("intangible_assets_other", "balance"),
        "accountspayablecurrent": ("accounts_payable", "balance"),
        "accountspayabletradecurrent": ("accounts_payable", "balance"),
        "employeerelatedliabilitiescurrent": ("accrued_liabilities", "balance"),
        "accruedliabilitiescurrent": ("accrued_liabilities", "balance"),
        "otherliabilitiescurrent": ("accrued_liabilities", "balance"),
        "contractwithcustomerliabilitycurrent": ("deferred_revenue", "balance"),
        "contractwithcustomerliability": ("deferred_revenue", "balance"),
        "deferredrevenuecurrent": ("deferred_revenue", "balance"),
        "deferredrevenue": ("deferred_revenue", "balance"),
        "longtermdebtcurrent": ("debt_current", "balance"),
        "shorttermborrowings": ("debt_current", "balance"),
        "commercialpaper": ("commercial_paper", "balance"),
        "longtermdebtandcapitalsecuritycurrent": ("debt_current", "balance"),
        "operatingleaseliabilitynoncurrent": ("operating_lease_liability", "balance"),
        "operatingleaseliabilitycurrent": ("operating_lease_liability", "balance"),
        "leaseobligation": ("operating_lease_liability", "balance"),
        "noncontrollinginterest": ("stockholders_equity", "balance"),
        "temporaryequitycarryingamountattributabletoparent": ("stockholders_equity", "balance"),
        "commonstockincludingadditionalpaidincapital": ("stockholders_equity", "balance"),
        "commonstocksincludingadditionalpaidincapital": ("stockholders_equity", "balance"),
        "commonstockvalue": ("stockholders_equity", "balance"),
        "additionalpaidincapital": ("stockholders_equity", "balance"),
        "treasurystockvalue": ("stockholders_equity", "balance"),
        "accumulatedothercomprehensiveincomelossnetoftax": (
            "accumulated_other_comprehensive_income",
            "balance",
        ),
        "marketablesecuritiesnoncurrent": ("other_noncurrent_assets", "balance"),
        "nontradereceivablescurrent": ("other_current_assets", "balance"),
        "otherliabilitiesnoncurrent": ("other_noncurrent_liabilities", "balance"),
        "intangibleassetsnetexcludinggoodwillnoncurrent": (
            "intangible_assets_other_noncurrent",
            "balance",
        ),
    }
)
