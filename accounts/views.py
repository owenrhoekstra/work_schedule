import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group, User
from django.contrib.auth.views import PasswordChangeView
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from schedule.models import CompanyMembership, Employee

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

            # A user can be invited to sign up at more than one company
            # with the same email. `Employee.objects.get(...)` used to
            # raise MultipleObjectsReturned here. `.filter().first()`
            # attaches the signup to the earliest-hired matching
            # Employee (Meta.ordering is start_date). Log so ops can
            # see it; if multi-company signup becomes common, add a
            # "which company?" picker before OTP issuance.
            candidates = list(
                Employee.objects.filter(
                    email__iexact=email, is_active=True, user__isnull=True
                ).order_by("start_date")
            )
            if not candidates:
                # clean_email guaranteed one existed; this is defense
                # against a mid-flight deletion between validation and
                # this block.
                form.add_error(None, "No active invitation found.")
                return render(
                    request,
                    "registration/signup.html",
                    {"form": form},
                )
            if len(candidates) > 1:
                logger.warning(
                    "Signup ambiguity: %d active unlinked employees for "
                    "%s; attaching to employee %s",
                    len(candidates),
                    email,
                    candidates[0].pk,
                )
            employee = candidates[0]

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


def _pending_signup_eligible(pending):
    """Recheck a pending_signup session's eligibility (SEC-006 finding #1).

    Employee email, active status, or user link may have changed since
    signup was initiated. Called before issuing replacement OTP codes;
    final account creation does the authoritative check with a
    select_for_update row lock.
    """
    try:
        employee = Employee.objects.get(pk=pending["employee_id"])
    except Employee.DoesNotExist:
        return False
    return (
        employee.email.lower() == pending["email"].lower()
        and employee.is_active
        and employee.user_id is None
    )


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
            # Reject stale sessions before issuing a replacement code —
            # management may have changed the employee's email or
            # deactivated them since the signup started (SEC-006 #1).
            if not _pending_signup_eligible(pending):
                request.session.pop("pending_signup", None)
                messages.error(
                    request,
                    "Your enrollment has changed. Please start again.",
                )
                return redirect("signup")

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
            # Success — create the User and link to the Employee.
            # Reload the employee under a row lock and revalidate
            # eligibility before attaching. Rejects stale sessions:
            # management may have changed the email or deactivated the
            # employee between signup start and OTP verification
            # (SEC-006 finding #1).
            with transaction.atomic():
                try:
                    employee = Employee.objects.select_for_update().get(
                        pk=pending["employee_id"]
                    )
                except Employee.DoesNotExist:
                    employee = None

                if employee is not None and employee.user_id is not None:
                    otp_service.clear_signup_otp(email)
                    request.session.pop("pending_signup", None)
                    messages.error(
                        request,
                        "This account has already been completed. Try logging in.",
                    )
                    return redirect("login")

                if (
                    employee is None
                    or employee.email.lower() != email.lower()
                    or not employee.is_active
                ):
                    otp_service.clear_signup_otp(email)
                    request.session.pop("pending_signup", None)
                    messages.error(
                        request,
                        "Your enrollment has changed. Please contact management.",
                    )
                    return redirect("signup")

                user = User(
                    username=pending["username"],
                    email=email,
                    password=pending["password_hash"],
                    first_name=employee.first_name,
                    last_name=employee.last_name,
                    is_active=True,
                )
                user.save()
                employee.user = user
                employee.save(update_fields=["user"])

                # Password signup creates a pending membership just like
                # OIDC first-login does. approve_account activates it.
                # Without this, the user's account exists but no company
                # access is ever granted — they'd land on /accounts/
                # waiting/ after approval instead of their schedule.

                CompanyMembership.objects.get_or_create(
                    user=user,
                    company=employee.company,
                    defaults={"role": "member", "status": "pending"},
                )

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


def _pending_memberships(request):
    """Pending CompanyMemberships at the current company, oldest first.

    Filters by request.company so each company's managers see only
    their own queue. Order by created_at ascending so new signups land
    at the top of the list — the manager's oldest tasks are at the
    bottom, newest at the top.

    Returns CompanyMembership objects (not Users), so the template can
    iterate and display both the user's identity and the pending-role
    context. The User is accessible via `.user` on each membership.
    """
    from schedule.models import CompanyMembership

    company = getattr(request, "company", None)
    if company is None:
        return CompanyMembership.objects.none()

    return (
        CompanyMembership.objects.filter(company=company, status="pending")
        .select_related("user")
        .order_by("-created_at")
    )


