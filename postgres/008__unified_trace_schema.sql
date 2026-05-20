-- v4__unified_trace_schema.sql
-- Migration to support unified SQL and Cypher query tracing

-- First, rename the existing SQL_ATTEMPTS table to the new unified name
-- This preserves existing data
ALTER TABLE SQL_ATTEMPTS RENAME TO QUERY_ATTEMPTS;

-- Add new columns to support Cypher queries
ALTER TABLE QUERY_ATTEMPTS 
ADD COLUMN query_type VARCHAR(10) DEFAULT 'sql' NOT NULL,
ADD COLUMN source_entities TEXT[]; -- For Neo4j node/relationship types

-- Rename the sql_query column to be more generic
ALTER TABLE QUERY_ATTEMPTS 
RENAME COLUMN sql_query TO query_text;

-- Update the column comments
COMMENT ON COLUMN QUERY_ATTEMPTS.query_text IS 'The SQL or Cypher query that was executed';
COMMENT ON COLUMN QUERY_ATTEMPTS.query_type IS 'Type of query: sql or cypher';
COMMENT ON COLUMN QUERY_ATTEMPTS.source_tables IS 'Array of table names for SQL queries';
COMMENT ON COLUMN QUERY_ATTEMPTS.source_entities IS 'Array of entity types for Cypher queries (nodes/relationships)';

-- Update the table comment
COMMENT ON TABLE QUERY_ATTEMPTS IS 'Stores SQL and Cypher query attempts and their results for each sub-query';

-- Add check constraint for query_type
ALTER TABLE QUERY_ATTEMPTS 
ADD CONSTRAINT chk_query_type CHECK (query_type IN ('sql', 'cypher'));

-- Update foreign key references to maintain data integrity
-- The foreign key name doesn't need to change as it still references the same table structure

-- Update indexes - rename to reflect the new unified approach
DROP INDEX IF EXISTS idx_sql_attempts_sub_query;
CREATE INDEX idx_query_attempts_sub_query ON QUERY_ATTEMPTS(sub_query_trace_id);
CREATE INDEX idx_query_attempts_query_type ON QUERY_ATTEMPTS(query_type);
CREATE INDEX idx_query_attempts_created ON QUERY_ATTEMPTS(created_at DESC);

-- Add composite index for common query patterns
CREATE INDEX idx_query_attempts_sub_query_type ON QUERY_ATTEMPTS(sub_query_trace_id, query_type);

-- Update table comments to reflect unified approach
COMMENT ON TABLE EXECUTION_TRACES IS 'Stores complete execution traces for financial query processing (SQL and Cypher)';
COMMENT ON TABLE SUB_QUERY_TRACES IS 'Stores individual sub-queries generated from complex questions (SQL and Cypher)';

-- Optional: If you want to preserve the old view for backward compatibility
CREATE VIEW SQL_ATTEMPTS AS
SELECT 
    id,
    sub_query_trace_id,
    attempt_number,
    query_text as sql_query,  -- Map back to old column name
    execution_time_ms,
    row_count,
    error_message,
    result_summary,
    source_tables,
    raw_results,
    created_at
FROM QUERY_ATTEMPTS 
WHERE query_type = 'sql';

-- Create a corresponding view for Cypher attempts
CREATE VIEW CYPHER_ATTEMPTS AS
SELECT 
    id,
    sub_query_trace_id,
    attempt_number,
    query_text as cypher_query,
    execution_time_ms,
    row_count,
    error_message,
    result_summary,
    source_entities,
    raw_results,
    created_at
FROM QUERY_ATTEMPTS 
WHERE query_type = 'cypher';

-- Add helpful views for analysis
CREATE VIEW QUERY_SUCCESS_RATES AS
SELECT 
    query_type,
    COUNT(*) as total_attempts,
    COUNT(CASE WHEN error_message IS NULL THEN 1 END) as successful_attempts,
    ROUND(
        COUNT(CASE WHEN error_message IS NULL THEN 1 END)::NUMERIC / 
        COUNT(*)::NUMERIC * 100, 2
    ) as success_rate_percent,
    AVG(execution_time_ms) as avg_execution_time_ms
FROM QUERY_ATTEMPTS
GROUP BY query_type;

-- Add parent trace reference
ALTER TABLE EXECUTION_TRACES 
ADD COLUMN parent_trace_id UUID REFERENCES EXECUTION_TRACES(id),
ADD COLUMN trace_level INTEGER DEFAULT 0,
ADD COLUMN orchestrator_type VARCHAR(50);

-- Index for efficient hierarchy queries
CREATE INDEX idx_execution_traces_parent ON EXECUTION_TRACES(parent_trace_id);
CREATE INDEX idx_execution_traces_hierarchy ON EXECUTION_TRACES(parent_trace_id, trace_level);

-- Grant necessary permissions
-- GRANT SELECT, INSERT, UPDATE, DELETE ON QUERY_ATTEMPTS TO your_application_user;
-- GRANT SELECT ON SQL_ATTEMPTS TO your_application_user; 
-- GRANT SELECT ON CYPHER_ATTEMPTS TO your_application_user;
-- GRANT SELECT ON QUERY_SUCCESS_RATES TO your_application_user;
