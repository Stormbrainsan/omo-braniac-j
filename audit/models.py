from django.db import models


class AuditLog(models.Model):
    class Event(models.TextChoices):
        OTP_REQUESTED = "otp_requested", "OTP requested"
        OTP_REQUEST_RATE_LIMITED = "otp_request_rate_limited", "OTP request rate limited"
        OTP_VERIFY_SUCCEEDED = "otp_verify_succeeded", "OTP verify succeeded"
        OTP_VERIFY_FAILED = "otp_verify_failed", "OTP verify failed"
        OTP_VERIFY_LOCKED = "otp_verify_locked", "OTP verify locked out"

    event = models.CharField(max_length=64, choices=Event.choices, db_index=True)
    email = models.EmailField(db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email", "-created_at"]),
            models.Index(fields=["event", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.event} · {self.email} · {self.created_at:%Y-%m-%d %H:%M:%S}"
