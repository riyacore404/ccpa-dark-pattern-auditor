"""Turn a submitted URL into a queued audit session.

The URL is validated here, before anything is stored or queued. Invalid or
non-public targets never reach the database or the browser agent.
"""

from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

from app.core.security import Resolver, system_resolver, validate_target_url
from app.db.repository import AuditRepository


class AuditRequestError(ValueError):
    """The audit cannot be requested (as opposed to an invalid URL)."""


@dataclass(frozen=True)
class AuditRequest:
    session_id: UUID
    platform_id: UUID
    domain: str
    requested_url: str


def platform_domain(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def request_audit(
    repository: AuditRepository,
    raw_url: object,
    trigger_source: str = "API",
    resolver: Resolver = system_resolver,
) -> AuditRequest:
    """Validate the URL, register its platform and create a QUEUED session.

    Raises TargetValidationError for an unacceptable URL and AuditRequestError
    when the platform has been deactivated.
    """
    url = validate_target_url(raw_url, resolver=resolver)
    domain = platform_domain(url)
    platform = repository.get_or_create_platform(domain)
    if not platform.is_active:
        raise AuditRequestError("this platform is not active")
    session_id = repository.create_session(platform.id, url, trigger_source)
    return AuditRequest(
        session_id=session_id,
        platform_id=platform.id,
        domain=domain,
        requested_url=url,
    )
