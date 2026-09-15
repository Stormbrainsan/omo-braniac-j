from django.conf import settings

GMAIL_DOMAINS = {"gmail.com", "googlemail.com", "hotmail.com", "outlook.com"}


def normalize_email(raw_email: str) -> str:
    """
    Baseline normalization applied to every email, regardless of provider:
    strip surrounding whitespace and lowercase it. This is safe because
    email local-parts and domains are effectively case-insensitive in
    practice (RFC 5321 technically allows case-sensitive local-parts, but
    no mainstream provider actually honors that — Gmail, Outlook, Yahoo all
    treat mail as case-insensitive), so lowercasing prevents
    "Test@Gmail.com" and "test@gmail.com" from being silently treated as
    two different accounts.

    Plus-addressing (test+work@gmail.com) is intentionally NOT collapsed to
    its base address by default. See README "Email address normalization
    and identity" for the full reasoning — in short: plus-tags are
    semantically meaningful (users rely on them for filtering, and some
    providers - not just Gmail - support them as fully distinct routable
    addresses), so silently merging identities based on a heuristic that
    only really holds for Gmail/Googlemail risks account-confusion bugs
    that are worse than the deduplication benefit.

    Set NORMALIZE_GMAIL_PLUS_ALIAS=1 to opt into Gmail-specific plus-tag and
    dot-insensitivity collapsing if your product decides that trade-off is
    worth it for a specific provider.
    """
    email = raw_email.strip().lower()

    if not settings.NORMALIZE_GMAIL_PLUS_ALIAS:
        return email

    if "@" not in email:
        return email

    local, _, domain = email.partition("@")
    if domain not in GMAIL_DOMAINS:
        return email

    local = local.split("+", 1)[0]
    local = local.replace(".", "")
    return f"{local}@{domain}"


def get_client_ip(request) -> str:
    """
    Prefers X-Forwarded-For (set by a reverse proxy/load balancer in front
    of the app) and falls back to REMOTE_ADDR for direct connections. Only
    the first hop of X-Forwarded-For is trusted here; in production this
    should be paired with a proxy that strips/overwrites client-supplied
    X-Forwarded-For headers so this can't be spoofed to dodge IP rate
    limiting.
    """
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")
