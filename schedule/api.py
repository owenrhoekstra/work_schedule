"""Schedule app API endpoints.

Branch 0: empty router. Feature branches add endpoints here as
features are dual-served. The router is still mounted so the URL
prefix exists and feature branches don't need to touch
`work_schedule/api/urls.py` when they add their first endpoint.
"""

from ninja import Router

router = Router(tags=["schedule"])