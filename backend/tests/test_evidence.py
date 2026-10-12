import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import Settings
from app.schemas.compliance import GroundingLevel
from app.services.evidence import (
    EvidenceConfigurationError,
    EvidenceError,
    EvidenceService,
    EvidenceStorageError,
    SupabaseEvidenceStore,
    evidence_object_path,
    extract_page_metadata,
    html_to_text,
    sha256_hex,
    to_step_context,
)
from app.services.gemini import GeminiAnalyzer
from app.services.tinyfish import RunStep, TinyFishClient

RUN_ID = "run-123"
SESSION = "3f2b8c1e-aaaa-bbbb-cccc-1234567890ab"
JPEG = b"\xff\xd8\xff\xe0" + b"jpegdata" * 20
PAGE = b"""<!doctype html>
<html><head>
  <title>  Cart | Example   Shop </title>
  <link rel="canonical" href="https://www.example.com/cart">
  <style>.x { color: red }</style>
  <script>var secret = "do not show";</script>
</head><body>
  <h1>Your cart</h1>
  <p>Hurry! Only 2 left in stock.</p>
  <div hidden>Hidden by attribute</div>
  <div style="display: none">Hidden by style</div>
  <span style="visibility:hidden">Hidden by visibility</span>
  <noscript>Enable JavaScript</noscript>
  <img src="a.png" alt="Free gift added">
  <input type="text" placeholder="Enter pincode">
  <input type="submit" value="Place order">
  <button aria-label="Close offer" title="Dismiss">x</button>
  <ul><li>Item A &amp; B</li><li>Fee: &#8377;49</li></ul>
</body></html>"""


# --- html_to_text ---------------------------------------------------------


def test_visible_text_is_extracted():
    text = html_to_text(PAGE)
    assert "Your cart" in text
    assert "Hurry! Only 2 left in stock." in text
    assert "Item A & B" in text
    assert "Fee: ₹49" in text


def test_scripts_styles_noscript_and_title_are_not_page_text():
    text = html_to_text(PAGE)
    for hidden in ("do not show", "color: red", "Enable JavaScript", "Cart | Example"):
        assert hidden not in text


def test_hidden_elements_are_dropped():
    text = html_to_text(PAGE)
    assert "Hidden by attribute" not in text
    assert "Hidden by style" not in text
    assert "Hidden by visibility" not in text


def test_user_facing_attributes_are_included():
    text = html_to_text(PAGE)
    for shown in ("Free gift added", "Enter pincode", "Place order", "Close offer", "Dismiss"):
        assert shown in text


def test_text_is_split_into_clean_lines():
    lines = html_to_text(PAGE).splitlines()
    assert all(line == " ".join(line.split()) and line for line in lines)
    assert "Your cart" in lines


def test_nested_hidden_content_stays_hidden_until_the_parent_closes():
    html = "<div><div hidden><p>inside</p><span>deep</span></div><p>after</p></div>"
    text = html_to_text(html)
    assert "inside" not in text and "deep" not in text
    assert "after" in text


def test_malformed_and_unclosed_html_does_not_crash_or_hide_the_rest():
    text = html_to_text("<div><p>one<p>two<div hidden>gone</div><b>three")
    assert "one" in text and "two" in text and "three" in text and "gone" not in text


def test_empty_and_binary_input():
    assert html_to_text(b"") == ""
    assert isinstance(html_to_text(b"\xff\xfe\x00<p>x</p>"), str)


def test_extracted_quote_is_found_by_phase_two_grounding():
    from app.schemas.compliance import ground_findings, StepAnalysisResponse, ModelFinding, EvidenceItem, EvidenceKind
    from app.schemas.taxonomy import DarkPatternCategory

    finding = ModelFinding(
        category=DarkPatternCategory.FALSE_URGENCY,
        confidence_score=0.8,
        explanation="e",
        observed_behavior="o",
        evidence=[EvidenceItem(kind=EvidenceKind.DOM_TEXT, observation="Hurry! Only 2 left in stock.")],
    )
    report = ground_findings(
        StepAnalysisResponse(findings=[finding]),
        dom_text=html_to_text(PAGE),
        step_number=1,
        model_provider="gemini",
        model_version="m",
    )
    assert len(report.accepted) == 1


# --- metadata -------------------------------------------------------------


