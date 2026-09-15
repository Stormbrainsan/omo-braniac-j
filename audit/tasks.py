import logging

from celery import shared_task

logger = logging.getLogger("otp")


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=30,
    max_retries=3,
)
def write_audit_log(
    self, event: str, email: str, ip_address: str, user_agent: str, metadata: dict
) -> None:
    # Imported here rather than at module load time to avoid a hard
    # dependency on Django's app registry being ready when Celery first
    # imports task modules (autodiscover happens very early in some
    # deployment setups).
    from .models import AuditLog

    AuditLog.objects.create(
        event=event,
        email=email,
        ip_address=ip_address or None,
        user_agent=user_agent[:512],
        metadata=metadata or {},
    )
    logger.info("Audit log written: %s for %s", event, email)
