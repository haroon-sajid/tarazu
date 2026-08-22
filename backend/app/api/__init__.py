"""HTTP routers for the public `/v1/...` API.

Routers are wiring, not logic: each one validates the request, calls a module
`service.py` (or, until the services land, the fixture repository), and returns
`app/shared/` schema objects. No matching, math, or rule logic lives here.

See [docs/decisions/0001-http-routers-live-in-app-api.md](../../../docs/decisions/0001-http-routers-live-in-app-api.md)
for why these sit at the app layer rather than inside the modules.
"""