def test_title_is_cleaned_and_same_site_canonical_is_used():
    title, url, source = extract_page_metadata(PAGE, "https://example.com/start")
    assert title == "Cart | Example Shop"
    assert url == "https://www.example.com/cart" and source == "canonical"


def test_canonical_to_another_site_is_ignored():
    html = '<link rel="canonical" href="https://evil.example/phish"><title>t</title>'
    _, url, source = extract_page_metadata(html, "https://example.com/start")
    assert url == "https://example.com/start" and source == "requested_url"


def test_canonical_with_a_non_web_scheme_is_ignored():
    html = '<link rel="canonical" href="javascript:alert(1)">'
    _, url, source = extract_page_metadata(html, "https://example.com/start")
    assert source == "requested_url"


def test_missing_title_and_canonical():
    title, url, source = extract_page_metadata("<p>hi</p>", "https://example.com/start")
    assert title is None and url == "https://example.com/start" and source == "requested_url"


# --- paths and hashing ----------------------------------------------------


def test_object_path_format():
    assert evidence_object_path(SESSION, 3, "screenshot", "jpg") == f"audit-sessions/{SESSION}/step-0003/screenshot.jpg"
    assert evidence_object_path(SESSION, 12, "dom", "html") == f"audit-sessions/{SESSION}/step-0012/dom.html"


@pytest.mark.parametrize("session", ["", "../x", "a/b", "a b", "x" * 80, "a;b"])
def test_object_path_rejects_unsafe_session_ids(session):
    with pytest.raises(EvidenceStorageError):
        evidence_object_path(session, 1, "dom", "html")


def test_object_path_rejects_bad_step_or_kind():
    with pytest.raises(EvidenceStorageError):
        evidence_object_path(SESSION, 0, "dom", "html")
    with pytest.raises(EvidenceStorageError):
        evidence_object_path(SESSION, 1, "video", "mp4")


def test_sha256_matches_hashlib_and_database_constraint_format():
    digest = sha256_hex(b"abc")
    assert digest == hashlib.sha256(b"abc").hexdigest()
    import re

    assert re.fullmatch(r"[0-9a-f]{64}", digest)


# --- Supabase store -------------------------------------------------------

SECRET_KEY = "sb_secret_exampleexampleexample"
JWT_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.c2lnbmF0dXJl"


def storage_settings(key=SECRET_KEY, **overrides):
    values = dict(supabase_url="https://abcd.supabase.co", supabase_service_role_key=key)
    values.update(overrides)
    return Settings(_env_file=None, **values)


def make_store(handler, key=SECRET_KEY, **overrides):
    seen = []

    def recording(request):
        seen.append(request)
        return handler(request)

    store = SupabaseEvidenceStore(storage_settings(key, **overrides), http=httpx.Client(transport=httpx.MockTransport(recording)))
    return store, seen


def test_upload_request_shape_for_a_new_style_secret_key():
    store, seen = make_store(lambda r: httpx.Response(200, json={"Key": "k"}))
    path = f"audit-sessions/{SESSION}/step-0001/dom.html"
    store.put(path, b"<p>hi</p>", "text/html; charset=utf-8")

    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == f"https://abcd.supabase.co/storage/v1/object/private-audit-evidence/{path}"
    assert request.headers["apikey"] == SECRET_KEY
    assert "authorization" not in request.headers  # secret keys are not JWTs
    assert request.headers["x-upsert"] == "false"  # never overwrite evidence
    assert request.headers["content-type"] == "text/html; charset=utf-8"
    assert request.content == b"<p>hi</p>"


def test_legacy_jwt_key_is_also_sent_as_bearer():
    store, seen = make_store(lambda r: httpx.Response(200, json={}), key=JWT_KEY)
    store.put("a/b.txt", b"x", "text/plain")
    assert seen[0].headers["apikey"] == JWT_KEY
    assert seen[0].headers["authorization"] == f"Bearer {JWT_KEY}"


def test_custom_bucket_name_is_used():
    store, seen = make_store(lambda r: httpx.Response(200, json={}), supabase_storage_bucket="other-bucket")
    store.put("a/b.txt", b"x", "text/plain")
    assert "/object/other-bucket/a/b.txt" in str(seen[0].url)


def test_upload_never_builds_a_public_url():
    store, seen = make_store(lambda r: httpx.Response(200, json={}))
    store.put("a/b.txt", b"x", "text/plain")
    assert "/public/" not in str(seen[0].url)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 500])
