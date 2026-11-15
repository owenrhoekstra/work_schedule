import logging

from django.contrib.auth.models import User
from django.db import transaction
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

logger = logging.getLogger(__name__)


class DocketOIDCBackend(OIDCAuthenticationBackend):
    """OIDC backend for Docket.

    Resolution order:
      1. Existing OIDCIdentity for (issuer, sub) → that user.
      2. Existing User with matching email (case-insensitive). Attach
         an OIDCIdentity to the user for this issuer.
      3. No User, but an active Employee with matching email and no
         linked user → create the User (inactive), link to the
         Employee, create a pending CompanyMembership, attach the
         OIDCIdentity.
      4. Otherwise → refuse. OIDC login is invite-only, matching
         password signup.
    """

    def filter_users_by_claims(self, claims):
        from accounts.models import OIDCIdentity

        issuer = claims.get("iss")
        subject = claims.get("sub")
        if issuer and subject:
            identity = (
                OIDCIdentity.objects.filter(issuer=issuer, subject=subject)
                .select_related("user")
                .first()
            )
            if identity:
                return User.objects.filter(pk=identity.user_id)

        email = claims.get("email")
        if email:
            return User.objects.filter(email__iexact=email)
        return User.objects.none()

    def create_user(self, claims):
        from accounts.models import OIDCIdentity
        from schedule.models import CompanyMembership, Employee

        email = claims.get("email")
        if not email:
            logger.warning("OIDC login rejected: no email claim")
            return None

        employee = (
            Employee.objects.filter(
                email__iexact=email, user__isnull=True, is_active=True
            )
            .select_related("company")
            .first()
        )
        if employee is None:
            logger.warning(
                "OIDC login rejected: no active unlinked employee for %s",
                email,
            )
            return None

        with transaction.atomic():
            user = User.objects.create_user(
                username=self._unique_username(email),
                email=email,
                is_active=True,
            )
            user.first_name = claims.get("given_name", "") or ""
            user.last_name = claims.get("family_name", "") or ""
            user.save(update_fields=["first_name", "last_name"])

            employee.user = user
            employee.save(update_fields=["user"])

            CompanyMembership.objects.create(
                user=user,
                company=employee.company,
                role="member",
                status="pending",
            )

            OIDCIdentity.objects.create(
                user=user, issuer=claims["iss"], subject=claims["sub"]
            )

        return user

    def update_user(self, user, claims):
        """Sync name from claims and ensure the OIDCIdentity exists.

        Called by the library after either an identity match or an
        email-claim match. On the first email-claim login, no
        OIDCIdentity row exists yet — create it here so subsequent
        logins take the fast path through `filter_users_by_claims`.
        On identity-match logins, only refresh `last_login_at`.
        """
        from django.utils import timezone

        from accounts.models import OIDCIdentity

        user.first_name = claims.get("given_name", "") or user.first_name
        user.last_name = claims.get("family_name", "") or user.last_name
        user.save(update_fields=["first_name", "last_name"])

        issuer = claims.get("iss")
        subject = claims.get("sub")
        if issuer and subject:
            identity, created = OIDCIdentity.objects.get_or_create(
                issuer=issuer,
                subject=subject,
                defaults={"user": user},
            )
            if not created and identity.user_id != user.pk:
                # Unreachable in practice (filter_users_by_claims would
                # have returned the identity's owner), but if the
                # (issuer, subject) tuple is somehow attached to
                # another user, refuse to silently rebind it.
                logger.warning(
                    "OIDC identity collision: %s#%s is attached to %s "
                    "but login resolved to %s",
                    issuer,
                    subject,
                    identity.user_id,
                    user.pk,
                )
                return user
            identity.last_login_at = timezone.now()
            identity.save(update_fields=["last_login_at"])

        return user

    def _unique_username(self, email):
        base = (email.split("@")[0] or "user")[:100]
        candidate = base
        suffix = 1
        while User.objects.filter(username=candidate).exists():
            suffix += 1
            candidate = f"{base}{suffix}"
        return candidate

    def get_or_create_user(self, access_token, id_token, payload):
        """Ensure `iss` and `sub` are on `user_info` before the rest of
        the flow runs.

        Zitadel's userinfo endpoint (OIDC_OP_USER_ENDPOINT) returns
        `sub`, `email`, `given_name`, etc., but NOT `iss`. Per OIDC
        spec `iss` is only required in the id_token, and Zitadel
        omits it from userinfo.

        `filter_users_by_claims` needs `iss` to look up an existing
        OIDCIdentity, and `update_user` needs it to persist the
        identity on first login. Without this merge, both fall
        through to email-only matching every login and no identity
        row is ever created — invisible to the test suite because
        tests mock `get_userinfo` to return a full claim dict.
        """
        user_info = self.get_userinfo(access_token, id_token, payload)
        if user_info is None:
            return None

        if isinstance(user_info, dict):
            if "iss" not in user_info and "iss" in payload:
                user_info["iss"] = payload["iss"]
            if "sub" not in user_info and "sub" in payload:
                user_info["sub"] = payload["sub"]

        claims_verified = self.verify_claims(user_info)
        if not claims_verified:
            return None

        users = self.filter_users_by_claims(user_info)
        if len(users) == 1:
            return self.update_user(users[0], user_info)
        elif len(users) > 1:
            return None

        return self.create_user(user_info)
