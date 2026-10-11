BEGIN;

-- ============================================================
-- 1. ENUM TYPES
-- ============================================================

CREATE TYPE public.audit_status AS ENUM (
    'QUEUED',
    'RUNNING',
    'COMPLETED',
    'FAILED',
    'CANCELLED'
);

CREATE TYPE public.audit_step_status AS ENUM (
    'PENDING',
    'RUNNING',
    'COMPLETED',
    'FAILED',
    'SKIPPED'
);

CREATE TYPE public.ccpa_dark_pattern_category AS ENUM (
    'FALSE_URGENCY',
    'BASKET_SNEAKING',
    'CONFIRM_SHAMING',
    'FORCED_ACTION',
    'SUBSCRIPTION_TRAP',
    'INTERFACE_INTERFERENCE',
    'BAIT_AND_SWITCH',
    'DRIP_PRICING',
    'DISGUISED_ADVERTISEMENT',
    'NAGGING',
    'TRICK_QUESTION',
    'SAAS_BILLING',
    'ROGUE_MALWARE'
);

CREATE TYPE public.finding_review_status AS ENUM (
    'PENDING_REVIEW',
    'CONFIRMED',
    'REJECTED',
    'INCONCLUSIVE'
);

CREATE TYPE public.audit_trigger_source AS ENUM (
    'DASHBOARD',
    'API',
    'SCHEDULED'
);

-- ============================================================
-- 2. PLATFORMS
-- One record per registered website.
-- ============================================================

CREATE TABLE public.platforms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    domain VARCHAR(253) NOT NULL UNIQUE,
    name VARCHAR(150) NOT NULL,

    category VARCHAR(50) NOT NULL CHECK (
        category IN (
            'E_COMMERCE',
            'QUICK_COMMERCE',
            'TRAVEL',
            'SUBSCRIPTION',
            'OTHER'
        )
    ),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT platforms_domain_not_blank
        CHECK (length(trim(domain)) > 0),

    CONSTRAINT platforms_name_not_blank
        CHECK (length(trim(name)) > 0)
);

-- ============================================================
-- 3. AUDIT SESSIONS
-- One record per requested audit run.
-- ============================================================

CREATE TABLE public.audit_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    platform_id UUID NOT NULL
        REFERENCES public.platforms(id)
        ON DELETE RESTRICT,

    status public.audit_status NOT NULL DEFAULT 'QUEUED',

    trigger_source public.audit_trigger_source NOT NULL
        DEFAULT 'DASHBOARD',

    requested_url TEXT NOT NULL,

    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    error_code VARCHAR(100),
    error_message TEXT,

    -- Execution and model provenance.
    agent_provider VARCHAR(50),
    agent_version VARCHAR(100),
    vision_model VARCHAR(150),
    taxonomy_version VARCHAR(50) NOT NULL DEFAULT 'CCPA-2023',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT audit_sessions_url_not_blank
        CHECK (length(trim(requested_url)) > 0),

    CONSTRAINT audit_sessions_time_order
        CHECK (
            completed_at IS NULL
            OR (
                started_at IS NOT NULL
                AND completed_at >= started_at
            )
        ),

    CONSTRAINT audit_sessions_error_code_not_blank
        CHECK (error_code IS NULL OR length(trim(error_code)) > 0)
);

-- ============================================================
-- 4. AUDIT STEPS
-- A sequential, evidence-bearing record for each browser state.
-- ============================================================

CREATE TABLE public.audit_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    session_id UUID NOT NULL
        REFERENCES public.audit_sessions(id)
        ON DELETE CASCADE,

    step_number INTEGER NOT NULL CHECK (step_number > 0),

    status public.audit_step_status NOT NULL DEFAULT 'PENDING',

    action_description TEXT,
    page_title TEXT,
    page_url TEXT NOT NULL,

    -- Store private bucket object paths, never public URLs.
    screenshot_object_path TEXT,
    dom_object_path TEXT,

    screenshot_sha256 CHAR(64),
    dom_sha256 CHAR(64),

    captured_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT audit_steps_unique_number
        UNIQUE (session_id, step_number),

    CONSTRAINT audit_steps_url_not_blank
        CHECK (length(trim(page_url)) > 0),

    CONSTRAINT audit_steps_screenshot_hash_format
        CHECK (
            screenshot_sha256 IS NULL
            OR screenshot_sha256 ~ '^[0-9a-f]{64}$'
        ),

    CONSTRAINT audit_steps_dom_hash_format
        CHECK (
            dom_sha256 IS NULL
            OR dom_sha256 ~ '^[0-9a-f]{64}$'
        )
);