def test_upload_failures_raise_without_leaking_the_key(status):
    store, _ = make_store(lambda r: httpx.Response(status, json={"message": f"denied for {SECRET_KEY}"}))
    with pytest.raises(EvidenceStorageError) as excinfo:
        store.put("a/b.txt", b"x", "text/plain")
    assert str(status) in str(excinfo.value)
    assert SECRET_KEY not in str(excinfo.value)


def test_upload_network_failure_raises_storage_error():
    def explode(request):
        raise httpx.ConnectError(f"boom {SECRET_KEY}")

    store, _ = make_store(explode)
    with pytest.raises(EvidenceStorageError) as excinfo:
        store.put("a/b.txt", b"x", "text/plain")
    assert SECRET_KEY not in str(excinfo.value)


@pytest.mark.parametrize("path", ["", "/abs/path", "../escape", "a/../b", "a//b", "a b", "a?x=1", "a#b", "a\\b"])
def test_unsafe_object_paths_are_rejected(path):
    store, seen = make_store(lambda r: httpx.Response(200, json={}))
    with pytest.raises(EvidenceStorageError):
        store.put(path, b"x", "text/plain")
    assert seen == []


def test_redirects_are_not_followed():
    def route(request):
        if request.url.host == "abcd.supabase.co":
            return httpx.Response(307, headers={"location": "https://evil.example/"})
        raise AssertionError("followed a redirect")

    store, seen = make_store(route)
    with pytest.raises(EvidenceStorageError):
        store.put("a/b.txt", b"x", "text/plain")
    assert all(r.url.host == "abcd.supabase.co" for r in seen)


def test_missing_storage_settings_raise():
    with pytest.raises(EvidenceConfigurationError):
        SupabaseEvidenceStore(Settings(_env_file=None))
    with pytest.raises(EvidenceConfigurationError):
        SupabaseEvidenceStore(Settings(_env_file=None, supabase_url="https://x.supabase.co"))


def test_non_https_supabase_url_is_refused():
    with pytest.raises(EvidenceConfigurationError):
        SupabaseEvidenceStore(storage_settings(supabase_url="http://abcd.supabase.co"))


# --- capture --------------------------------------------------------------


class MemoryStore:
    def __init__(self, fail_on=None):
        self.objects = {}
        self.fail_on = fail_on

    def put(self, object_path, data, content_type):
        if self.fail_on and self.fail_on in object_path:
            raise EvidenceStorageError("simulated failure")
        self.objects[object_path] = (data, content_type)


def tinyfish_with(page=PAGE, screenshot=JPEG):
    def route(request):
        if request.url.path.endswith("/screenshot"):
            return httpx.Response(200, content=screenshot)
        if request.url.path.endswith("/html"):
            return httpx.Response(200, content=page)
        return httpx.Response(404)

    return TinyFishClient(
        Settings(_env_file=None, tinyfish_api_key="tf-key"),
        http=httpx.Client(transport=httpx.MockTransport(route)),
        resolver=lambda h, p: ["93.184.216.34"],
        sleep=lambda s: None,
    )


FIXED_NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)


def service(store, **kwargs):
    return EvidenceService(tinyfish_with(**kwargs), store, clock=lambda: FIXED_NOW)


def good_step(**overrides):
    values = dict(id="evt_7", timestamp="2026-10-11T15:47:53Z", action="Open the cart", screenshot="s", html="h")
    values.update(overrides)
    return RunStep(**values)


def capture(svc, step=None, number=2):
    return svc.capture_step(
        run_id=RUN_ID,
        step=step or good_step(),
        session_id=SESSION,
        step_number=number,
        requested_url="https://example.com/start",
    )


def test_capture_stores_both_artifacts_privately_with_exact_bytes():
    store = MemoryStore()
    evidence = capture(service(store))

    assert set(store.objects) == {evidence.screenshot_object_path, evidence.dom_object_path}
    assert store.objects[evidence.screenshot_object_path] == (JPEG, "image/jpeg")
    assert store.objects[evidence.dom_object_path] == (PAGE, "text/html; charset=utf-8")
    assert evidence.screenshot_object_path == f"audit-sessions/{SESSION}/step-0002/screenshot.jpg"
    assert evidence.dom_object_path == f"audit-sessions/{SESSION}/step-0002/dom.html"
    assert not evidence.screenshot_object_path.startswith(("http", "/"))


