import pytest

from app.core.security import TargetValidationError
from app.db.repository import PlatformRecord
from app.services.audit_intake import AuditRequestError, platform_domain, request_audit

PUBLIC = lambda host, port: ["93.184.216.34"]  # noqa: E731


class FakeRepo:
    def __init__(self, active=True):
        self.active = active
        self.platforms = []
        self.sessions = []

    def get_or_create_platform(self, domain, name=None, category="OTHER"):
        self.platforms.append(domain)
        return PlatformRecord(id="p-1", domain=domain, is_active=self.active)

    def create_session(self, platform_id, url, trigger_source="API"):
        self.sessions.append((platform_id, url, trigger_source))
        return "s-1"


def test_valid_url_creates_a_queued_session():
    repo = FakeRepo()
    result = request_audit(repo, "https://Example.com/shop?x=1", "DASHBOARD", resolver=PUBLIC)
    assert result.session_id == "s-1"
    assert result.domain == "example.com"
    assert result.requested_url == "https://example.com/shop?x=1"
    assert repo.sessions == [("p-1", "https://example.com/shop?x=1", "DASHBOARD")]


def test_www_prefix_is_grouped_with_the_bare_domain():
    assert platform_domain("https://www.example.com/a") == "example.com"
    assert platform_domain("https://shop.example.com/a") == "shop.example.com"


@pytest.mark.parametrize(
    "bad",
    [
        "http://localhost/",
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data",
        "ftp://example.com/",
        "https://user:pw@example.com/",
        "https://example.com:8443/",
        "",
        None,
    ],
)
def test_unacceptable_urls_never_reach_the_database(bad):
    repo = FakeRepo()
    with pytest.raises(TargetValidationError):
        request_audit(repo, bad, resolver=PUBLIC)
    assert repo.platforms == [] and repo.sessions == []


def test_private_resolution_is_rejected_before_storing_anything():
    repo = FakeRepo()
    with pytest.raises(TargetValidationError):
        request_audit(repo, "https://sneaky.example.com/", resolver=lambda h, p: ["10.0.0.5"])
    assert repo.platforms == [] and repo.sessions == []


def test_inactive_platform_is_refused_and_no_session_is_created():
    repo = FakeRepo(active=False)
    with pytest.raises(AuditRequestError):
        request_audit(repo, "https://example.com/", resolver=PUBLIC)
    assert repo.sessions == []
