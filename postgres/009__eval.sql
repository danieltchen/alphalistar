-- Database schema for evaluation framework

-- ============================================
-- Evaluation Runs Table
-- ============================================
CREATE TABLE IF NOT EXISTS evaluation_runs (
    id UUID PRIMARY KEY,
    run_name VARCHAR(200) NOT NULL,
    run_type VARCHAR(50) NOT NULL CHECK (run_type IN ('baseline', 'comparison', 'ab_test', 'iterative')),
    status VARCHAR(50) NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    question_count INTEGER NOT NULL CHECK (question_count > 0),
    iteration_count INTEGER NOT NULL CHECK (iteration_count > 0 AND iteration_count <= 10),
    judge_model VARCHAR(100) NOT NULL,
    control_model VARCHAR(100) NOT NULL,
    description TEXT,
    configuration JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    created_by_user_id INTEGER NOT NULL DEFAULT 1,
    
    -- Indexes
    CONSTRAINT evaluation_runs_name_unique UNIQUE (run_name, created_at)
);

CREATE INDEX IF NOT EXISTS idx_evaluation_runs_status ON evaluation_runs(status);
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_created_at ON evaluation_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_run_type ON evaluation_runs(run_type);

-- ============================================
-- Evaluation Pairs Table
-- ============================================
CREATE TABLE IF NOT EXISTS evaluation_pairs (
    id UUID PRIMARY KEY,
    evaluation_run_id UUID NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
    question_id VARCHAR(100) NOT NULL,
    question_text TEXT NOT NULL,
    company_ticker VARCHAR(10),
    
    -- Control group data
    control_responses JSONB NOT NULL, -- Array of ResponseInvocation objects
    control_primary_response TEXT NOT NULL,
    control_avg_latency_ms INTEGER NOT NULL,
    
    -- Experimental group data
    experimental_responses JSONB NOT NULL,
    experimental_primary_response TEXT NOT NULL,
    experimental_avg_latency_ms INTEGER NOT NULL,
    experimental_trace_id UUID NOT NULL,
    experimental_confidence_score NUMERIC(5,4) NOT NULL CHECK (experimental_confidence_score >= 0 AND experimental_confidence_score <= 1),
    
    -- Retrieved data context
    retrieved_data_summary TEXT NOT NULL,
    data_sources JSONB NOT NULL, -- Array of strings
    total_rows_retrieved INTEGER NOT NULL DEFAULT 0,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Indexes
    CONSTRAINT evaluation_pairs_unique_question UNIQUE (evaluation_run_id, question_id)
);