def test_capture_hashes_the_stored_bytes():
    evidence = capture(service(MemoryStore()))
    assert evidence.screenshot_sha256 == hashlib.sha256(JPEG).hexdigest()
    assert evidence.dom_sha256 == hashlib.sha256(PAGE).hexdigest()


def test_capture_fills_the_step_fields_the_database_needs():
    evidence = capture(service(MemoryStore()))
    assert evidence.step_number == 2
    assert evidence.tinyfish_step_id == "evt_7"
    assert evidence.action_description == "Open the cart"
    assert evidence.page_title == "Cart | Example Shop"
    assert evidence.page_url == "https://www.example.com/cart"
    assert evidence.page_url_source == "canonical"
    assert evidence.captured_at == datetime(2026, 10, 11, 15, 47, 53, tzinfo=timezone.utc)
    assert "Hurry! Only 2 left in stock." in evidence.dom_text


def test_capture_uses_png_extension_for_png_screenshots():
    png = b"\x89PNG\r\n\x1a\n" + b"p" * 50
    evidence = capture(service(MemoryStore(), screenshot=png))
    assert evidence.screenshot_object_path.endswith("screenshot.png")
    assert evidence.screenshot_mime_type == "image/png"


def test_capture_falls_back_to_the_clock_when_the_timestamp_is_unusable():
    evidence = capture(service(MemoryStore()), step=good_step(timestamp="garbage"))
    assert evidence.captured_at == FIXED_NOW
    evidence = capture(service(MemoryStore()), step=good_step(timestamp=None))
    assert evidence.captured_at == FIXED_NOW


def test_capture_refuses_steps_without_evidence():
    store = MemoryStore()
    with pytest.raises(EvidenceError):
        capture(service(store), step=good_step(html=None))
    with pytest.raises(EvidenceError):
        capture(service(store), step=good_step(screenshot=None))
    assert store.objects == {}


def test_storage_failure_propagates():
    with pytest.raises(EvidenceStorageError):
        capture(service(MemoryStore(fail_on="dom.html")))


def test_repr_hides_bytes_and_page_text():
    shown = repr(capture(service(MemoryStore())))
    assert "jpegdata" not in shown and "Hurry" not in shown


# --- end to end with the Phase 2 analyzer ---------------------------------


class FakeGeminiModels:
    def __init__(self, quote):
        self.quote = quote
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            text=json.dumps(
                {
                    "findings": [
                        {
                            "category": "FALSE_URGENCY",
                            "confidence_score": 0.8,
                            "explanation": "Scarcity message.",
                            "observed_behavior": "Claims 2 items remain.",
                            "evidence": [{"kind": "DOM_TEXT", "observation": self.quote}],
                        }
                    ]
                }
            )
        )


def test_captured_step_flows_through_the_gemini_analyzer_and_is_grounded():
    evidence = capture(service(MemoryStore()))
    models = FakeGeminiModels("Hurry! Only 2 left in stock.")
    analyzer = GeminiAnalyzer(
        Settings(_env_file=None, gemini_api_key="g", gemini_model="test-model"),
        client=SimpleNamespace(models=models),
    )

    report = analyzer.analyze_step(to_step_context(evidence))

    assert len(report.accepted) == 1
    assert report.accepted[0].grounding == GroundingLevel.DOM_VERIFIED
    assert report.accepted[0].step_number == 2
    image_part = models.calls[0]["contents"][0]
    assert image_part.inline_data.data == JPEG


def test_a_quote_not_on_the_captured_page_is_rejected():
    evidence = capture(service(MemoryStore()))
    analyzer = GeminiAnalyzer(
        Settings(_env_file=None, gemini_api_key="g", gemini_model="test-model"),
        client=SimpleNamespace(models=FakeGeminiModels("Only 1 left, buy now")),
    )
    report = analyzer.analyze_step(to_step_context(evidence))
    assert report.accepted == [] and len(report.rejected) == 1


def test_step_context_carries_the_captured_fields():
    evidence = capture(service(MemoryStore()))
    context = to_step_context(evidence)
    assert context.step_number == 2
    assert context.page_url == "https://www.example.com/cart"
    assert context.page_title == "Cart | Example Shop"
    assert context.screenshot == JPEG and context.screenshot_mime_type == "image/jpeg"
    assert context.dom_text == evidence.dom_text
