"""Send every email template to a recipient for visual review.

Walks the full set of transactional emails the app produces, rendering
each through the real send_email path so what lands in the inbox is
exactly what a recipient would see. Useful for iterating on layout and
copy without triggering the actual business events.

Every template gets a sibling send when a template has meaningfully
different branches (e.g. shift_changed has override, default, and
cycle-change variants).
"""

from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand

from accounts.emails import send_email

# Derive from settings so links in test emails match the environment
# the command is running against (local dev, staging, prod). Strip any
# trailing slash so f-string concatenation never produces "//".
_SITE_URL = settings.SITE_URL.rstrip("/")


class Command(BaseCommand):
    help = "Send every email template to a recipient for visual review."

    def add_arguments(self, parser):
        parser.add_argument(
            "recipient",
            help="Email address to send the test emails to.",
        )
        parser.add_argument(
            "--text-only",
            action="store_true",
            help="Send the plain-text version only (for reviewing .txt siblings).",
        )

    def handle(self, *args, **options):
        recipient = options["recipient"]
        text_only = options["text_only"]
        mode = "plain-text" if text_only else "HTML"
        self.stdout.write(f"Sending {mode} test emails to {recipient}...")

        sends = self._build_sends(recipient)

        for label, template, subject, context in sends:
            send_email(
                template=template,
                subject=self._decorate_subject(subject, text_only),
                context=context,
                to=recipient,
                fail_silently=False,
                text_only=text_only,
            )
            self.stdout.write(self.style.SUCCESS(f"  ✓ {label}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nAll {len(sends)} {mode} emails sent to {recipient}."
            )
        )

    @staticmethod
    def _decorate_subject(subject, text_only):
        """Tag the subject so test emails are easy to spot in an inbox."""
        prefix = "[TEST TXT]" if text_only else "[TEST]"
        return f"{prefix} {subject}"

    @staticmethod
    def _build_sends(recipient):
        """The full set of (label, template, subject, context) tuples.

        Kept as a static method so the list is easy to scan and edit
        without wading through handle().
        """
        return [
            # ----- Onboarding -------------------------------------------
            (
                "welcome (HTML)",
                "emails/welcome.html",
                f"Welcome to {settings.APP_NAME}",
                {
                    "employee_name": "Owen",
                    "employee_email": recipient,
                    "signup_url": f"{_SITE_URL}/accounts/signup/",
                },
            ),
            (
                "account_approved (HTML)",
                "emails/account_approved.html",
                "Your account is ready",
                {
                    "employee_name": "Owen",
                    "login_url": f"{_SITE_URL}/accounts/login/",
                },
            ),
            # ----- Auth -------------------------------------------------
            (
                "otp",
                "emails/otp.html",
                "Your verification code",
                {
                    "code": "482917",
                    "expiry_minutes": 10,
                    "purpose": "Use this to verify your email address",
                },
            ),
            (
                "password_reset",
                "emails/password_reset.html",
                "Reset your password",
                {
                    "username": "owen",
                    "reset_url": f"{_SITE_URL}/accounts/reset/MQ/cb1-abc123/",
                    "expiry_hours": 24,
                },
            ),
            # ----- Schedule changes ------------------------------------
            # Override: single-day change with a label header.
            (
                "shift_changed (override)",
                "emails/shift_changed.html",
                "Your shift on Wednesday, October 1 has changed",
                {
                    "headline": "Your shift on Wednesday, October 1 has changed",
                    "subheadline": "This only affects the day(s) listed below.",
                    "changes": [
                        {
                            "label": "Wednesday, October 1",
                            "old": "9:00 AM – 5:00 PM",
                            "new": "10:00 AM – 6:00 PM",
                        },
                    ],
                    "schedule_url": f"{_SITE_URL}/schedule/home/",
                },
            ),
            # Default: multi-day change to regular hours, no cycle change.
            (
                "shift_changed (default, multi-day)",
                "emails/shift_changed.html",
                "Your regular schedule has changed",
                {
                    "headline": "Your regular hours have changed",
                    "subheadline": (
                        "These changes affect upcoming weeks until further notice."
                    ),
                    "changes": [
                        {
                            "label": "Tuesday",
                            "old": "9:00 AM – 5:00 PM",
                            "new": "OFF",
                        },
                        {
                            "label": "Thursday",
                            "old": "OFF",
                            "new": "1:00 PM – 5:00 PM",
                        },
                        {
                            "label": "Saturday",
                            "old": "10:00 AM – 2:00 PM",
                            "new": "10:00 AM – 4:00 PM",
                        },
                    ],
                    "schedule_url": f"{_SITE_URL}/schedule/home/",
                },
            ),
            # Cycle extended: rotation row plus new-week tables.
            (
                "shift_changed (cycle extended)",
                "emails/shift_changed.html",
                "Your rotation pattern has changed",
                {
                    "headline": "Your rotation pattern has been extended",
                    "subheadline": (
                        "Your schedule now repeats every 3 weeks instead of 2. "
                        "The newly added weeks are shown below."
                    ),
                    "changes": [],
                    "cycle_change": {
                        "old_cycle": 2,
                        "new_cycle": 3,
                        "new_weeks": [
                            {
                                "label": "Week C",
                                "rows": [
                                    {"day": "Monday", "time": "9:00 AM – 5:00 PM"},
                                    {"day": "Tuesday", "time": "9:00 AM – 5:00 PM"},
                                    {"day": "Wednesday", "time": "OFF"},
                                    {"day": "Thursday", "time": "9:00 AM – 5:00 PM"},
                                    {"day": "Friday", "time": "9:00 AM – 5:00 PM"},
                                    {"day": "Saturday", "time": "OFF"},
                                ],
                            },
                        ],
                    },
                    "schedule_url": f"{_SITE_URL}/schedule/home/",
                },
            ),
            # Cycle shortened: rotation row with no new-week tables.
            (
                "shift_changed (cycle shortened)",
                "emails/shift_changed.html",
                "Your rotation pattern has changed",
                {
                    "headline": "Your rotation pattern has been shortened",
                    "subheadline": (
                        "Your schedule now repeats every 2 weeks instead of 3. "
                        "Weeks beyond the new rotation no longer apply."
                    ),
                    "changes": [],
                    "cycle_change": {
                        "old_cycle": 3,
                        "new_cycle": 2,
                        "new_weeks": [],
                    },
                    "schedule_url": f"{_SITE_URL}/schedule/home/",
                },
            ),
            # ----- Offboarding -----------------------------------------
            (
                "deactivation_notice",
                "emails/deactivation_notice.html",
                "A note about your schedule",
                {
                    "employee_name": "Owen",
                    "last_day": date.today() + timedelta(days=14),
                    "reason": (
                        "Thank you for your work — we'll be in touch about next steps."
                    ),
                },
            ),
        ]