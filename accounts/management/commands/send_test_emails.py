from datetime import date, timedelta

from django.core.management.base import BaseCommand

from accounts.emails import send_email


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

        sends = [
            (
                "welcome",
                "emails/welcome.html",
                "[TEST TXT] Welcome to Work Schedule",
                {
                    "employee_name": "Owen",
                    "employee_email": recipient,
                    "signup_url": "https://work-schedule.principiasystems.ca/accounts/signup/",
                },
            ),
            (
                "account_approved",
                "emails/account_approved.html",
                "[TEST TXT] Your account is ready",
                {
                    "employee_name": "Owen",
                    "login_url": "https://work-schedule.principiasystems.ca/accounts/login/",
                },
            ),
            (
                "otp",
                "emails/otp.html",
                "[TEST TXT] Your verification code",
                {
                    "code": "482917",
                    "expiry_minutes": 10,
                    "purpose": "Use this to verify your email address",
                },
            ),
            (
                "password_reset",
                "emails/password_reset.html",
                "[TEST TXT] Reset your password",
                {
                    "username": "owen",
                    "reset_url": "https://work-schedule.principiasystems.ca/accounts/reset/MQ/cb1-abc123/",
                    "expiry_hours": 24,
                },
            ),
            (
                "shift_changed (override)",
                "emails/shift_changed.html",
                "[TEST TXT] Your shift on Wednesday, October 1 has changed",
                {
                    "headline": "Your shift on Wednesday, October 1 has changed",
                    "subheadline": "This only affects that one day.",
                    "old_display": "9:00 AM – 5:00 PM",
                    "new_display": "10:00 AM – 6:00 PM",
                    "schedule_url": "https://work-schedule.principiasystems.ca/schedule/home/",
                },
            ),
            (
                "shift_changed (default)",
                "emails/shift_changed.html",
                "[TEST TXT] Your regular Tuesday hours have changed",
                {
                    "headline": "Your regular Tuesday hours have changed",
                    "subheadline": "This affects every upcoming week until it's changed again.",
                    "old_display": "9:00 AM – 5:00 PM",
                    "new_display": "OFF",
                    "schedule_url": "https://work-schedule.principiasystems.ca/schedule/home/",
                },
            ),
            (
                "deactivation_notice",
                "emails/deactivation_notice.html",
                "[TEST TXT] Your last day on schedule",
                {
                    "employee_name": "Owen",
                    "last_day": date.today() + timedelta(days=14),
                    "reason": "Thank you for your work — we'll be in touch about next steps.",
                },
            ),
        ]

        for label, template, subject, context in sends:
            send_email(
                template=template,
                subject=subject,
                context=context,
                to=recipient,
                fail_silently=False,
                text_only=text_only,
            )
            self.stdout.write(self.style.SUCCESS(f"  ✓ {label}"))

        self.stdout.write(
            self.style.SUCCESS(f"\nAll {len(sends)} {mode} emails sent to {recipient}.")
        )