CREATE INDEX IF NOT EXISTS idx_evaluation_pairs_run_id ON evaluation_pairs(evaluation_run_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_pairs_question_id ON evaluation_pairs(question_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_pairs_trace_id ON evaluation_pairs(experimental_trace_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_pairs_created_at ON evaluation_pairs(created_at DESC);

-- ============================================
-- Judgement Scores Table
-- ============================================
CREATE TABLE IF NOT EXISTS judgement_scores (
    id UUID PRIMARY KEY,
    evaluation_pair_id UUID NOT NULL REFERENCES evaluation_pairs(id) ON DELETE CASCADE,
    judge_type VARCHAR(50) NOT NULL CHECK (judge_type IN ('factual_grounding', 'completeness', 'consistency', 'relevance')),
    judge_model VARCHAR(100) NOT NULL,
    
    -- Scores
    control_score NUMERIC(5,4) NOT NULL CHECK (control_score >= 0 AND control_score <= 1),
    experimental_score NUMERIC(5,4) NOT NULL CHECK (experimental_score >= 0 AND experimental_score <= 1),
    improvement_delta NUMERIC(6,4) NOT NULL, -- Can be negative
    
    -- Qualitative assessment
    reasoning TEXT NOT NULL,
    identified_issues_control JSONB DEFAULT '[]', -- Array of strings
    identified_issues_experimental JSONB DEFAULT '[]',
    confidence NUMERIC(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    
    -- Semantic entropy (for consistency judge)
    semantic_entropy_control NUMERIC(5,4),
    semantic_entropy_experimental NUMERIC(5,4),
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT judgement_scores_unique_pair_judge UNIQUE (evaluation_pair_id, judge_type)
);

CREATE INDEX IF NOT EXISTS idx_judgement_scores_pair_id ON judgement_scores(evaluation_pair_id);
CREATE INDEX IF NOT EXISTS idx_judgement_scores_judge_type ON judgement_scores(judge_type);
CREATE INDEX IF NOT EXISTS idx_judgement_scores_created_at ON judgement_scores(created_at DESC);

-- ============================================
-- Human Annotations Table (Optional - for future Tier 3)
-- ============================================
CREATE TABLE IF NOT EXISTS human_annotations (
    id UUID PRIMARY KEY,
    evaluation_pair_id UUID NOT NULL REFERENCES evaluation_pairs(id) ON DELETE CASCADE,
    annotator_user_id INTEGER NOT NULL,
    
    -- Preference
    preferred_response VARCHAR(20) CHECK (preferred_response IN ('control', 'experimental', 'tie', 'both_poor')),
    
    -- Ratings
    factual_accuracy_rating INTEGER CHECK (factual_accuracy_rating >= 1 AND factual_accuracy_rating <= 5),
    relevance_rating INTEGER CHECK (relevance_rating >= 1 AND relevance_rating <= 5),
    completeness_rating INTEGER CHECK (completeness_rating >= 1 AND completeness_rating <= 5),
    
    -- Comments
    comments TEXT,
    annotation_time_seconds INTEGER,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    CONSTRAINT human_annotations_unique UNIQUE (evaluation_pair_id, annotator_user_id)
);

CREATE INDEX IF NOT EXISTS idx_human_annotations_pair_id ON human_annotations(evaluation_pair_id);
CREATE INDEX IF NOT EXISTS idx_human_annotations_user_id ON human_annotations(annotator_user_id);

-- ============================================
-- Views for Easy Querying
-- ============================================

-- View: Evaluation Run Summary
CREATE OR REPLACE VIEW evaluation_run_summary AS
SELECT 
    er.id,
    er.run_name,
    er.run_type,
    er.status,
    er.question_count,
    er.iteration_count,
    er.created_at,
    er.completed_at,
    COUNT(DISTINCT ep.id) as completed_pairs,
    
    -- Factual grounding scores
    AVG(CASE WHEN js.judge_type = 'factual_grounding' THEN js.control_score END) as avg_control_factual_grounding,
    AVG(CASE WHEN js.judge_type = 'factual_grounding' THEN js.experimental_score END) as avg_experimental_factual_grounding,
    AVG(CASE WHEN js.judge_type = 'factual_grounding' THEN js.improvement_delta END) as avg_improvement_factual_grounding,
    
    -- Completeness scores
    AVG(CASE WHEN js.judge_type = 'completeness' THEN js.control_score END) as avg_control_completeness,
    AVG(CASE WHEN js.judge_type = 'completeness' THEN js.experimental_score END) as avg_experimental_completeness,
    AVG(CASE WHEN js.judge_type = 'completeness' THEN js.improvement_delta END) as avg_improvement_completeness,
    
    -- Consistency scores
    AVG(CASE WHEN js.judge_type = 'consistency' THEN js.control_score END) as avg_control_consistency,
    AVG(CASE WHEN js.judge_type = 'consistency' THEN js.experimental_score END) as avg_experimental_consistency,
    AVG(CASE WHEN js.judge_type = 'consistency' THEN js.improvement_delta END) as avg_improvement_consistency,
    
    -- Performance
    AVG(ep.control_avg_latency_ms)::INTEGER as avg_control_latency_ms,
    AVG(ep.experimental_avg_latency_ms)::INTEGER as avg_experimental_latency_ms,
    
    -- Data quality
    AVG(ep.experimental_confidence_score) as avg_experimental_confidence,
    SUM(ep.total_rows_retrieved) as total_rows_retrieved

FROM evaluation_runs er
LEFT JOIN evaluation_pairs ep ON er.id = ep.evaluation_run_id
LEFT JOIN judgement_scores js ON ep.id = js.evaluation_pair_id
GROUP BY er.id, er.run_name, er.run_type, er.status, er.question_count, 
         er.iteration_count, er.created_at, er.completed_at;

-- View: Detailed Pair Results
CREATE OR REPLACE VIEW evaluation_pair_details AS
SELECT 
    ep.id,
    ep.evaluation_run_id,
    er.run_name,
    ep.question_id,
    ep.question_text,
    ep.company_ticker,
    ep.experimental_trace_id,
    ep.experimental_confidence_score,
    ep.total_rows_retrieved,
    
    -- Judgement scores
    js_fg.control_score as fg_control_score,
    js_fg.experimental_score as fg_experimental_score,
    js_fg.improvement_delta as fg_improvement,
    
    js_comp.control_score as completeness_control_score,
    js_comp.experimental_score as completeness_experimental_score,
    js_comp.improvement_delta as completeness_improvement,
    
    js_cons.control_score as consistency_control_score,
    js_cons.experimental_score as consistency_experimental_score,
    js_cons.improvement_delta as consistency_improvement,
    js_cons.semantic_entropy_control,
    js_cons.semantic_entropy_experimental,
    
    ep.created_at

FROM evaluation_pairs ep
JOIN evaluation_runs er ON ep.evaluation_run_id = er.id
LEFT JOIN judgement_scores js_fg ON ep.id = js_fg.evaluation_pair_id AND js_fg.judge_type = 'factual_grounding'
LEFT JOIN judgement_scores js_comp ON ep.id = js_comp.evaluation_pair_id AND js_comp.judge_type = 'completeness'
LEFT JOIN judgement_scores js_cons ON ep.id = js_cons.evaluation_pair_id AND js_cons.judge_type = 'consistency';

-- ============================================
-- Utility Functions
-- ============================================

-- Function to calculate hallucination rate for a run
CREATE OR REPLACE FUNCTION calculate_hallucination_rate(
    p_evaluation_run_id UUID,
    p_group VARCHAR(20), -- 'control' or 'experimental'
    p_threshold NUMERIC DEFAULT 0.6
) RETURNS NUMERIC AS $$
DECLARE
    v_total_pairs INTEGER;
    v_hallucinated_pairs INTEGER;
BEGIN
    -- Count total pairs
    SELECT COUNT(*) INTO v_total_pairs
    FROM evaluation_pairs
    WHERE evaluation_run_id = p_evaluation_run_id;
    
    IF v_total_pairs = 0 THEN
        RETURN 0.0;
    END IF;
    
    -- Count pairs with low factual grounding (hallucinations)
    IF p_group = 'control' THEN
        SELECT COUNT(*) INTO v_hallucinated_pairs
        FROM evaluation_pairs ep
        JOIN judgement_scores js ON ep.id = js.evaluation_pair_id
        WHERE ep.evaluation_run_id = p_evaluation_run_id
          AND js.judge_type = 'factual_grounding'
          AND js.control_score < p_threshold;
    ELSE
        SELECT COUNT(*) INTO v_hallucinated_pairs
        FROM evaluation_pairs ep
        JOIN judgement_scores js ON ep.id = js.evaluation_pair_id
        WHERE ep.evaluation_run_id = p_evaluation_run_id
          AND js.judge_type = 'factual_grounding'
          AND js.experimental_score < p_threshold;
    END IF;
    
    RETURN ROUND(v_hallucinated_pairs::NUMERIC / v_total_pairs::NUMERIC, 4);
END;
$$ LANGUAGE plpgsql;

-- Comments for documentation
COMMENT ON TABLE evaluation_runs IS 'Tracks evaluation runs/batches';
COMMENT ON TABLE evaluation_pairs IS 'Stores control vs experimental response pairs';
COMMENT ON TABLE judgement_scores IS 'LLM judge assessments of response quality';
COMMENT ON TABLE human_annotations IS 'Human evaluator annotations (optional)';
