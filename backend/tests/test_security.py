import pytest

from app.core.security import (
    TargetValidationError,
    check_agent_action,
    is_public_address,
    validate_target_url,
)
import ipaddress

PUBLIC = ["93.184.216.34"]


def public_resolver(host, port):
    return PUBLIC


def validate(url, resolver=public_resolver):
    return validate_target_url(url, resolver=resolver)


# --- accepted -------------------------------------------------------------


def test_plain_https_url_is_accepted():
    assert validate("https://example.com/shop?a=1") == "https://example.com/shop?a=1"


def test_http_url_is_accepted_and_fragment_dropped():
    assert validate("http://example.com/x#section") == "http://example.com/x"


def test_host_is_lowercased_and_trailing_dot_removed():
    assert validate("https://EXAMPLE.com./") == "https://example.com/"


def test_empty_path_becomes_slash():
    assert validate("https://example.com") == "https://example.com/"


def test_default_ports_are_allowed():
    assert validate("https://example.com:443/") == "https://example.com:443/"
    assert validate("http://example.com:80/") == "http://example.com:80/"


def test_unicode_host_is_converted_to_ascii():
    assert validate("https://bücher.example/") == "https://xn--bcher-kva.example/"


def test_public_ip_literal_is_accepted_without_dns():
    def boom(host, port):
        raise AssertionError("resolver must not be used for IP literals")

    assert validate("http://8.8.8.8/", resolver=boom) == "http://8.8.8.8/"


def test_surrounding_whitespace_is_trimmed():
    assert validate("  https://example.com/  ") == "https://example.com/"


def test_resolver_receives_host_and_scheme_default_port():
    seen = []

    def spy(host, port):
        seen.append((host, port))
        return PUBLIC

    validate_target_url("https://example.com/", resolver=spy)
    validate_target_url("http://example.com/", resolver=spy)
    assert seen == [("example.com", 443), ("example.com", 80)]


# --- rejected: syntax -----------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "example.com",
        "ftp://example.com/",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,hi",
        "https://",
        "https:///path",
        "https://exa mple.com/",
        "https://example.com/\nHost: evil",
        "https://example.com\\@evil.com/",
        "https://user:pw@example.com/",
        "https://example.com@evil.com/",
        "https://example.com:8080/",
        "https://example.com:22/",
        "https://example.com:notaport/",
        "https://" + "a" * 70 + ".com/",
        "https://example.com/" + "a" * 2100,
    ],
)
def test_malformed_or_unsafe_urls_are_rejected(url):
    with pytest.raises(TargetValidationError):
        validate(url)


@pytest.mark.parametrize("value", [None, 123, ["https://example.com"], b"https://example.com"])
def test_non_string_input_is_rejected(value):
    with pytest.raises(TargetValidationError):
        validate(value)


# --- rejected: internal names and addresses -------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://intranet/",
        "http://printer.local/",
        "http://db.internal/",
        "http://nas.lan/",
        "http://x.localhost/",
        "http://2130706433/",
        "http://0x7f.0.0.1/",
        "http://127.1/",
        "http://example.123/",
    ],
)
def test_internal_or_numeric_host_names_are_rejected(url):
    with pytest.raises(TargetValidationError):
        validate(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.64.0.1/",
        "http://100.100.100.200/",
        "http://0.0.0.0/",
        "http://224.0.0.1/",
        "http://240.0.0.1/",
        "http://[::1]/",
        "http://[fe80::1]/",
        "http://[fc00::1]/",
        "http://[fd00:ec2::254]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[::ffff:10.0.0.1]/",
        "http://[64:ff9b::7f00:1]/",
        "http://[2002:7f00:1::]/",
    ],
)
def test_non_public_ip_literals_are_rejected(url):
    with pytest.raises(TargetValidationError):
        validate(url)


def test_name_resolving_to_private_address_is_rejected():
    with pytest.raises(TargetValidationError):
        validate("https://sneaky.example.com/", resolver=lambda h, p: ["10.0.0.7"])


def test_name_resolving_to_mixed_addresses_is_rejected():
    with pytest.raises(TargetValidationError):
        validate("https://mixed.example.com/", resolver=lambda h, p: ["93.184.216.34", "127.0.0.1"])


def test_name_resolving_to_metadata_address_is_rejected():
    with pytest.raises(TargetValidationError):
        validate("https://meta.example.com/", resolver=lambda h, p: ["169.254.169.254"])


def test_unresolvable_name_is_rejected():
    def fail(host, port):
        raise OSError("no such host")

    with pytest.raises(TargetValidationError):
        validate("https://nope.example.com/", resolver=fail)


def test_empty_resolution_is_rejected():
    with pytest.raises(TargetValidationError):
        validate("https://nope.example.com/", resolver=lambda h, p: [])


def test_garbage_resolution_is_rejected():
    with pytest.raises(TargetValidationError):
        validate("https://nope.example.com/", resolver=lambda h, p: ["not-an-ip"])


def test_is_public_address_basics():
    assert is_public_address(ipaddress.ip_address("8.8.8.8"))
    assert is_public_address(ipaddress.ip_address("2606:4700:4700::1111"))
    assert not is_public_address(ipaddress.ip_address("192.168.0.1"))


# --- agent action guard ---------------------------------------------------


@pytest.mark.parametrize(
    "text,rule",
    [
        ("Entering the credit card number into the form", "payment_details"),
        ("Typing CVV", "payment_details"),
        ("Selecting UPI as the payment method", "payment_details"),
        ("Fill in debit card details", "payment_details"),
        ("Waiting for the OTP to arrive", "otp"),
        ("Entering the one-time password", "otp"),
        ("Typing the verification code", "otp"),
        ("Clicking Place order", "purchase"),
        ("Placing the order now", "purchase"),
        ("Click Pay now", "purchase"),
        ("Confirm the purchase", "purchase"),
        ("Completing checkout", "purchase"),
        ("Click Buy now", "purchase"),
        ("Subscribing now to the newsletter plan", "purchase"),
        ("Start your free trial", "purchase"),
        ("Logging in with the account", "login"),
        ("Click Sign in", "login"),
        ("Entering the password", "login"),
        ("Create an account", "login"),
        ("Registering a new user", "login"),
        ("Solving the CAPTCHA", "captcha"),
        ("Pass the reCAPTCHA challenge", "captcha"),
    ],
)
def test_guard_blocks_forbidden_actions(text, rule):
    verdict = check_agent_action(text)
    assert verdict.allowed is False
    assert verdict.rule == rule
    assert verdict.matched


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "   ",
        "Visit example.com to read heading and paragraph",
        "Extract main heading and first paragraph",
        "Scroll down to see the product list",
        "Click on the first product",
        "Add the item to the cart",
        "Open the cart and read the order summary",
        "Read the delivery fee shown at checkout summary",
        "Enter pincode 110001 to check delivery",
        "Return heading and paragraph as JSON",
        "Task completed",
        "Close the newsletter pop-up",
        "Note the countdown timer showing 10 minutes",
    ],
)
def test_guard_allows_ordinary_browsing(text):
    assert check_agent_action(text).allowed is True
