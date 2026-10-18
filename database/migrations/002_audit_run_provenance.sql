BEGIN;

-- ============================================================
-- 002: provenance columns used by the audit runner.
-- Additive only. For a database that already
-- has 001_initial_schema.sql applied. Run it once: a second run
-- stops with an error and changes nothing.
-- ============================================================

-- The browser agent's own run id, so every audit can be traced
-- back to the exact agent run that produced its evidence.
ALTER TABLE public.audit_sessions
    ADD COLUMN IF NOT EXISTS agent_run_id VARCHAR(128);

-- Where page_url came from: the page's canonical link, or the URL
-- the audit was asked to visit (the agent reports no per-step URL).
ALTER TABLE public.audit_steps
    ADD COLUMN IF NOT EXISTS page_url_source VARCHAR(20);

ALTER TABLE public.audit_steps
    ADD CONSTRAINT audit_steps_page_url_source_values
    CHECK (
        page_url_source IS NULL
        OR page_url_source IN ('canonical', 'requested_url')
    );

-- True when the page text was cut to the size limit before analysis,
-- so the model saw only part of the page.
ALTER TABLE public.audit_steps
    ADD COLUMN IF NOT EXISTS dom_truncated BOOLEAN NOT NULL DEFAULT FALSE;

-- Whether the model analysis of this step finished.
ALTER TABLE public.audit_steps
    ADD COLUMN IF NOT EXISTS analysis_status VARCHAR(20) NOT NULL DEFAULT 'PENDING';

ALTER TABLE public.audit_steps
    ADD CONSTRAINT audit_steps_analysis_status_values
    CHECK (analysis_status IN ('PENDING', 'COMPLETED', 'FAILED', 'SKIPPED'));

-- How a finding was supported: quoted page text that was verified
-- against the captured DOM, or a screenshot-only observation.
ALTER TABLE public.dark_pattern_violations
    ADD COLUMN IF NOT EXISTS grounding VARCHAR(20);

ALTER TABLE public.dark_pattern_violations
    ADD CONSTRAINT violations_grounding_values
    CHECK (grounding IS NULL OR grounding IN ('DOM_VERIFIED', 'VISUAL_ONLY'));

COMMIT;
