"""Response and request schemas for the accounts app API.

Every Pydantic Schema for this app's /api/v1/ endpoints lives here,
per AGENTS.md. Request schemas and response schemas both go in this
file — one import surface per app.
"""

from ninja import Schema

from work_schedule.auth import is_company_admin, is_team_admin


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


class SelectTeamRequest(Schema):
    # None or "" clears the selection (all-teams view). A UUID string
    # narrows scope=team to that one team.
    team_id: str | None = None


class SelectTeamResponse(Schema):
    ok: bool
    error: str = ""


class TeamMembershipSchema(Schema):
    id: str
    name: str
    company_id: str
    role: str

class CompanyAdminMe(Schema):
    status: bool
    company_id: str

class TeamAdminMe(Schema):
    status: bool
    company_id: str
    team_id: str


class MeResponse(Schema):
    id: str
    first_name: str
    last_name: str
    is_platform_admin: bool
    is_company_admin: list[CompanyAdminMe]
    is_team_admin: list[TeamAdminMe]
    permissions: list[str]
    current_company_id: str | None
    current_team_id: str | None
    companies: list[CompanySchema]
    teams: list[TeamMembershipSchema]
    available_scopes: list[str]
