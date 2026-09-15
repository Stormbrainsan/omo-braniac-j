# TSES Email OTP Authentication Service

Email-based OTP authentication built with Django + DRF, Redis for OTP
storage/rate limiting, Celery for async work, SimpleJWT for tokens, and
drf-spectacular for OpenAPI docs.

## Setup

```bash
cp .env.example .env
docker compose up --build
```

That single command builds the image, waits for Postgres to be reachable,
runs migrations, and starts the API on `http://localhost:8000`

- Swagger UI: `http://localhost:8000/api/docs/`
- ReDoc: `http://localhost:8000/api/redoc/`
- Raw schema: `http://localhost:8000/api/schema/`



Business logic (rate limiting, OTP lifecycle, lockouts) lives in
`accounts/services.py`, 
