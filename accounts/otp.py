import hashlib
import secrets
import time

from django.core.cache import cache

from accounts.emails import send_email

OTP_TTL = 600  # 10 minutes
MAX_VERIFY_ATTEMPTS = 3
SEND_WINDOW = 3600  # 1 hour
SEND_COOLDOWNS = [60, 180, 600]  # seconds; index = send number - 1
MAX_SENDS = 4


def _hash(code):
    return hashlib.sha256(code.encode()).hexdigest()


def _generate():
    return f"{secrets.randbelow(1_000_000):06d}"


def user_email(user):
    """Prefer the Employee's email (management-controlled). Fall back to User."""
    if hasattr(user, "employee") and user.employee and user.employee.email:
        return user.employee.email
    return user.email or None


def mask_email(email):
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked = local[0] + "*"
    else:
        masked = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked}@{domain}"


def send_status(identifier):
    """Returns (can_send, seconds_until_allowed)."""
    count = cache.get(f"otp-send-count:{identifier}", 0)
    last_sent = cache.get(f"otp-last-sent:{identifier}", 0)
    if count == 0:
        return True, 0
    if count >= MAX_SENDS:
        return False, 0
    cooldown = SEND_COOLDOWNS[count - 1]
    elapsed = time.time() - last_sent
    if elapsed >= cooldown:
        return True, 0
    return False, int(cooldown - elapsed) + 1


def _record_send(identifier):
    count_key = f"otp-send-count:{identifier}"
    count = cache.get(count_key, 0)
    if count == 0:
        cache.set(count_key, 1, timeout=SEND_WINDOW)
    else:
        cache.incr(count_key)
    cache.set(f"otp-last-sent:{identifier}", time.time(), timeout=SEND_WINDOW)


def issue_otp(user, purpose="Use this to confirm your password change"):
    email = user_email(user)
    if not email:
        return False
    code = _generate()
    cache.set(f"otp:{user.id}", _hash(code), timeout=OTP_TTL)
    cache.delete(f"otp-attempts:{user.id}")
    _record_send(user.id)
    send_email(...)
    return True


def verify_otp(user, submitted):
    """Returns True if the submitted code matches the stored one."""
    stored = cache.get(f"otp:{user.id}")
    if not stored:
        return False
    return secrets.compare_digest(stored, _hash(submitted.strip()))


def record_failed_attempt(user):
    """Increment attempt counter. Returns remaining attempts before lockout."""
    key = f"otp-attempts:{user.id}"
    attempts = cache.get(key, 0) + 1
    if attempts >= MAX_VERIFY_ATTEMPTS:
        clear(user)
        return 0
    cache.set(key, attempts, timeout=OTP_TTL)
    return MAX_VERIFY_ATTEMPTS - attempts


def clear(user):
    cache.delete(f"otp:{user.id}")
    cache.delete(f"otp-attempts:{user.id}")


SIGNUP_WINDOW = 3600  # 1 hour
SIGNUP_MAX_PER_IP = 5


def check_signup_rate_limit(ip):
    """Return True if this IP is allowed to submit another signup.

    Allows up to SIGNUP_MAX_PER_IP attempts per SIGNUP_WINDOW, keyed by IP.
    """
    if not ip:
        return True  # no IP available, don't block
    key = f"signup-rate:{ip}"
    count = cache.get(key, 0)
    if count >= SIGNUP_MAX_PER_IP:
        return False
    if count == 0:
        cache.set(key, 1, timeout=SIGNUP_WINDOW)
    else:
        cache.incr(key)
    return True


SIGNUP_OTP_PREFIX = "signup-otp"


def _email_identifier(email):
    """Stable, non-reversible identifier for an email address."""
    return hashlib.sha256(email.lower().strip().encode()).hexdigest()[:32]


def issue_signup_otp(email, purpose="Verify your email to finish signing up"):
    ident = _email_identifier(email)
    code = _generate()
    cache.set(f"{SIGNUP_OTP_PREFIX}:{ident}", _hash(code), timeout=OTP_TTL)
    cache.delete(f"{SIGNUP_OTP_PREFIX}-attempts:{ident}")
    _record_send(f"signup:{email}")

    send_email(
        template="emails/otp.html",
        subject="Your verification code",
        context={
            "code": code,
            "expiry_minutes": OTP_TTL // 60,
            "purpose": purpose,
        },
        to=email,
    )
    return True


def verify_signup_otp(email, submitted):
    ident = _email_identifier(email)
    stored = cache.get(f"{SIGNUP_OTP_PREFIX}:{ident}")
    if not stored:
        return False
    return secrets.compare_digest(stored, _hash(submitted.strip()))


def record_failed_signup_attempt(email):
    """Returns remaining attempts, or 0 if invalidated."""
    ident = _email_identifier(email)
    key = f"{SIGNUP_OTP_PREFIX}-attempts:{ident}"
    attempts = cache.get(key, 0) + 1
    if attempts >= MAX_VERIFY_ATTEMPTS:
        clear_signup_otp(email)
        return 0
    cache.set(key, attempts, timeout=OTP_TTL)
    return MAX_VERIFY_ATTEMPTS - attempts


def clear_signup_otp(email):
    ident = _email_identifier(email)
    cache.delete(f"{SIGNUP_OTP_PREFIX}:{ident}")
    cache.delete(f"{SIGNUP_OTP_PREFIX}-attempts:{ident}")
