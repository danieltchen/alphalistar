-- Migration script to add knowledge graph tracking columns
-- Add columns to track knowledge graph processing status

-- Add graph processing status to FILING table
ALTER TABLE FILING 
ADD COLUMN IF NOT EXISTS graph_processed BOOLEAN DEFAULT FALSE;

ALTER TABLE FILING 
ADD COLUMN IF NOT EXISTS graph_processed_date TIMESTAMP DEFAULT NULL;

-- Add index for faster queries on graph processing status
CREATE INDEX IF NOT EXISTS idx_filing_graph_processed 
ON FILING(graph_processed, graph_processed_date);

-- Add comments to document the new columns
COMMENT ON COLUMN FILING.graph_processed IS 'Indicates whether knowledge graph extraction has been completed for this filing';
COMMENT ON COLUMN FILING.graph_processed_date IS 'Timestamp when knowledge graph processing was completed';

-- Mark existing completed filings as needing graph processing
UPDATE FILING 
SET graph_processed = FALSE
WHERE completed = TRUE 
AND graph_processed IS NULL;

-- Create a view to easily find filings that need KG processing
CREATE OR REPLACE VIEW filings_needing_kg_processing AS
SELECT 
    f.id,
    f.symbol,
    f.accessionNo,
    f.type,
    f.filingDate,
    f.completed,
    f.graph_processed,
    COUNT(s.id) as chunk_count
FROM FILING f
LEFT JOIN STATEMENTS s ON f.id = s.filingId
WHERE f.completed = TRUE 
  AND (f.graph_processed IS NULL OR f.graph_processed = FALSE)
GROUP BY f.id, f.symbol, f.accessionNo, f.type, f.filingDate, f.completed, f.graph_processed
HAVING COUNT(s.id) > 0
ORDER BY f.filingDate DESC;

-- Add comment to the view
COMMENT ON VIEW filings_needing_kg_processing IS 'View showing filings that have been processed for text but not yet for knowledge graph extraction';
