-- Execution trace schema: root traces, sub-queries, unified query attempts (SQL + pgvector retrieval).
-- Replaces legacy migrations 007 + 008 + 009 (no SQL_ATTEMPTS rename path; QUERY_ATTEMPTS created directly).

DROP TABLE IF EXISTS QUERY_ATTEMPTS CASCADE;
DROP TABLE IF EXISTS SUB_QUERY_TRACES CASCADE;
DROP TABLE IF EXISTS EXECUTION_TRACES CASCADE;
-- Legacy table name from older installs
DROP TABLE IF EXISTS SQL_ATTEMPTS CASCADE;

CREATE TABLE IF NOT EXISTS USERS (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO USERS (username)
VALUES ('admin')
ON CONFLICT (username) DO NOTHING;

CREATE TABLE EXECUTION_TRACES (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL DEFAULT 1,
    session_id UUID,
    company_ticker VARCHAR(10),
    original_question TEXT NOT NULL,
    relevance_check JSONB,
    query_plan JSONB,
    synthesis_context TEXT,
    final_answer TEXT,
    confidence_score DECIMAL(3, 2),
    execution_time_ms INTEGER,
    verification_metadata JSONB,
    parent_trace_id UUID REFERENCES EXECUTION_TRACES (id),
    trace_level INTEGER NOT NULL DEFAULT 0,
    orchestrator_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES USERS (id)
);

CREATE TABLE SUB_QUERY_TRACES (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_trace_id UUID NOT NULL,
    sub_query_name VARCHAR(255),
    sub_query_question TEXT,
    sub_query_description TEXT,
    order_index INTEGER,
    execution_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (execution_trace_id) REFERENCES EXECUTION_TRACES (id) ON DELETE CASCADE
);

CREATE TABLE QUERY_ATTEMPTS (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sub_query_trace_id UUID NOT NULL,
    attempt_number INTEGER NOT NULL,
    query_text TEXT NOT NULL,
    query_type VARCHAR(10) NOT NULL DEFAULT 'sql',
    execution_time_ms INTEGER,
    row_count INTEGER,
    error_message TEXT,
    result_summary JSONB,
    source_tables TEXT[],
    source_indexes TEXT[],
    raw_results JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sub_query_trace_id) REFERENCES SUB_QUERY_TRACES (id) ON DELETE CASCADE,
    CONSTRAINT chk_query_type CHECK (query_type IN ('sql', 'vector'))
);

CREATE INDEX idx_execution_traces_user_id ON EXECUTION_TRACES (user_id);
CREATE INDEX idx_execution_traces_company ON EXECUTION_TRACES (company_ticker);
CREATE INDEX idx_execution_traces_created ON EXECUTION_TRACES (created_at DESC);
CREATE INDEX idx_execution_traces_session ON EXECUTION_TRACES (session_id);
CREATE INDEX idx_execution_traces_parent ON EXECUTION_TRACES (parent_trace_id);
CREATE INDEX idx_execution_traces_hierarchy ON EXECUTION_TRACES (parent_trace_id, trace_level);

CREATE INDEX idx_sub_query_traces_execution ON SUB_QUERY_TRACES (execution_trace_id);

CREATE INDEX idx_query_attempts_sub_query ON QUERY_ATTEMPTS (sub_query_trace_id);
CREATE INDEX idx_query_attempts_query_type ON QUERY_ATTEMPTS (query_type);
CREATE INDEX idx_query_attempts_created ON QUERY_ATTEMPTS (created_at DESC);
CREATE INDEX idx_query_attempts_sub_query_type ON QUERY_ATTEMPTS (sub_query_trace_id, query_type);

COMMENT ON TABLE EXECUTION_TRACES IS 'Stores complete execution traces for financial query processing (SQL + vector RAG)';
COMMENT ON TABLE SUB_QUERY_TRACES IS 'Stores individual sub-queries generated from complex questions';
COMMENT ON TABLE QUERY_ATTEMPTS IS 'Stores SQL and vector (pgvector) retrieval attempts per sub-query';

COMMENT ON COLUMN EXECUTION_TRACES.relevance_check IS 'JSON containing relevance check result and reasoning';
COMMENT ON COLUMN EXECUTION_TRACES.query_plan IS 'JSON containing the complete query breakdown plan';
COMMENT ON COLUMN EXECUTION_TRACES.verification_metadata IS 'JSON containing confidence scores, data sources, and potential issues';
COMMENT ON COLUMN EXECUTION_TRACES.parent_trace_id IS 'Optional parent trace for hierarchical / multi-orchestrator runs';
COMMENT ON COLUMN EXECUTION_TRACES.trace_level IS 'Depth in trace tree (0 = root)';
COMMENT ON COLUMN EXECUTION_TRACES.orchestrator_type IS 'Which orchestrator produced this trace (e.g. hybrid, sql, vector)';

COMMENT ON COLUMN QUERY_ATTEMPTS.query_text IS 'Executed SQL text or serialized vector retrieval spec (e.g. query + index identifiers)';
COMMENT ON COLUMN QUERY_ATTEMPTS.query_type IS 'sql or vector (pgvector / embedding retrieval)';
COMMENT ON COLUMN QUERY_ATTEMPTS.result_summary IS 'JSON summary of key results for quick access';
COMMENT ON COLUMN QUERY_ATTEMPTS.raw_results IS 'Full result payload for verification';
COMMENT ON COLUMN QUERY_ATTEMPTS.source_tables IS 'Relational table names touched (SQL)';
COMMENT ON COLUMN QUERY_ATTEMPTS.source_indexes IS 'pgvector index or logical chunk source identifiers (vector)';

-- Backward-compatible view for code expecting sql_query column name
CREATE OR REPLACE VIEW SQL_ATTEMPTS AS
SELECT
    id,
    sub_query_trace_id,
    attempt_number,
    query_text AS sql_query,
    execution_time_ms,
    row_count,
    error_message,
    result_summary,
    source_tables,
    raw_results,
    created_at
FROM QUERY_ATTEMPTS
WHERE query_type = 'sql';

CREATE OR REPLACE VIEW VECTOR_ATTEMPTS AS
SELECT
    id,
    sub_query_trace_id,
    attempt_number,
    query_text AS vector_query,
    execution_time_ms,
    row_count,
    error_message,
    result_summary,
    source_indexes,
    raw_results,
    created_at
FROM QUERY_ATTEMPTS
WHERE query_type = 'vector';

CREATE OR REPLACE VIEW QUERY_SUCCESS_RATES AS
SELECT
    query_type,
    COUNT(*) AS total_attempts,
    COUNT(CASE WHEN error_message IS NULL THEN 1 END) AS successful_attempts,
    ROUND(
        COUNT(CASE WHEN error_message IS NULL THEN 1 END)::NUMERIC
        / NULLIF(COUNT(*)::NUMERIC, 0) * 100,
        2
    ) AS success_rate_percent,
    AVG(execution_time_ms) AS avg_execution_time_ms
FROM QUERY_ATTEMPTS
GROUP BY query_type;
