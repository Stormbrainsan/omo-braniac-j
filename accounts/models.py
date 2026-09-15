# We use Django's built-in `auth.User` as the identity record created/updated
# on successful OTP verification. See README "Key design decisions" for why
# a custom user model wasn't introduced for this assessment: the only
# identity attribute we need is a normalized, unique email, and
# User.username / User.email already give us that with zero extra
# migrations, admin wiring, or SimpleJWT configuration.
#
# If this went to production with more identity fields (phone, KYC status,
# etc.) we'd swap this for a custom AbstractUser subclass with `email` as
# the USERNAME_FIELD before the first migration ever ran.
