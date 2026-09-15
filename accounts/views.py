from django.contrib.auth import get_user_model
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from redis.exceptions import RedisError
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from audit.tasks import write_audit_log

from .enqueue import enqueue
from .serializers import OTPRequestSerializer, OTPVerifySerializer, TokenPairSerializer
from .services import OTPLocked, OTPService, RateLimitExceeded, VerifyResult
from .tasks import send_otp_email
from .utils import get_client_ip, normalize_email

User = get_user_model()


class OTPRequestView(APIView):
    """
    POST /api/v1/auth/otp/request

    Generates and stores a one-time code for the given email, subject to
    per-email and per-IP rate limits. Never reveals whether the email
    belongs to an existing user (this is an auth entry point, not a
    lookup).
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=OTPRequestSerializer,
        responses={
            202: OpenApiResponse(description="OTP generated and queued for delivery."),
            400: OpenApiResponse(description="Invalid email."),
            429: OpenApiResponse(description="Rate limit exceeded."),
            503: OpenApiResponse(description="Redis unavailable."),
        },
        examples=[
            OpenApiExample(
                "Request OTP",
                value={"email": "user@example.com"},
                request_only=True,
            )
        ],
    )
    def post(self, request):
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = normalize_email(serializer.validated_data["email"])
        ip_address = get_client_ip(request)

        service = OTPService()
        try:
            service.enforce_request_rate_limits(email, ip_address)
        except RateLimitExceeded as exc:
            enqueue(
                write_audit_log,
                event="otp_request_rate_limited",
                email=email,
                ip_address=ip_address,
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
                metadata={"scope": exc.scope},
            )
            return Response(
                {
                    "detail": (
                        "Too many OTP requests. Please wait before trying again."
                    ),
                    "retry_after": exc.retry_after,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": str(exc.retry_after)},
            )
        except RedisError:
            return Response(
                {"detail": "Service temporarily unavailable. Please try again shortly."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            code = service.store_otp(email)
        except RedisError:
            return Response(
                {"detail": "Service temporarily unavailable. Please try again shortly."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        enqueue(send_otp_email, email=email, code=code)
        enqueue(
            write_audit_log,
            event="otp_requested",
            email=email,
            ip_address=ip_address,
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            metadata={},
        )

        return Response(
            {"detail": "OTP generated. Check your email."},
            status=status.HTTP_202_ACCEPTED,
        )


class OTPVerifyView(APIView):
    """
    POST /api/v1/auth/otp/verify

    Validates a submitted OTP, creates/updates the corresponding user on
    success, and returns a JWT access/refresh pair.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=OTPVerifySerializer,
        responses={
            200: TokenPairSerializer,
            400: OpenApiResponse(description="Invalid or expired OTP."),
            423: OpenApiResponse(description="Account locked after too many failed attempts."),
            503: OpenApiResponse(description="Redis unavailable."),
        },
        examples=[
            OpenApiExample(
                "Verify OTP",
                value={"email": "user@example.com", "otp": "123456"},
                request_only=True,
            )
        ],
    )
    def post(self, request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = normalize_email(serializer.validated_data["email"])
        submitted_code = serializer.validated_data["otp"]
        ip_address = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        service = OTPService()
        try:
            result = service.verify(email, submitted_code)
        except OTPLocked as exc:
            enqueue(
                write_audit_log,
                event="otp_verify_locked",
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={},
            )
            return Response(
                {
                    "detail": "Too many failed attempts. Account temporarily locked.",
                    "retry_after": exc.retry_after,
                },
                status=status.HTTP_423_LOCKED,
                headers={"Retry-After": str(exc.retry_after)},
            )
        except RedisError:
            return Response(
                {"detail": "Service temporarily unavailable. Please try again shortly."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if result.status != VerifyResult.STATUS_OK:
            service.register_failed_attempt(email)
            enqueue(
                write_audit_log,
                event="otp_verify_failed",
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"reason": result.status},
            )
            message = (
                "OTP has expired or was never requested."
                if result.status == VerifyResult.STATUS_EXPIRED
                else "Incorrect OTP."
            )
            return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)

        service.reset_failed_attempts(email)

        user, _ = User.objects.get_or_create(
            username=email, defaults={"email": email}
        )
        if user.email != email:
            user.email = email
            user.save(update_fields=["email"])

        refresh = RefreshToken.for_user(user)

        enqueue(
            write_audit_log,
            event="otp_verify_succeeded",
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"user_id": user.id},
        )

        return Response(
            {"access": str(refresh.access_token), "refresh": str(refresh)},
            status=status.HTTP_200_OK,
        )
