CREATE TABLE IF NOT EXISTS PROCESS_RUN_STATE (
    id SERIAL PRIMARY KEY,
    ticker_id INTEGER NOT NULL REFERENCES TICKER(id) ON DELETE CASCADE,
    process_name VARCHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'idle',
    last_started_at TIMESTAMP,
    last_completed_at TIMESTAMP,
    last_failed_at TIMESTAMP,
    last_success_cursor JSONB,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    lock_token UUID,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_process_run_state UNIQUE (ticker_id, process_name),
    CONSTRAINT chk_process_name CHECK (
        process_name IN ('stocks', 'financials', 'press_releases')
    ),
    CONSTRAINT chk_process_status CHECK (
        status IN ('idle', 'running', 'success', 'failed')
    )
);

CREATE INDEX IF NOT EXISTS idx_process_run_state_ticker
    ON PROCESS_RUN_STATE (ticker_id);

CREATE INDEX IF NOT EXISTS idx_process_run_state_status
    ON PROCESS_RUN_STATE (status);

CREATE INDEX IF NOT EXISTS idx_process_run_state_process_name
    ON PROCESS_RUN_STATE (process_name);

CREATE OR REPLACE FUNCTION set_process_run_state_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_process_run_state_updated_at ON PROCESS_RUN_STATE;
CREATE TRIGGER trg_process_run_state_updated_at
    BEFORE UPDATE ON PROCESS_RUN_STATE
    FOR EACH ROW
    EXECUTE FUNCTION set_process_run_state_updated_at();
