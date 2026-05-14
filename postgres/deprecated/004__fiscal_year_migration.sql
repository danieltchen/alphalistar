-- Migration to fix fiscal_year column type from VARCHAR(4) to INTEGER

-- Fix BALANCESHEET table
BEGIN;

-- Add new integer column
ALTER TABLE BALANCESHEET ADD COLUMN fiscal_year_int INTEGER;

-- Copy data, converting string to integer
UPDATE BALANCESHEET SET fiscal_year_int = fiscal_year::INTEGER;

-- Drop old column and rename new one
ALTER TABLE BALANCESHEET DROP COLUMN fiscal_year;
ALTER TABLE BALANCESHEET RENAME COLUMN fiscal_year_int TO fiscal_year;

-- Add NOT NULL constraint
ALTER TABLE BALANCESHEET ALTER COLUMN fiscal_year SET NOT NULL;

-- Recreate the unique constraint with the new integer column
ALTER TABLE BALANCESHEET ADD CONSTRAINT balancesheet_unique_period 
    UNIQUE (tickerId, fiscal_year, fiscal_period_end, period_type);

COMMIT;

-- Fix INCOME table
BEGIN;

-- Add new integer column
ALTER TABLE INCOME ADD COLUMN fiscal_year_int INTEGER;

-- Copy data, converting string to integer
UPDATE INCOME SET fiscal_year_int = fiscal_year::INTEGER;

-- Drop old column and rename new one
ALTER TABLE INCOME DROP COLUMN fiscal_year;
ALTER TABLE INCOME RENAME COLUMN fiscal_year_int TO fiscal_year;

-- Add NOT NULL constraint
ALTER TABLE INCOME ALTER COLUMN fiscal_year SET NOT NULL;

-- Recreate the unique constraint with the new integer column
ALTER TABLE INCOME ADD CONSTRAINT income_unique_period 
    UNIQUE (tickerId, fiscal_year, fiscal_period_end, period_type);

COMMIT;

-- Fix CASHFLOW table
BEGIN;

-- Add new integer column
ALTER TABLE CASHFLOW ADD COLUMN fiscal_year_int INTEGER;

-- Copy data, converting string to integer
UPDATE CASHFLOW SET fiscal_year_int = fiscal_year::INTEGER;

-- Drop old column and rename new one
ALTER TABLE CASHFLOW DROP COLUMN fiscal_year;
ALTER TABLE CASHFLOW RENAME COLUMN fiscal_year_int TO fiscal_year;

-- Add NOT NULL constraint
ALTER TABLE CASHFLOW ALTER COLUMN fiscal_year SET NOT NULL;

-- Recreate the unique constraint with the new integer column
ALTER TABLE CASHFLOW ADD CONSTRAINT cashflow_unique_period 
    UNIQUE (tickerId, fiscal_year, fiscal_period_end, period_type);

COMMIT;

-- Add helpful comments
COMMENT ON COLUMN BALANCESHEET.fiscal_year IS 'Fiscal year as integer (e.g., 2024)';
COMMENT ON COLUMN INCOME.fiscal_year IS 'Fiscal year as integer (e.g., 2024)';
COMMENT ON COLUMN CASHFLOW.fiscal_year IS 'Fiscal year as integer (e.g., 2024)';

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_balancesheet_fiscal_year ON BALANCESHEET(fiscal_year);
CREATE INDEX IF NOT EXISTS idx_income_fiscal_year ON INCOME(fiscal_year);
CREATE INDEX IF NOT EXISTS idx_cashflow_fiscal_year ON CASHFLOW(fiscal_year);