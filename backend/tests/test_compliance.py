import pytest
from pydantic import ValidationError

from app.schemas.compliance import (
    VISUAL_ONLY_CONFIDENCE_CAP,
    EvidenceItem,
    EvidenceKind,
    GroundingLevel,
    ModelFinding,
    ReviewStatus,
    StepAnalysisResponse,
    ValidatedFinding,
    ground_findings,
)
from app.schemas.taxonomy import DarkPatternCategory

DOM = "Hurry!   Only 2 left in stock. Offer ends in 10 minutes."


def make_finding(evidence, confidence=0.9, **overrides):
    data = dict(
        category=DarkPatternCategory.FALSE_URGENCY,
        confidence_score=confidence,
        explanation="A scarcity message is shown.",
        observed_behavior="Text claims only 2 items remain.",
        evidence=evidence,
    )
    data.update(overrides)
    return ModelFinding(**data)


def ground(findings):
    return ground_findings(
        StepAnalysisResponse(findings=findings),
        dom_text=DOM,
        step_number=3,
        model_provider="gemini",
        model_version="test-model",
    )


def dom(text):
    return EvidenceItem(kind=EvidenceKind.DOM_TEXT, observation=text)


def visual(text):
    return EvidenceItem(kind=EvidenceKind.VISUAL, observation=text)


def test_verified_dom_quote_is_accepted():
    report = ground([make_finding([dom("Only 2 left in stock")])])
    assert len(report.accepted) == 1
    finding = report.accepted[0]
    assert finding.grounding == GroundingLevel.DOM_VERIFIED
    assert finding.evidence[0].verified is True
    assert finding.confidence_score == 0.9
    assert finding.step_number == 3


def test_match_ignores_case_and_whitespace():
    report = ground([make_finding([dom("hurry! only 2   LEFT")])])
    assert len(report.accepted) == 1


def test_fabricated_quote_is_dropped_and_finding_rejected():
    report = ground([make_finding([dom("Only 1 left, buy now")])])
    assert report.accepted == []
    assert len(report.rejected) == 1
    assert report.rejected[0].reason == "no evidence survived verification"


def test_fabricated_quote_dropped_but_real_quote_kept():
    report = ground(
        [make_finding([dom("Only 1 left, buy now"), dom("Offer ends in 10 minutes")])]
    )
    assert len(report.accepted) == 1
    assert len(report.accepted[0].evidence) == 1
    assert report.accepted[0].evidence[0].observation == "Offer ends in 10 minutes"


def test_visual_only_finding_is_capped():
    report = ground([make_finding([visual("A red countdown timer is shown")], 0.95)])
    finding = report.accepted[0]
    assert finding.grounding == GroundingLevel.VISUAL_ONLY
    assert finding.confidence_score == VISUAL_ONLY_CONFIDENCE_CAP
    assert finding.evidence[0].verified is False


def test_visual_only_finding_below_cap_is_unchanged():
    report = ground([make_finding([visual("A countdown timer")], 0.3)])
    assert report.accepted[0].confidence_score == 0.3


def test_dom_verified_wins_over_visual_when_mixed():
    report = ground(
        [make_finding([dom("Only 2 left in stock"), visual("Red banner")], 0.95)]
    )
    finding = report.accepted[0]
    assert finding.grounding == GroundingLevel.DOM_VERIFIED
    assert finding.confidence_score == 0.95


def test_finding_without_evidence_is_rejected():
    report = ground([make_finding([])])
    assert report.accepted == []
    assert len(report.rejected) == 1


def test_blank_evidence_text_is_ignored():
    report = ground([make_finding([dom("   ")])])
    assert report.accepted == []


def test_blank_explanation_is_rejected():
    report = ground([make_finding([dom("Only 2 left")], explanation="   ")])
    assert report.accepted == []
    assert "blank" in report.rejected[0].reason


def test_legal_reference_is_filled_from_taxonomy_not_model():
    report = ground([make_finding([dom("Only 2 left")])])
    assert "Annexure 1" in report.accepted[0].legal_reference
    assert "False Urgency" in report.accepted[0].legal_reference


def test_accepted_findings_are_pending_review():
    report = ground([make_finding([dom("Only 2 left")])])
    assert report.accepted[0].review_status == ReviewStatus.PENDING_REVIEW


def test_validated_finding_cannot_be_created_as_confirmed():
    with pytest.raises(ValidationError):
        ValidatedFinding(
            step_number=1,
            category=DarkPatternCategory.NAGGING,
            confidence_score=0.5,
            explanation="x",
            observed_behavior="y",
            legal_reference="z",
            evidence=[],
            grounding=GroundingLevel.VISUAL_ONLY,
            review_status=ReviewStatus.CONFIRMED,
            model_provider="gemini",
            model_version="m",
        )


def test_confidence_out_of_range_is_rejected_at_parse():
    with pytest.raises(ValidationError):
        ModelFinding(
            category=DarkPatternCategory.NAGGING,
            confidence_score=1.5,
            explanation="x",
            observed_behavior="y",
            evidence=[],
        )


def test_unknown_category_is_rejected_at_parse():
    with pytest.raises(ValidationError):
        StepAnalysisResponse.model_validate(
            {
                "findings": [
                    {
                        "category": "LACK_OF_TRANSPARENCY",
                        "confidence_score": 0.5,
                        "explanation": "x",
                        "observed_behavior": "y",
                        "evidence": [],
                    }
                ]
            }
        )


def test_empty_response_yields_empty_report():
    report = ground([])
    assert report.accepted == [] and report.rejected == []
    assert report.dom_truncated is False
