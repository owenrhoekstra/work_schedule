import logging
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group, User
from django.contrib.auth.views import PasswordChangeView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from schedule.models import Employee

from . import otp as otp_service
from .forms import ProfileForm, SignUpForm, StyledPasswordChangeForm

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Best-effort client IP behind Cloudflare Tunnel."""
    cf = request.META.get("HTTP_CF_CONNECTING_IP")
    if cf:
        return cf.strip()
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def signup(request):
    if request.method == "POST":
        ip = get_client_ip(request)
        if not otp_service.check_signup_rate_limit(ip):
            return render(
                request,
                "registration/signup.html",
                {"form": SignUpForm(), "rate_limited": True},
            )

        form = SignUpForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            employee = Employee.objects.get(
                email__iexact=email, is_active=True, user__isnull=True
            )

            # Stash pending signup in the session — nothing is created until
            # the OTP is verified.
            request.session["pending_signup"] = {
                "username": form.cleaned_data["username"],
                "email": email,
                "password_hash": make_password(form.cleaned_data["password1"]),
                "employee_id": str(employee.id),
            }

            otp_service.issue_signup_otp(email)
            return redirect("verify_signup_otp")
    else:
        form = SignUpForm()
    return render(request, "registration/signup.html", {"form": form})


def verify_signup_otp(request):
    pending = request.session.get("pending_signup")
    if not pending:
        messages.error(
            request,
            "Your signup session has expired. Please start again.",
        )
        return redirect("signup")

    email = pending["email"]

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "resend":
            # Rate-limit resends per email
            can_send, wait = otp_service.send_status(f"signup:{email}")
            if can_send:
                otp_service.issue_signup_otp(email)
                messages.success(request, "A new code has been sent.")
            elif wait > 0:
                messages.warning(
                    request,
                    f"Please wait {wait} seconds before requesting another code.",
                )
            else:
                messages.error(request, "Too many requests. Try again later.")
            return redirect("verify_signup_otp")

        code = (request.POST.get("code") or "").strip()
        if not code:
            messages.error(request, "Enter the code from your email.")
            return render(
                request,
                "registration/signup_verify_otp.html",
                {"masked_email": otp_service.mask_email(email)},
            )

        if otp_service.verify_signup_otp(email, code):
            # Success — create the User and link to the Employee
            employee = Employee.objects.get(pk=pending["employee_id"])

            # Guard: another session may have completed first
            if employee.user_id is not None:
                messages.error(
                    request,
                    "This account has already been completed. Try logging in.",
                )
                request.session.pop("pending_signup", None)
                return redirect("login")

            user = User(
                username=pending["username"],
                email=email,
                password=pending["password_hash"],
                first_name=employee.first_name,
                last_name=employee.last_name,
                is_active=False,
            )
            user.save()
            employee.user = user
            employee.save(update_fields=["user"])

            otp_service.clear_signup_otp(email)
            request.session.pop("pending_signup", None)
            return render(request, "registration/signup_pending.html")

        remaining = otp_service.record_failed_signup_attempt(email)
        if remaining == 0:
            messages.error(
                request,
                "Too many incorrect codes. Request a new one to continue.",
            )
            # Still on the page; the user can hit "Send a new code"
        else:
            plural = "s" if remaining != 1 else ""
            messages.error(
                request,
                f"Incorrect code. {remaining} attempt{plural} remaining.",
            )
        return render(
            request,
            "registration/signup_verify_otp.html",
            {"masked_email": otp_service.mask_email(email)},
        )

    return render(
        request,
        "registration/signup_verify_otp.html",
        {"masked_email": otp_service.mask_email(email)},
    )


def _pending_users():
    return User.objects.filter(is_active=False, employee__is_active=True)


@login_required
@permission_required("auth.change_user", raise_exception=True)
def pending_accounts(request):
    return render(request, "pending_accounts.html", {"pending": _pending_users()})


from schedule import notifications


@login_required
@permission_required("auth.change_user", raise_exception=True)
def approve_account(request, user_id):
    if request.method == "POST":
        user = get_object_or_404(User, id=user_id)
        user.is_active = True
        user.save()
        staff_group, _ = Group.objects.get_or_create(name="Staff")
        user.groups.add(staff_group)

        if request.POST.get("notify"):
            employee = getattr(user, "employee", None)
            ok, error = notifications.send_account_approved_email(user, employee)
            if ok:
                messages.success(request, f"Approved and notified {user.username}.")
            else:
                messages.warning(request, f"Approved, but email failed: {error}")
        else:
            messages.success(request, f"Approved {user.username}.")
    return redirect("pending_accounts")


@login_required
def profile(request):
    employee = getattr(request.user, "employee", None)

    if request.method == "POST":
        form = ProfileForm(request.POST, user=request.user, employee=employee)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("profile")
    else:
        form = ProfileForm(user=request.user, employee=employee)

    return render(
        request,
        "registration/profile.html",
        {"form": form, "employee": employee},
    )


def _safe_next(request):
    """Return a validated `next` URL, or fall back to profile."""
    candidate = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if candidate and url_has_allowed_host_and_scheme(
        url=candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return reverse("profile")


@login_required
def verify_otp(request):
    user = request.user
    next_url = _safe_next(request)
    email = otp_service.user_email(user)

    if not email:
        messages.error(
            request,
            "No email address is on file for your account. "
            "Contact a manager to update it.",
        )
        return redirect("profile")

    # POST — either a resend request or a code verification
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "resend":
            can_send, wait = otp_service.send_status(user.id)
            if can_send:
                if otp_service.issue_otp(user):
                    messages.success(request, "A new code has been sent.")
                else:
                    messages.error(request, "Couldn't send the code. Try again later.")
            elif wait > 0:
                messages.warning(
                    request,
                    f"Please wait {wait} seconds before requesting another code.",
                )
            else:
                messages.error(
                    request,
                    "Too many requests. Please try again later.",
                )
            return redirect(f"{reverse('verify_otp')}?next={next_url}")

        # Otherwise — verify the submitted code
        code = (request.POST.get("code") or "").strip()
        if not code:
            messages.error(request, "Enter the code from your email.")
            return render(
                request,
                "registration/verify_otp.html",
                {"next": next_url, "masked_email": otp_service.mask_email(email)},
            )

        if otp_service.verify_otp(user, code):
            request.session["otp_verified_at"] = timezone.now().isoformat()
            otp_service.clear(user)
            return redirect(next_url)

        remaining = otp_service.record_failed_attempt(user)
        if remaining == 0:
            messages.error(
                request,
                "Too many incorrect codes. Request a new one to continue.",
            )
        else:
            plural = "s" if remaining != 1 else ""
            messages.error(
                request,
                f"Incorrect code. {remaining} attempt{plural} remaining.",
            )
        return render(
            request,
            "registration/verify_otp.html",
            {"next": next_url, "masked_email": otp_service.mask_email(email)},
        )

    # GET — issue an OTP if none is live
    if not otp_service.cache.get(f"otp:{user.id}"):
        can_send, wait = otp_service.send_status(user.id)
        if can_send:
            otp_service.issue_otp(user)
            messages.info(request, "We've emailed you a verification code.")
        elif wait > 0:
            messages.warning(
                request,
                f"Please wait {wait} seconds before requesting another code.",
            )
        else:
            messages.error(request, "Too many requests. Please try again later.")

    return render(
        request,
        "registration/verify_otp.html",
        {"next": next_url, "masked_email": otp_service.mask_email(email)},
    )


class OTPGatedPasswordChangeView(PasswordChangeView):
    """Requires a recent OTP verification before allowing a password change."""

    form_class = StyledPasswordChangeForm
    template_name = "registration/password_change_form.html"
    success_url = reverse_lazy("password_change_done")

    VERIFICATION_TTL = timedelta(minutes=5)

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not self._recently_verified(request):
            verify_url = reverse("verify_otp")
            return redirect(f"{verify_url}?next={request.path}")
        return super().dispatch(request, *args, **kwargs)

    def _recently_verified(self, request):
        raw = request.session.get("otp_verified_at")
        if not raw:
            return False
        try:
            ts = datetime.fromisoformat(raw)
        except TypeError, ValueError:
            return False
        if timezone.is_naive(ts):
            ts = timezone.make_aware(ts)
        if timezone.now() - ts > self.VERIFICATION_TTL:
            request.session.pop("otp_verified_at", None)
            return False
        return True

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.session.pop("otp_verified_at", None)
        return response
