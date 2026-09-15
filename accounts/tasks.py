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
def send_otp_email(self, email: str, code: str) -> None:
    """
    Per the brief, actually sending mail is out of scope — logging from the
    worker process stands in for a real email backend (SES/Postmark/etc).
    Swapping this for a real send is a one-line change: call
    django.core.mail.send_mail(...) here instead of logger.info, since the
    task boundary (async, retried, idempotent-enough for an OTP resend) is
    already correct.
    """
    logger.info("Sending OTP %s to %s (worker pid task id=%s)", code, email, self.request.id)
