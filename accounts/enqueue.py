import logging

logger = logging.getLogger("otp")


def enqueue(task, *args, **kwargs) -> None:
    """
    Best-effort task dispatch. If the broker is unreachable (Celery/Redis
    down), a Celery-decorated task is still a plain callable — invoking it
    directly runs the task body synchronously, in-process, bypassing the
    broker entirely. That keeps the audit trail and OTP email attempt from
    being silently dropped when the broker is the thing that's broken,
    without blocking the request on a lot of retry latency in the
    success path.

    This is a deliberate trade-off documented in the README ("Failure
    scenarios: Celery unavailable"): callers of `enqueue` must be requests
    where a same-process synchronous fallback is acceptable UX (a slightly
    slower response during an outage) rather than something that must
    never block, such as sending a large batch email.
    """
    try:
        task.delay(*args, **kwargs)
    except Exception:
        logger.warning(
            "Broker unavailable, running %s synchronously as a fallback.",
            getattr(task, "name", task),
        )
        try:
            task(*args, **kwargs)
        except Exception:
            logger.exception("Synchronous fallback for %s also failed.", task)
