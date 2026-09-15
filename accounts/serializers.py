from rest_framework import serializers


class OTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class OTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.RegexField(
        regex=r"^\d{6}$",
        error_messages={"invalid": "OTP must be exactly 6 digits."},
    )


class TokenPairSerializer(serializers.Serializer):
    """Response shape only — used for OpenAPI documentation."""

    access = serializers.CharField()
    refresh = serializers.CharField()
