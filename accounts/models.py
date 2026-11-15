from django.contrib.auth.models import User
from django.db import models
from django.db.models.functions import UUID7


class OIDCIdentity(models.Model):
    """Link between a Django User and an external OIDC subject.

    One user can have multiple OIDC identities (Zitadel now, Keycloak
    or another IdP later). The (issuer, subject) pair is the canonical
    identity tuple; email is not stored here because it can change at
    the provider without notice.
    """

    id = models.UUIDField(primary_key=True, db_default=UUID7(), editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="oidc_identities"
    )
    issuer = models.CharField(max_length=255)
    subject = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    last_login_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["issuer", "subject"]
        constraints = [
            models.UniqueConstraint(
                fields=["issuer", "subject"], name="unique_oidc_identity"
            )
        ]

    def __str__(self):
        return f"{self.issuer}#{self.subject}"
