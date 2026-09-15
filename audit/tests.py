from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import AuditLog

User = get_user_model()


class AuditLogAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="auditor@example.com", email="auditor@example.com"
        )
        self.token = str(RefreshToken.for_user(self.user).access_token)

        # Create audit logs
        AuditLog.objects.create(
            event=AuditLog.Event.OTP_REQUESTED,
            email="target@example.com",
            ip_address="127.0.0.1",
        )
        AuditLog.objects.create(
            event=AuditLog.Event.OTP_VERIFY_SUCCEEDED,
            email="target@example.com",
            ip_address="127.0.0.1",
        )

    def test_unauthenticated_access_denied(self):
        url = reverse("audit-log-list")
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_audit_list(self):
        url = reverse("audit-log-list")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(res.data["count"], 2)

    def test_audit_filter_by_email(self):
        url = reverse("audit-log-list")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
        res = self.client.get(url, {"email": "target@example.com"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 2)
