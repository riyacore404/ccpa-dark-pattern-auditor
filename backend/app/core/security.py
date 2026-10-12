"""Target URL validation and the agent-action guard.

validate_target_url():
    Accepts only public http(s) websites. Rejects credentials in the URL,
    unusual ports, internal-looking names, and any name that resolves to a
    non-public address.

    Limit to be aware of: the browser runs on TinyFish's infrastructure and
    resolves names itself, so this check is best-effort. It stops obviously
    internal or malformed targets from being submitted, but it cannot stop
    DNS changing after the check or a public site redirecting somewhere else.

check_agent_action():
    A conservative text screen over what the browsing agent says it is doing.
    It is one layer of defense in depth. The primary controls are the rules
    in the goal text and never giving the agent any credentials.
"""

import ipaddress
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

MAX_URL_LENGTH = 2048
ALLOWED_PORTS = frozenset({80, 443})

_BLOCKED_SUFFIXES = (
    ".local",
    ".localhost",
    ".localdomain",
    ".internal",
    ".intranet",
    ".lan",
    ".home",
    ".corp",
    ".private",
)
_LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
_EXTRA_BLOCKED_NETWORKS = (
    ipaddress.ip_network("64:ff9b::/96"),  # NAT64 can embed private IPv4
    ipaddress.ip_network("2002::/16"),  # 6to4 can embed private IPv4
)

Resolver = Callable[[str, int], list[str]]


class TargetValidationError(ValueError):
    """The submitted target URL is not acceptable."""


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    return sorted({info[4][0].split("%")[0] for info in infos})


def is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    for network in _EXTRA_BLOCKED_NETWORKS:
        if network.version == address.version and address in network:
            return False
    return bool(
        address.is_global
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
    )


def validate_target_url(raw: object, *, resolver: Resolver = system_resolver) -> str:
    """Return a normalized public URL, or raise TargetValidationError."""
    if not isinstance(raw, str):
        raise TargetValidationError("URL must be a string")
    text = raw.strip()
    if not text:
        raise TargetValidationError("URL is empty")
    if len(text) > MAX_URL_LENGTH:
        raise TargetValidationError("URL is too long")
    if any(ord(ch) <= 32 or ord(ch) == 127 for ch in text) or "\\" in text:
        raise TargetValidationError("URL contains whitespace, control or backslash characters")

    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError as exc:
        raise TargetValidationError("URL is malformed") from exc

    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise TargetValidationError("only http and https URLs are allowed")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise TargetValidationError("URLs containing credentials are not allowed")
    if port is not None and port not in ALLOWED_PORTS:
        raise TargetValidationError("only the default web ports (80, 443) are allowed")

    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise TargetValidationError("URL has no host")

    literal: ipaddress.IPv4Address | ipaddress.IPv6Address | None
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        if not is_public_address(literal):
            raise TargetValidationError("IP address is not a public address")
        host_for_url = f"[{host}]" if literal.version == 6 else host
        resolved_host = host
    else:
        try:
            ascii_host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise TargetValidationError("host name is not valid") from exc
        labels = ascii_host.split(".")
        if len(ascii_host) > 253 or len(labels) < 2:
            raise TargetValidationError("host must be a fully qualified public domain name")
        if not all(_LABEL.match(label) for label in labels):
            raise TargetValidationError("host name is not valid")
        if labels[-1].isdigit():
            raise TargetValidationError("numeric host names are not allowed")
        if ascii_host.endswith(_BLOCKED_SUFFIXES):
            raise TargetValidationError("internal host names are not allowed")
        host_for_url = ascii_host
        resolved_host = ascii_host

    if literal is None:
        try:
            addresses = resolver(resolved_host, port or (443 if scheme == "https" else 80))
        except OSError as exc:
            raise TargetValidationError("host name could not be resolved") from exc
        if not addresses:
            raise TargetValidationError("host name could not be resolved")
        for address in addresses:
            try:
                parsed = ipaddress.ip_address(address)
            except ValueError as exc:
                raise TargetValidationError("host resolved to an invalid address") from exc
            if not is_public_address(parsed):
                raise TargetValidationError("host resolves to a non-public address")

    netloc = host_for_url + (f":{port}" if port else "")
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))


# ---------------------------------------------------------------------------
# Agent-action guard
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActionVerdict:
    allowed: bool
    rule: str | None = None
    matched: str | None = None


_GUARD_RULES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern, re.IGNORECASE))
    for name, pattern in (
        (
            "payment_details",
            r"\b(credit|debit)\s+card\b|\bcard\s+(number|details|info\w*)\b"
            r"|\bcvv\b|\bcvc\b|\bupi\b|\bnet\s*banking\b|\bbank\s+account\b",
        ),
        (
            "otp",
            r"\botp\b|\bone[\s-]time\s+(password|passcode|pin|code)\b"
            r"|\b(verification|security|sms)\s+code\b",
        ),
        (
            "purchase",
            r"\bplac(e|es|ed|ing)\s+(the\s+|an?\s+|your\s+|this\s+)?order\b"
            r"|\b(pay|paying)\s+now\b"
            r"|\bconfirm(s|ed|ing)?\s+(the\s+|your\s+|this\s+)?"
            r"(purchase|payment|order|booking|subscription)\b"
            r"|\bcomplet(e|es|ed|ing)\s+(the\s+|your\s+|this\s+)?"
            r"(purchase|payment|checkout|order|booking)\b"
            r"|\bbuy\s+now\b"
            r"|\bsubscrib(e|es|ed|ing)\s+(now|to)\b"
            r"|\bstart(s|ed|ing)?\s+(the\s+|a\s+|your\s+)?(free\s+)?trial\b",
        ),
        (
            "login",
            r"\b(log|sign)(s|ged|ging)?[\s-]*in(to)?\b|\bpassword\b"
            r"|\bcreat(e|es|ed|ing)\s+(an?\s+|the\s+|your\s+)?account\b"
            r"|\bsign(s|ed|ing)?\s+up\b|\bregist(er|ers|ered|ering)\b",
        ),
        (
            "captcha",
            r"\bcaptcha\b|\brecaptcha\b|\bhcaptcha\b|\bhuman\s+verification\b"
            r"|\bverify\s+(you\s+are|that\s+you\s+are)\s+(a\s+)?human\b"
            r"|\bbot\s+(check|detection)\b",
        ),
    )
)


def check_agent_action(text: str | None) -> ActionVerdict:
    """Screen one agent step description. Deliberately conservative: a
    blocked verdict stops the run for human review, it is not a finding."""
    if not text or not text.strip():
        return ActionVerdict(allowed=True)
    for name, pattern in _GUARD_RULES:
        match = pattern.search(text)
        if match:
            return ActionVerdict(allowed=False, rule=name, matched=match.group(0))
    return ActionVerdict(allowed=True)
