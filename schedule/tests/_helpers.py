"""Test helpers shared across test modules.

`login_as` sets the tenant session alongside the Django session. When
TENANT_ENFORCEMENT activates in commit 4, every view-hitting test
will go through this helper instead of bare `force_login`.
"""


def login_as(client, user, company=None, team=None):
    """Log in a user and optionally set the tenant session.

    `company` / `team` may be model instances or UUID/str PKs. When
    omitted, no tenant session is set — enforcement (if active) will
    redirect to the picker, which is usually not what a test wants.
    """
    client.force_login(user)

    if company is None and team is None:
        return

    session = client.session
    if company is not None:
        session["company_id"] = str(getattr(company, "id", company))
    if team is not None:
        session["team_id"] = str(getattr(team, "id", team))
    session.save()