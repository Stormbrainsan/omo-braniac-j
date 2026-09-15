from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .services import OTPService, RateLimitExceeded
from .utils import normalize_email

User = get_user_model()


class EmailNormalizationTests(APITestCase):
    def test_normalize_email_basic(self):
        self.assertEqual(normalize_email("  TestUser@Example.COM  "), "testuser@example.com")

    def test_normalize_email_gmail_plus_disabled(self):
        with patch.object(settings, "NORMALIZE_GMAIL_PLUS_ALIAS", False):
            self.assertEqual(normalize_email("test+alias@gmail.com"), "test+alias@gmail.com")

    def test_normalize_email_gmail_plus_enabled(self):
        with patch.object(settings, "NORMALIZE_GMAIL_PLUS_ALIAS", True):
            self.assertEqual(normalize_email("te.st+alias@gmail.com"), "test@gmail.com")


class OTPServiceTests(APITestCase):
    def setUp(self):
        self.service = OTPService()
        self.email = "testservice@example.com"
        # Clear keys for this email
        self.service.client.delete(
            f"otp:code:{self.email}",
            f"otp:req:email:{self.email}",
            f"otp:fail:{self.email}",
            f"otp:lock:{self.email}",
        )

    def test_store_and_verify_otp(self):
        code = self.service.store_otp(self.email)
        self.assertEqual(len(code), 6)

        # Verify correct code
        res = self.service.verify(self.email, code)
        self.assertEqual(res.status, "ok")

        # Second verify should fail (expired/deleted because it's single-use)
        res_second = self.service.verify(self.email, code)
        self.assertEqual(res_second.status, "expired")

    def test_rate_limiting(self):
        with patch.object(settings, "OTP_REQUEST_MAX_PER_EMAIL", 2):
            self.service.enforce_request_rate_limits(self.email, "127.0.0.1")
            self.service.enforce_request_rate_limits(self.email, "127.0.0.1")
            with self.assertRaises(RateLimitExceeded):
                self.service.enforce_request_rate_limits(self.email, "127.0.0.1")


class OTPAPITests(APITestCase):
    def setUp(self):
        self.email = "testapi@example.com"
        self.service = OTPService()
        self.service.client.delete(
            f"otp:code:{self.email}",
            f"otp:req:email:{self.email}",
            f"otp:fail:{self.email}",
            f"otp:lock:{self.email}",
        )

    @patch("accounts.views.enqueue")
    def test_otp_request_and_verify_flow(self, mock_enqueue):
        # 1. Request OTP
        url_req = reverse("otp-request")
        res_req = self.client.post(url_req, {"email": self.email}, format="json")
        self.assertEqual(res_req.status_code, status.HTTP_202_ACCEPTED)

        # 2. Get stored code from Redis directly
        code = self.service.client.get(f"otp:code:{self.email}")
        self.assertIsNotNone(code)

        # 3. Verify OTP
        url_ver = reverse("otp-verify")
        res_ver = self.client.post(
            url_ver, {"email": self.email, "otp": code}, format="json"
        )
        self.assertEqual(res_ver.status_code, status.HTTP_200_OK)
        self.assertIn("access", res_ver.data)
        self.assertIn("refresh", res_ver.data)

        # User should now exist in DB
        self.assertTrue(User.objects.filter(username=self.email).exists())
