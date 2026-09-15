# TSES Backend Engineering Assessment — OTP Authentication Service

Email-based OTP authentication built with Django + DRF, Redis for OTP
storage/rate limiting, Celery for async work, SimpleJWT for tokens, and
drf-spectacular for OpenAPI docs.

## Setup

```bash
cp .env.example .env
docker compose up --build
```

That single command builds the image, waits for Postgres to be reachable,
runs migrations, and starts the API on `http://localhost:8000` plus a
Celery worker. No manual `migrate` or `createsuperuser` step is required to
exercise the three endpoints. `createsuperuser` is only needed if you want
to browse `/admin/` — the Swagger docs at `/api/docs/` don't require auth
to view.

- Swagger UI: `http://localhost:8000/api/docs/`
- ReDoc: `http://localhost:8000/api/redoc/`
- Raw schema: `http://localhost:8000/api/schema/`

### Try it

```bash
curl -X POST localhost:8000/api/v1/auth/otp/request \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com"}'

# grab the code from `docker compose logs celery_worker`

curl -X POST localhost:8000/api/v1/auth/otp/verify \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","otp":"123456"}'

curl localhost:8000/api/v1/audit/logs \
  -H "Authorization: Bearer <access token from above>"
```

## Project structure

```
config/           settings, root urlconf, celery app, wsgi/asgi
accounts/         OTP request/verify endpoints, Redis-backed OTP logic
  services.py     OTPService — all Redis reads/writes, rate limiting, Lua scripts
  redis_client.py shared redis-py connection pool
  utils.py        email normalization, client-IP extraction
  enqueue.py      best-effort Celery dispatch with a synchronous fallback
  tasks.py        send_otp_email (logs, stands in for real email delivery)
  views.py        OTPRequestView, OTPVerifyView
audit/            AuditLog model + read API
  models.py       AuditLog
  tasks.py        write_audit_log (async DB write)
  filters.py      django-filter FilterSet (email/event/from/to)
  views.py        AuditLogListView (paginated, JWT-protected)
```

Business logic (rate limiting, OTP lifecycle, lockouts) lives in
`accounts/services.py`, not in the views — views are thin: validate input,
call the service, translate the result into an HTTP response.

## Key design decisions

**Raw redis-py instead of Django's cache framework.** The cache framework's
generic `get`/`set`/`incr` API doesn't give atomic "increment-and-set-TTL-only-on-first-write"
or atomic "compare-and-delete" — the two primitives this whole service
depends on. Both are implemented as small Lua scripts (`EVAL`), which Redis
guarantees run atomically, so there's no race window between the check and
the mutation.

**No custom User model.** The only identity attribute needed is a
normalized, unique email. `django.contrib.auth.User.username` holds the
normalized email (guaranteed unique) and `User.email` mirrors it. This
avoids the migration/admin/SimpleJWT wiring a custom user model would add,
at the cost of a slightly odd "email lives in username" mapping — flagged
below as something I'd change before production.

**JWT is issued directly from the view**, not via SimpleJWT's
`TokenObtainPairView`, because there's no password to obtain a token
against — `RefreshToken.for_user(user)` is called once OTP verification
succeeds.

**`enqueue()` synchronous fallback.** See "Failure scenarios" below — if
the broker is unreachable, the Celery task is invoked directly in-process
instead of being dropped.

**Audit log write is not on the request's critical path for correctness.**
It's dispatched async so a slow or briefly-unavailable audit write never
delays or fails the auth response — but per "failure scenarios" below, it
does fall back to a synchronous DB write if Celery itself can't be reached,
so it's still not silently lost.

## Handling the required scenarios

### Multiple OTP requests before a previous OTP expires

`store_otp()` unconditionally overwrites `otp:code:<email>` with a fresh
code and a fresh TTL. The previous code is immediately invalidated —
there's exactly one live OTP per email at a time, and it's always the most
recently issued one. This was chosen over "reject a new request while one
is still active" because rejecting creates a bad UX loop (user didn't get
the email, tries again, gets told no) with no real security benefit: the
old code becoming unusable the moment a new one is requested is arguably
*more* secure, not less. The per-email rate limit (3 per 10 minutes) is the
actual abuse control here, not the overwrite behavior.

### Concurrent OTP verification requests

Verification is a single Lua script (`GET` + conditional `DEL`) executed
atomically by Redis. If two requests race to verify the same correct code
at the same instant, Redis serializes the two `EVAL` calls: exactly one
sees the code and deletes it (success), the other finds nothing there
anymore and gets `expired` (indistinguishable from a stale/expired code, by
design — this endpoint reveals no extra information from timing). There's
no window where both requests could succeed, and no window where a correct
code is rejected because of a lost race with itself.

### Failure scenarios

- **Redis unavailable** (OTP storage/rate limiting): every Redis call in
  the request/verify views is wrapped, and a `redis.exceptions.RedisError`
  is turned into `503 Service Unavailable`. We fail closed here — if we
  can't check rate limits or store a fresh OTP, we don't guess.
- **Celery/broker unavailable**: `accounts/enqueue.py` tries `.delay()`
  first; if that raises (broker unreachable), it invokes the
  Celery-decorated task directly as a plain Python function, running it
  synchronously in the request/response cycle instead of dropping it. This
  keeps the audit trail intact and still "sends" the OTP email (via the
  same logger) during a broker outage, at the cost of slightly higher
  latency on that specific request. This is a deliberate trade-off for a
  service where losing an audit record is worse than an occasional slow
  response; it would be wrong for a task doing genuinely heavy or
  slow work.
