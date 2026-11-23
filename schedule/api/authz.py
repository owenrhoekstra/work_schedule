from ninja.errors import HttpError


def authorize(request, *perms: str, admin: bool = True):
    """Gate before any DB lookup. Returns the current company.

    admin=False is for read paths: any member holding the perms may
    pass, but the tenant check (company must exist) still applies.
    """
    company = request.company
    if company is None:
        raise HttpError(400, "No company in context.")
    if admin and not getattr(request, "is_company_admin", False):
        raise HttpError(403, "Forbidden.")
    if not all(request.user.has_perm(p) for p in perms):
        raise HttpError(403, "Forbidden.")
    return company
