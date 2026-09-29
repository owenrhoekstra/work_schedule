from unittest.mock import patch

from django.core import mail
from django.template import TemplateDoesNotExist
from django.test import SimpleTestCase, override_settings

from accounts.emails import _html_to_text, send_email

_LOCMEM_EMAIL = override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
)


class HtmlToTextTests(SimpleTestCase):
    def test_strips_tags(self):
        html = "<p>Hello <strong>world</strong></p>"
        self.assertEqual(_html_to_text(html).strip(), "Hello world")

    def test_strips_style_block(self):
        html = "<style>body{color:red}</style><p>Hello</p>"
        result = _html_to_text(html)
        self.assertNotIn("color", result)
        self.assertIn("Hello", result)

    def test_strips_script_block(self):
        html = "<script>alert('x')</script><p>Hello</p>"
        self.assertNotIn("alert", _html_to_text(html))

    def test_strips_comments(self):
        html = "<!-- hidden --><p>Visible</p>"
        self.assertNotIn("hidden", _html_to_text(html))
        self.assertIn("Visible", _html_to_text(html))

    def test_block_tags_become_newlines(self):
        html = "<p>One</p><p>Two</p>"
        result = _html_to_text(html)
        self.assertIn("One\n", result)
        self.assertIn("Two", result)

    def test_html_entities_unescaped(self):
        html = "<p>It&#x27;s here</p>"
        self.assertIn("It's here", _html_to_text(html))


@_LOCMEM_EMAIL
class SendEmailTests(SimpleTestCase):
    def test_sends_html_and_plain(self):
        send_email(
            template="emails/otp.html",
            subject="Test",
            context={"code": "123456", "expiry_minutes": 10},
            to="test@example.com",
        )
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.subject, "Test")
        self.assertEqual(msg.to, ["test@example.com"])
        # multipart with text and html
        self.assertEqual(len(msg.alternatives), 1)
        self.assertEqual(msg.alternatives[0][1], "text/html")

    def test_text_only_skips_html_alternative(self):
        send_email(
            template="emails/otp.html",
            subject="Test",
            context={"code": "123456", "expiry_minutes": 10},
            to="test@example.com",
            text_only=True,
        )
        self.assertEqual(len(mail.outbox), 1)
        # A text-only send uses EmailMessage, which has no .alternatives
        self.assertEqual(getattr(mail.outbox[0], "alternatives", []), [])

    def test_uses_txt_sibling_when_present(self):
        send_email(
            template="emails/otp.html",
            subject="Test",
            context={"code": "987654", "expiry_minutes": 5},
            to="test@example.com",
        )
        # Body (text/plain) should come from otp.txt and contain the code
        self.assertIn("987654", mail.outbox[0].body)

    def test_site_url_and_domain_injected(self):
        send_email(
            template="emails/otp.html",
            subject="Test",
            context={"code": "111111", "expiry_minutes": 5},
            to="test@example.com",
        )
        # The txt sibling ends with "site_url" and "@site_domain #code"
        body = mail.outbox[0].body
        self.assertIn("http", body)  # site_url present
        self.assertIn("@", body)  # site_domain present

    def test_string_recipient_coerced_to_list(self):
        send_email(
            template="emails/otp.html",
            subject="Test",
            context={"code": "111111", "expiry_minutes": 5},
            to="solo@example.com",
        )
        self.assertEqual(mail.outbox[0].to, ["solo@example.com"])