- **Celery worker crashes mid-task / Postgres blip during an audit
  write**: both `send_otp_email` and `write_audit_log` are registered with
  `autoretry_for=(Exception,)` and exponential backoff (`retry_backoff`,
  max 3 retries), so a transient DB hiccup during the audit write retries
  a few times before giving up rather than failing on the first blip.

### Email address normalization and identity

`accounts/utils.normalize_email()` always lowercases and strips
whitespace — `Test@Gmail.com` and `test@gmail.com` are the same account,
because no mainstream provider treats the local-part as case-sensitive in
practice even though RFC 5321 technically permits it.

**Plus-addressing is *not* collapsed by default.** `test@gmail.com`,
`test+123@gmail.com`, and `test+work@gmail.com` are treated as three
distinct identities unless `NORMALIZE_GMAIL_PLUS_ALIAS=1` is set. Reasoning:

- Plus-tags are semantically meaningful to the people who use them — they
  rely on the distinction to filter/route/track where an address was
  given out. Silently merging `you+bank@x.com` and `you+forum@x.com` into
  one account removes a signal the user deliberately created.
- The "strip everything after `+`" heuristic is Gmail/Googlemail-specific
  behavior, not a general email rule. Applying it to arbitrary domains
  would be actively wrong for providers where `+` isn't a sub-addressing
  delimiter at all, or where two different real mailboxes could
  legitimately both deliver mail that ends up validating the same
  "normalized" string.
- The trade-off of *not* normalizing: a user could accidentally create two
  separate accounts (`test@gmail.com` and `test+work@gmail.com`) without
  realizing they're "the same person" to a human, and would get two
  separate audit trails / two separate JWT identities. I judged that a
  minor, self-inflicted annoyance vs. the identity-confusion risk of
  guessing wrong about provider-specific aliasing rules.

Gmail also ignores dots in the local-part (`te.st@gmail.com` ==
`test@gmail.com`), which the same `NORMALIZE_GMAIL_PLUS_ALIAS` flag also
collapses when enabled, scoped strictly to `gmail.com`/`googlemail.com`
domains — it's never applied to other providers.

## Assumptions

- "Create or update the user" on successful verification means
  get-or-create by normalized email; there's no separate registration
  step.
- The audit log's `filter by email` is an exact (case-insensitive) match,
  not a substring search, since audit lookups are almost always "show me
  everything for this one address."
- `from`/`to` audit filters are ISO-8601 datetimes (not bare dates) so a
  caller can scope to a specific hour, not just a day.
- Rate limiting counts *requests*, not successful sends — a rate-limited
  request still counts against future attempts (both counters are bumped
  before the limit check short-circuits further processing), which is the
  conservative/anti-abuse reading of "max N requests."
- 429/423 responses include `Retry-After` (seconds) since the brief calls
  it out as a nice-to-have for the request endpoint, and it's just as
  useful on the lockout response.

## Trade-offs considered

- **In-process synchronous fallback vs. dead-letter queue.** A more robust
  answer to "Celery is down" is a persistent local dead-letter store
  (e.g. an outbox table) that a recovery job replays once the broker comes
  back. I went with the simpler synchronous fallback because it's
  sufficient for the two lightweight tasks this service has (a log line
  and a single DB insert) and doesn't need extra infrastructure — but it's
  the first thing I'd swap out if these tasks got heavier or slower.
- **Django's default User vs. a custom user model.** Noted above under
  "no custom User model" — the fastest path for this assessment, but not
  what I'd start a real product on.
- **Lua scripts vs. `MULTI`/`WATCH` transactions.** Both give atomicity;
  Lua scripting was chosen because it's simpler to read as one unit and
  avoids the optimistic-retry-on-conflict boilerplate `WATCH` needs.

## Edge cases handled

- Wrong OTP format (`otp` isn't exactly 6 digits) is a `400` from
  serializer validation, before touching Redis at all.
- Verifying against an email with no OTP ever requested returns the same
  "expired" response as a genuinely expired one — no information leak
  about whether a request was ever made.
- Hitting the per-email and per-IP request limits in the same call still
  reports a single coherent `429` (email limit is checked first, since
  it's the tighter, more specific control).
- A locked-out email (5 failed verifies in 15 minutes) is rejected with
  `423 Locked` even if the *correct* OTP is finally submitted — a
  successful late guess doesn't bypass the lockout.
- Successful verification resets the failed-attempt counter and any lock,
  so a legitimate user isn't punished by an earlier attacker's failed
  attempts once they get the right code in through a fresh request.

## Improvements before production

- Swap the "email lives in `User.username`" mapping for a proper custom
  user model with `email` as `USERNAME_FIELD`.
- Real email delivery (SES/Postmark) behind the same `send_otp_email` task
  boundary — the async/retry structure is already correct.
- An outbox-table-based dead-letter approach instead of the synchronous
  Celery fallback, once tasks do more than a log line and a DB insert.
- Blacklist/rotate refresh tokens on logout (`BLACKLIST_AFTER_ROTATION` is
  off in `SIMPLE_JWT` right now for simplicity — flipping it on needs the
  `token_blacklist` app wired in).
- Structured (JSON) logging and a real APM/metrics hook instead of the
  plain `logger.info` calls used to satisfy "log output is sufficient."
- Terraform/IaC for Postgres/Redis instead of the docker-compose
  containers, and secrets management instead of a plain `.env` file.
