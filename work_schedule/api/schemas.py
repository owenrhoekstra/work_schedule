"""Project-level API schemas.

Smoke endpoint schema lives here for now. Any future project-wide
schemas (health, version, feature flags) belong in this file rather
than scattered across individual api.py modules.
"""

from ninja import Schema


class MeSchema(Schema):
    id: int
    email: str
    is_staff: bool