-- ============================================================
-- 5. DARK PATTERN FINDINGS
-- Findings are machine-generated hypotheses until reviewed.
-- ============================================================

CREATE TABLE public.dark_pattern_violations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    session_id UUID NOT NULL
        REFERENCES public.audit_sessions(id)
        ON DELETE CASCADE,

    step_id UUID NOT NULL
        REFERENCES public.audit_steps(id)
        ON DELETE CASCADE,

    category public.ccpa_dark_pattern_category NOT NULL,

    confidence_score NUMERIC(4, 3) NOT NULL CHECK (
        confidence_score >= 0.000
        AND confidence_score <= 1.000
    ),

    explanation TEXT NOT NULL,
    observed_behavior TEXT NOT NULL,
    suggested_fix TEXT,

    -- CSS selector or human-readable visual location.
    offending_element_selector TEXT,

    -- Ground the finding in the relevant legal provision.
    legal_reference TEXT NOT NULL,

    review_status public.finding_review_status NOT NULL
        DEFAULT 'PENDING_REVIEW',

    reviewed_at TIMESTAMPTZ,
    reviewer_reference TEXT,
    review_notes TEXT,

    -- Store model provenance and supporting evidence references.
    model_provider VARCHAR(50),
    model_version VARCHAR(150),
    evidence JSONB NOT NULL DEFAULT '[]'::JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT violations_explanation_not_blank
        CHECK (length(trim(explanation)) > 0),

    CONSTRAINT violations_observed_behavior_not_blank
        CHECK (length(trim(observed_behavior)) > 0),

    CONSTRAINT violations_legal_reference_not_blank
        CHECK (length(trim(legal_reference)) > 0),

    CONSTRAINT violations_evidence_is_array
        CHECK (jsonb_typeof(evidence) = 'array'),

    CONSTRAINT violations_review_timestamp
        CHECK (
            review_status = 'PENDING_REVIEW'
            OR reviewed_at IS NOT NULL
        )
);

-- ============================================================
-- 6. INDEXES
-- ============================================================

CREATE INDEX idx_audit_sessions_platform_created
    ON public.audit_sessions (platform_id, created_at DESC);

CREATE INDEX idx_audit_sessions_status_created
    ON public.audit_sessions (status, created_at DESC);

CREATE INDEX idx_audit_steps_session_number
    ON public.audit_steps (session_id, step_number);

CREATE INDEX idx_audit_steps_captured_at
    ON public.audit_steps (captured_at DESC)
    WHERE captured_at IS NOT NULL;

CREATE INDEX idx_violations_session
    ON public.dark_pattern_violations (session_id);

CREATE INDEX idx_violations_step
    ON public.dark_pattern_violations (step_id);

CREATE INDEX idx_violations_category_created
    ON public.dark_pattern_violations (category, created_at DESC);

CREATE INDEX idx_violations_review_status
    ON public.dark_pattern_violations (review_status, created_at DESC);

CREATE INDEX idx_violations_evidence
    ON public.dark_pattern_violations USING GIN (evidence);

-- ============================================================
-- 7. AUTOMATIC UPDATED_AT MAINTENANCE
-- ============================================================

CREATE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_platforms_updated_at
BEFORE UPDATE ON public.platforms
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_audit_sessions_updated_at
BEFORE UPDATE ON public.audit_sessions
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_dark_pattern_violations_updated_at
BEFORE UPDATE ON public.dark_pattern_violations
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at();

-- ============================================================
-- 8. ROW-LEVEL SECURITY
-- The browser must not receive direct access to audit records.
-- Backend access will be configured separately.
-- ============================================================

ALTER TABLE public.platforms ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dark_pattern_violations ENABLE ROW LEVEL SECURITY;

-- Intentionally create no permissive client-facing policies here.
-- Authenticated frontend access will be introduced only with an
-- explicit authorization model in a later implementation phase.

COMMIT;
