"""Schemas for model output, evidence grounding, and validated findings.

Flow:
  1. The model returns a StepAnalysisResponse (untrusted hypotheses).
  2. ground_findings() checks every finding against the DOM text the model
     was actually shown, drops evidence it cannot verify, and rejects
     findings left without evidence.
  3. Survivors become ValidatedFinding records. They always start as
     PENDING_REVIEW. Only a human reviewer may change that, later.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.taxonomy import (
    TAXONOMY_VERSION,
    DarkPatternCategory,
    legal_reference,
)

# Findings supported only by what the model says it saw in the screenshot
# cannot be machine-verified, so their confidence is capped. Owner-tunable.
VISUAL_ONLY_CONFIDENCE_CAP = 0.6


class ReviewStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class EvidenceKind(StrEnum):
    DOM_TEXT = "DOM_TEXT"
    VISUAL = "VISUAL"


class GroundingLevel(StrEnum):
    DOM_VERIFIED = "DOM_VERIFIED"
    VISUAL_ONLY = "VISUAL_ONLY"


# ---------------------------------------------------------------------------
# Model-facing schemas (sent to Gemini as the response schema)
# ---------------------------------------------------------------------------


class EvidenceItem(BaseModel):
    """One piece of supporting evidence.

    DOM_TEXT: text copied exactly from the supplied page text.
    VISUAL: a plain description of something visible in the screenshot.
    """

    kind: EvidenceKind
    observation: str


class ModelFinding(BaseModel):
    category: DarkPatternCategory
    confidence_score: float = Field(ge=0.0, le=1.0)
    explanation: str
    observed_behavior: str
    suggested_fix: str | None = None
    offending_element_selector: str | None = None
    evidence: list[EvidenceItem]


class StepAnalysisResponse(BaseModel):
    findings: list[ModelFinding] = []


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


class StepContext(BaseModel):
    """Everything the analyzer needs about one captured browser state."""

    model_config = ConfigDict(frozen=True)

    step_number: int = Field(gt=0)
    page_url: str
    page_title: str | None = None
    action_description: str | None = None
    screenshot: bytes
    screenshot_mime_type: str = "image/png"
    dom_text: str


# ---------------------------------------------------------------------------
# Validated outputs
# ---------------------------------------------------------------------------


class VerifiedEvidence(EvidenceItem):
    verified: bool


class ValidatedFinding(BaseModel):
    """A grounded finding, ready to be stored as PENDING_REVIEW."""

    model_config = ConfigDict(protected_namespaces=())

    step_number: int = Field(gt=0)
    category: DarkPatternCategory
    confidence_score: float = Field(ge=0.0, le=1.0)
    explanation: str
    observed_behavior: str
    suggested_fix: str | None = None
    offending_element_selector: str | None = None
    legal_reference: str
    evidence: list[VerifiedEvidence]
    grounding: GroundingLevel
    review_status: Literal[ReviewStatus.PENDING_REVIEW] = ReviewStatus.PENDING_REVIEW
    model_provider: str
    model_version: str
    taxonomy_version: str = TAXONOMY_VERSION


class RejectedFinding(BaseModel):
    finding: ModelFinding
    reason: str


class GroundingReport(BaseModel):
    accepted: list[ValidatedFinding] = []
    rejected: list[RejectedFinding] = []
    # True when the page text was cut to fit the size limit, so the model
    # saw only part of the page. Reviewers should know this.
    dom_truncated: bool = False


# ---------------------------------------------------------------------------
# Grounding
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def ground_findings(
    response: StepAnalysisResponse,
    *,
    dom_text: str,
    step_number: int,
    model_provider: str,
    model_version: str,
    visual_only_cap: float = VISUAL_ONLY_CONFIDENCE_CAP,
) -> GroundingReport:
    """Verify model findings against the DOM text the model was shown.

    Rules:
      - A DOM_TEXT quote must appear in dom_text (whitespace and case
        insensitive). Quotes that do not are discarded.
      - VISUAL evidence is kept but cannot be verified.
      - A finding with no surviving evidence is rejected.
      - A finding with only VISUAL evidence is capped at visual_only_cap.
      - Blank explanation or observed_behavior rejects the finding.
    """
    dom_normalized = _normalize(dom_text)
    report = GroundingReport()

    for finding in response.findings:
        if not finding.explanation.strip() or not finding.observed_behavior.strip():
            report.rejected.append(
                RejectedFinding(
                    finding=finding,
                    reason="explanation or observed_behavior is blank",
                )
            )
            continue

        kept: list[VerifiedEvidence] = []
        for item in finding.evidence:
            observation = item.observation.strip()
            if not observation:
                continue
            if item.kind == EvidenceKind.DOM_TEXT:
                if _normalize(observation) in dom_normalized:
                    kept.append(
                        VerifiedEvidence(
                            kind=item.kind, observation=observation, verified=True
                        )
                    )
            else:
                kept.append(
                    VerifiedEvidence(
                        kind=item.kind, observation=observation, verified=False
                    )
                )

        if not kept:
            report.rejected.append(
                RejectedFinding(
                    finding=finding,
                    reason="no evidence survived verification",
                )
            )
            continue

        if any(item.verified for item in kept):
            grounding = GroundingLevel.DOM_VERIFIED
            confidence = finding.confidence_score
        else:
            grounding = GroundingLevel.VISUAL_ONLY
            confidence = min(finding.confidence_score, visual_only_cap)

        report.accepted.append(
            ValidatedFinding(
                step_number=step_number,
                category=finding.category,
                confidence_score=confidence,
                explanation=finding.explanation.strip(),
                observed_behavior=finding.observed_behavior.strip(),
                suggested_fix=finding.suggested_fix,
                offending_element_selector=finding.offending_element_selector,
                legal_reference=legal_reference(finding.category),
                evidence=kept,
                grounding=grounding,
                model_provider=model_provider,
                model_version=model_version,
            )
        )

    return report
