"""Request and response models for the HTTP API.

Responses expose what a reviewer needs and nothing internal: no object-store
paths, no credentials, no raw model output.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    trigger_source: Literal["DASHBOARD", "API"] = "API"


class AuditCreated(BaseModel):
    session_id: UUID
    status: Literal["QUEUED"] = "QUEUED"


class AuditSummary(BaseModel):
    id: UUID
    status: str
    domain: str
    requested_url: str
    trigger_source: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    agent_provider: str | None = None
    agent_run_id: str | None = None
    vision_model: str | None = None
    taxonomy_version: str
    step_count: int
    finding_count: int


class AuditStep(BaseModel):
    step_number: int
    status: str
    analysis_status: str
    action_description: str | None = None
    page_title: str | None = None
    page_url: str
    page_url_source: str | None = None
    captured_at: datetime | None = None
    screenshot_sha256: str | None = None
    dom_sha256: str | None = None
    dom_truncated: bool
    has_evidence: bool


class AuditFinding(BaseModel):
    id: UUID
    step_number: int
    category: str
    confidence_score: float
    grounding: str | None = None
    explanation: str
    observed_behavior: str
    suggested_fix: str | None = None
    offending_element_selector: str | None = None
    legal_reference: str
    review_status: str
    evidence: list[dict[str, Any]]
    model_provider: str | None = None
    model_version: str | None = None
    created_at: datetime


def step_from_row(row: dict[str, Any]) -> AuditStep:
    return AuditStep(
        step_number=row["step_number"],
        status=row["status"],
        analysis_status=row["analysis_status"],
        action_description=row["action_description"],
        page_title=row["page_title"],
        page_url=row["page_url"],
        page_url_source=row["page_url_source"],
        captured_at=row["captured_at"],
        screenshot_sha256=row["screenshot_sha256"],
        dom_sha256=row["dom_sha256"],
        dom_truncated=row["dom_truncated"],
        has_evidence=bool(row["screenshot_object_path"] and row["dom_object_path"]),
    )


def finding_from_row(row: dict[str, Any]) -> AuditFinding:
    return AuditFinding(
        id=row["id"],
        step_number=row["step_number"],
        category=row["category"],
        confidence_score=float(row["confidence_score"]),
        grounding=row["grounding"],
        explanation=row["explanation"],
        observed_behavior=row["observed_behavior"],
        suggested_fix=row["suggested_fix"],
        offending_element_selector=row["offending_element_selector"],
        legal_reference=row["legal_reference"],
        review_status=row["review_status"],
        evidence=row["evidence"],
        model_provider=row["model_provider"],
        model_version=row["model_version"],
        created_at=row["created_at"],
    )
