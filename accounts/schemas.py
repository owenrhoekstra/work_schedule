"""Response and request schemas for the accounts app API.

Every Pydantic Schema for this app's /api/v1/ endpoints lives here,
per AGENTS.md. Request schemas and response schemas both go in this
file — one import surface per app.
"""

from ninja import Schema


class CompanySchema(Schema):
    id: str
    name: str
    slug: str
    role: str


class CompaniesResponse(Schema):
    current_company_id: str | None
    companies: list[CompanySchema]


class SelectCompanyRequest(Schema):
    company_id: str


class SelectCompanyResponse(Schema):
    ok: bool
    error: str = ""


class TeamMembershipSchema(Schema):
    id: str
    name: str
    company_id: str
    role: str


class MeResponse(Schema):
    id: str
    first_name: str
    last_name: str
    is_platform_admin: bool
    permissions: list[str]
    current_company_id: str | None
    current_team_id: str | None
    companies: list[CompanySchema]
    teams: list[TeamMembershipSchema]
