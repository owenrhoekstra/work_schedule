import re
from html import unescape
from urllib.parse import urlparse

from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils.html import strip_tags

_BLOCK_TAGS = r"br|p|div|h1|h2|h3|h4|h5|h6|tr|li|table|blockquote|hr"


def _html_to_text(html):
    """Convert HTML to a reasonable plain-text approximation.

    Strips style/script blocks entirely (their content would otherwise
    appear as visible text), inserts newlines for block-level tags, then
    collapses runs of blank lines.
    """
    # Remove <style> and <script> blocks including their contents
    text = re.sub(
        r"<(style|script)[^>]*>.*?</\1>",
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Remove HTML comments
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # Insert newlines for block-level tags
    text = re.sub(rf"</?({_BLOCK_TAGS})[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = strip_tags(text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def send_email(
    *,
    template,
    subject,
    context,
    to,
    from_email=None,
    fail_silently=False,
    text_only=False,
):
    """Render and send an email.

    Sends multipart/alternative with HTML + text/plain by default.
    When `text_only=True` or `settings.EMAIL_HTML_ENABLED` is False,
    sends plain text only.

    EMAIL_HTML_ENABLED is derived from DEBUG in settings.py: dev sends
    plaintext only (the console backend dumps raw MIME to the terminal
    and HTML parts there are unreadable noise); staging and prod send
    both parts. Override via the EMAIL_HTML_ENABLED env var if you need
    HTML output in dev to check rendering before pushing.

    Every email gets three context values injected automatically:

    - `app_name` — the branded name from settings.APP_NAME
    - `site_url` — the base URL of the site
    - `site_domain` — the domain part of site_url

    Caller-supplied context wins on collision, so a specific email can
    override any of these if it ever needs to.
    """
    if isinstance(to, str):
        to = [to]

    parsed = urlparse(settings.SITE_URL)
    context = {
        "app_name": settings.APP_NAME,
        "site_url": settings.SITE_URL,
        "site_domain": parsed.netloc,
        **context,
    }

    # Force text-only when HTML is disabled globally (dev). Explicit
    # `text_only=True` also forces it, regardless of setting.
    send_html = not text_only and getattr(settings, "EMAIL_HTML_ENABLED", True)

    text_template = template.rsplit(".", 1)[0] + ".txt"
    html_body = None
    try:
        text_body = render_to_string(text_template, context)
    except TemplateDoesNotExist:
        # No .txt sibling — derive text from the HTML. Renders HTML
        # regardless of send_html because we need the content.
        html_body = render_to_string(template, context)
        text_body = _html_to_text(html_body)

    from_addr = from_email or settings.DEFAULT_FROM_EMAIL

    if not send_html:
        msg = EmailMessage(
            subject=subject,
            body=text_body,
            from_email=from_addr,
            to=to,
        )
    else:
        if html_body is None:
            html_body = render_to_string(template, context)
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=from_addr,
            to=to,
        )
        msg.attach_alternative(html_body, "text/html")

    msg.send(fail_silently=fail_silently)