@login_required
@permission_required("auth.change_user", raise_exception=True)
def pending_accounts(request):
    return render(
        request,
        "pending_accounts.html",
        {"pending": _pending_memberships(request)},
    )


from schedule import notifications


@login_required
@permission_required("auth.change_user", raise_exception=True)
def approve_account(request, user_id):
    """Approve a pending account at the current company.

    Activates the CompanyMembership(user_id, request.company, status=
    "pending") if one exists. Also activates the User account if it's
    still inactive — new password-signup users start inactive until a
    manager approves, and OIDC signups start active but their
    membership is pending. Both gates clear here.

    Approves at the current company only. A user with pending
    memberships at two companies needs each company's manager to
    approve independently — that's the intended semantics: employment
    at one workplace doesn't grant access at another.
    """
    if request.method != "POST":
        return redirect("pending_accounts")

    from django.db import transaction

    from schedule.models import CompanyMembership

    company = getattr(request, "company", None)
    if company is None:
        messages.error(request, "No company context for this approval.")
        return redirect("pending_accounts")

    user = get_object_or_404(User, id=user_id)
    membership = CompanyMembership.objects.filter(
        user=user, company=company, status="pending"
    ).first()
    if membership is None:
        messages.error(
            request,
            f"No pending membership for {user.username} at this company.",
        )
        return redirect("pending_accounts")

    with transaction.atomic():
        membership.status = CompanyMembership.STATUS_ACTIVE
        membership.save(update_fields=["status"])

        # User.is_active is always True by this point (OIDC and
        # password signup both create active accounts). The access
        # gate is CompanyMembership.status, not the account flag.
        # Nothing to flip here.

        staff_group, _ = Group.objects.get_or_create(name="Staff")
        user.groups.add(staff_group)

    if request.POST.get("notify"):
        employee = user.employees.filter(company=company).first()
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
    # Scope to the current company. A user employed at two companies
    # has one Employee per company; editing their profile while working
    # at Company B must not touch Company A's Employee record.
    #
    # request.company is set by TenantMiddleware for every authed
    # request (including exempt paths like /accounts/profile/). It's
    # None if the user has 0 or 2+ viable companies with no session
    # choice — in that case `employee` is None and profile edits touch
    # the shared User only, which is the correct fallback.
    employee = request.user.employees.filter(company=request.company).first()

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


@login_required
def company_picker(request):
    """Pick a company to work in.

    Shows active memberships only. Pending memberships stay hidden
    (they go through the acceptance flow, not the picker). Users with
    exactly one membership are auto-selected and redirected — that
    path fires from TenantMiddleware's auto-resolution, but this view
    keeps the same behavior as a safety net.
    """
    from work_schedule.auth import viable_memberships

    memberships = sorted(
        viable_memberships(request.user),
        key=lambda m: m.company.name,
    )

    if not memberships:
        return redirect("waiting")

    if len(memberships) == 1:
        request.session["company_id"] = str(memberships[0].company_id)
        return redirect("home")

    if request.method == "POST":
        company_id = request.POST.get("company_id", "").strip()
        if any(str(m.company_id) == company_id for m in memberships):
            request.session["company_id"] = company_id
            return redirect("home")
        messages.error(request, "Please choose a company.")

    return render(
        request,
        "registration/company_picker.html",
        {"memberships": memberships},
    )


@login_required
def waiting(request):
    """Landing page for authed users with no active company membership.

    Typically reached when a signup hasn't been approved yet, or when
    a membership was revoked. Message points at the manager so the
    user knows who to ask.
    """
    return render(request, "registration/waiting.html")


def login_spa(request):
    """Render the Vue login shell.

    Config for the Vue app is injected via window.__LOGIN_CONFIG__
    in the template — no round-trip for oidc_enabled, no separate
    status endpoint.
    """
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    return render(
        request,
        "registration/login_spa.html",
        {"oidc_enabled": settings.OIDC_ENABLED},
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
        except (TypeError, ValueError):
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
