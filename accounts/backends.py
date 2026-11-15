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
                is_active=False,
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
        from django.utils import timezone

        from accounts.models import OIDCIdentity

        user.first_name = claims.get("given_name", "") or user.first_name
        user.last_name = claims.get("family_name", "") or user.last_name
        user.save(update_fields=["first_name", "last_name"])

        OIDCIdentity.objects.filter(
            user=user, issuer=claims.get("iss"), subject=claims.get("sub")
        ).update(last_login_at=timezone.now())

        return user

    def _unique_username(self, email):
        base = (email.split("@")[0] or "user")[:100]
        candidate = base
        suffix = 1
        while User.objects.filter(username=candidate).exists():
            suffix += 1
            candidate = f"{base}{suffix}"
        return candidate