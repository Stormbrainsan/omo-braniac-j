import random
from dataclasses import dataclass

from django.conf import settings

from .redis_client import get_redis_client

# ---------------------------------------------------------------------------
# Redis key layout
# ---------------------------------------------------------------------------
# otp:code:<email>        -> the current 6-digit OTP               (TTL = OTP_TTL_SECONDS)
# otp:req:email:<email>   -> request counter for that email         (TTL = OTP_REQUEST_WINDOW_EMAIL_SECONDS)
# otp:req:ip:<ip>         -> request counter for that IP            (TTL = OTP_REQUEST_WINDOW_IP_SECONDS)
# otp:fail:<email>        -> failed-verify counter for that email   (TTL = OTP_LOCKOUT_WINDOW_SECONDS)
# otp:lock:<email>        -> presence = account locked out          (TTL = OTP_LOCKOUT_WINDOW_SECONDS)

CODE_KEY = "otp:code:{email}"
REQ_EMAIL_KEY = "otp:req:email:{email}"
REQ_IP_KEY = "otp:req:ip:{ip}"
FAIL_KEY = "otp:fail:{email}"
LOCK_KEY = "otp:lock:{email}"

# Atomically increment a counter and set its expiry only the first time it's
# created, so a burst of requests never resets the sliding window.
_INCR_WITH_EXPIRY = """
local current = redis.call('INCR', KEYS[1])
if tonumber(current) == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""

# Atomically verify-and-consume an OTP: only deletes the stored code if it
# matches what was submitted. This is what makes OTPs one-time-use and safe
# under concurrent verification attempts (see README "Concurrent OTP
# verification").
_CHECK_AND_CONSUME = """
local stored = redis.call('GET', KEYS[1])
if not stored then
    return -1
end
if stored == ARGV[1] then
    redis.call('DEL', KEYS[1])
    return 1
end
return 0
"""


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int, scope: str):
        self.retry_after = retry_after
        self.scope = scope
        super().__init__(f"Rate limit exceeded for {scope}, retry after {retry_after}s")


class OTPLocked(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Account locked, retry after {retry_after}s")


@dataclass
class VerifyResult:
    STATUS_OK = "ok"
    STATUS_INVALID = "invalid"
    STATUS_EXPIRED = "expired"
    status: str


class OTPService:
    """
    Wraps every Redis interaction the OTP flow needs. Kept as a thin class
    (rather than free functions) so views/tests can swap the redis client or
    mock this out entirely without touching Django settings.
    """

    def __init__(self):
        self.client = get_redis_client()
        self._incr_with_expiry = self.client.register_script(_INCR_WITH_EXPIRY)
        self._check_and_consume = self.client.register_script(_CHECK_AND_CONSUME)

    # -- rate limiting -----------------------------------------------------
    def _bump_and_enforce(self, key: str, limit: int, window: int, scope: str) -> None:
        count = self._incr_with_expiry(keys=[key], args=[window])
        if int(count) > limit:
            ttl = self.client.ttl(key)
            raise RateLimitExceeded(retry_after=max(ttl, 1), scope=scope)

    def enforce_request_rate_limits(self, email: str, ip_address: str) -> None:
        """
        Raises RateLimitExceeded if either the per-email or per-IP request
        limit has been exceeded. Both counters are bumped so that abusive
        traffic is tracked on both axes regardless of which one trips first.
        """
        self._bump_and_enforce(
            REQ_EMAIL_KEY.format(email=email),
            settings.OTP_REQUEST_MAX_PER_EMAIL,
            settings.OTP_REQUEST_WINDOW_EMAIL_SECONDS,
            scope="email",
        )
        self._bump_and_enforce(
            REQ_IP_KEY.format(ip=ip_address),
            settings.OTP_REQUEST_MAX_PER_IP,
            settings.OTP_REQUEST_WINDOW_IP_SECONDS,
            scope="ip",
        )

    # -- OTP lifecycle -------------------------------------------------------
    @staticmethod
    def generate_code() -> str:
        return f"{random.randint(0, 999999):06d}"

    def store_otp(self, email: str) -> str:
        """
        Generates a fresh OTP and overwrites whatever was previously stored
        for this email. Overwriting (rather than rejecting a new request
        while one is still live) is the intended behavior for "multiple OTP
        requests before a previous OTP expires" — see README.
        """
        code = self.generate_code()
        self.client.set(CODE_KEY.format(email=email), code, ex=settings.OTP_TTL_SECONDS)
        return code

    def is_locked(self, email: str) -> int | None:
        ttl = self.client.ttl(LOCK_KEY.format(email=email))
        return ttl if ttl and ttl > 0 else None

    def register_failed_attempt(self, email: str) -> None:
        key = FAIL_KEY.format(email=email)
        count = self._incr_with_expiry(
            keys=[key], args=[settings.OTP_LOCKOUT_WINDOW_SECONDS]
        )
        if int(count) >= settings.OTP_MAX_FAILED_ATTEMPTS:
            self.client.set(
                LOCK_KEY.format(email=email),
                "1",
                ex=settings.OTP_LOCKOUT_WINDOW_SECONDS,
            )

    def reset_failed_attempts(self, email: str) -> None:
        self.client.delete(FAIL_KEY.format(email=email), LOCK_KEY.format(email=email))

    def verify(self, email: str, submitted_code: str) -> VerifyResult:
        """
        Checks a lockout first, then atomically consumes the stored OTP if
        it matches. Does NOT itself record failed attempts / reset them —
        the caller (the view) does that, so this method stays a pure
        Redis-facing primitive that's easy to unit test.
        """
        locked_ttl = self.is_locked(email)
        if locked_ttl is not None:
            raise OTPLocked(retry_after=locked_ttl)

        result = self._check_and_consume(
            keys=[CODE_KEY.format(email=email)], args=[submitted_code]
        )
        result = int(result)
        if result == 1:
            return VerifyResult(status=VerifyResult.STATUS_OK)
        if result == -1:
            return VerifyResult(status=VerifyResult.STATUS_EXPIRED)
        return VerifyResult(status=VerifyResult.STATUS_INVALID)
