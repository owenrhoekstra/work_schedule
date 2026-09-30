import logging

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from accounts.emails import send_email

logger = logging.getLogger(__name__)


def _cooldown_ok(key, seconds=60):
    """Return True if allowed to send now, False if on cooldown.

    Sets the cooldown key when returning True, so callers don't need to.
    """
    if cache.get(key):
        return False
    cache.set(key, 1, timeout=seconds)
    return True


def _check_email_eligibility(employee):
    """Return (eligible, reason).

    An employee is eligible to receive schedule-related emails when:
    - They have a linked User account (they've signed up).
    - The User is active (approved, not deactivated).
    - They're currently on the schedule (last_day is null or in the future).

    reason is a short phrase describing why they're ineligible, or None if
    they are eligible. Callers include it in their return message.
    """
    if not employee.user_id:
        return False, "employee hasn't signed up yet"
    if not employee.user.is_active:
        return False, "employee's account is inactive"
    today = timezone.localdate()
    if employee.last_day and employee.last_day < today:
        return False, "employee is no longer on the schedule"
    return True, None


def _signup_url():
    return f"{settings.SITE_URL}/accounts/signup/"


def _login_url():
    return f"{settings.SITE_URL}/accounts/login/"


def _schedule_url():
    return f"{settings.SITE_URL}/schedule/home/"


def _try_send(**kwargs):
    """Wrap send_email so failures return a message instead of raising.

    The caller's action should still succeed when the email fails.
    """
    try:
        send_email(**kwargs)
    except Exception:
        logger.exception("Failed to send email: %s", kwargs.get("template"))
        return False, "Could not send email. Please try again."
    return True, None


# ---------------------------------------------------------------------------
# Welcome — exempt from eligibility (invites a non-user)
# ---------------------------------------------------------------------------


def send_welcome_email(employee):
    """Send the welcome email. Rate-limited per employee (60s).

    Exempt from eligibility checks — this email's purpose is to invite
    someone who hasn't signed up yet.
    """
    if not _cooldown_ok(f"welcome-sent:{employee.id}"):
        return False, "Please wait a minute before sending again."

    return _try_send(
        template="emails/welcome.html",
        subject="Welcome to Work Schedule",
        context={
            "employee_name": employee.first_name,
            "employee_email": employee.email,
            "signup_url": _signup_url(),
        },
        to=employee.email,
    )


# ---------------------------------------------------------------------------
# Account approved — gated on employee eligibility
# ---------------------------------------------------------------------------


def send_account_approved_email(user, employee):
    """Send the account-approved email. Rate-limited per user (60s)."""
    to = employee.email if employee else user.email
    if not to:
        return False, "No email address on file."

    if employee:
        eligible, reason = _check_email_eligibility(employee)
        if not eligible:
            return False, f"No email sent — {reason}."

    if not _cooldown_ok(f"approved-sent:{user.id}"):
        return False, "Please wait a minute before sending again."

    return _try_send(
        template="emails/account_approved.html",
        subject="Your account is ready",
        context={
            "employee_name": employee.first_name if employee else None,
            "login_url": _login_url(),
        },
        to=to,
    )


# ---------------------------------------------------------------------------
# Shift changes — gated on employee eligibility
# ---------------------------------------------------------------------------


def send_shift_changes_email(employee, changes, *, kind, cycle_change=None):
    """Send a schedule-change notification.

    `changes` is a list of dicts:
        label — human label ("Wednesday, October 1" or "Monday")
        old   — previous display string ("9:00 AM – 5:00 PM" or "OFF")
        new   — new display string

    `kind` is "override" or "default".

    `cycle_change` is None, or a dict:
        old_cycle — previous cycle length in weeks
        new_cycle — new cycle length
        new_weeks — list of dicts, one per newly-active week
    """
    if not changes and not cycle_change:
        return False, "No changes to notify."

    eligible, reason = _check_email_eligibility(employee)
    if not eligible:
        return False, f"No email sent — {reason}."

    if cycle_change:
        subject = "Your rotation pattern has changed"
        if cycle_change["new_cycle"] > cycle_change["old_cycle"]:
            headline = "Your rotation pattern has been extended"
        else:
            headline = "Your rotation pattern has been shortened"

        if changes:
            subheadline = (
                f"Your schedule now repeats every {cycle_change['new_cycle']} "
                f"weeks instead of {cycle_change['old_cycle']}, along with the "
                f"other changes listed below."
            )
        elif cycle_change["new_cycle"] > cycle_change["old_cycle"]:
            subheadline = (
                f"Your schedule now repeats every {cycle_change['new_cycle']} "
                f"weeks instead of {cycle_change['old_cycle']}. The newly added "
                f"weeks are shown below."
            )
        else:
            subheadline = (
                f"Your schedule now repeats every {cycle_change['new_cycle']} "
                f"weeks instead of {cycle_change['old_cycle']}. Weeks beyond "
                f"the new rotation no longer apply."
            )
    else:
        if kind == "override":
            if len(changes) == 1:
                headline = f"Your shift on {changes[0]['label']} has changed"
            else:
                headline = "Your shift schedule has changed"
            subject = "Your shift has changed"
            subheadline = "This only affects the day(s) listed below."
        else:
            headline = "Your regular hours have changed"
            subject = "Your regular schedule has changed"
            subheadline = "These changes affect upcoming weeks until further notice."

    return _try_send(
        template="emails/shift_changed.html",
        subject=subject,
        context={
            "headline": headline,
            "subheadline": subheadline,
            "changes": changes or [],
            "cycle_change": cycle_change,
            "schedule_url": _schedule_url(),
        },
        to=employee.email,
    )


# ---------------------------------------------------------------------------
# Deactivation — gated on employee eligibility
# ---------------------------------------------------------------------------


def send_deactivation_email(employee, reason=None):
    """Send the deactivation notice.

    Only sent while the employee is still on the schedule. If the
    deactivation is immediate (last_day in the past), they're already
    gone — no point telling them it's coming.
    """
    eligible, eligibility_reason = _check_email_eligibility(employee)
    if not eligible:
        return False, f"No email sent — {eligibility_reason}."

    return _try_send(
        template="emails/deactivation_notice.html",
        subject="A note about your schedule",
        context={
            "employee_name": employee.first_name,
            "last_day": employee.last_day,
            "reason": reason,
        },
        to=employee.email,
    )
