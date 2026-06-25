# core/rate_limit.py
#
# Shared slowapi Limiter instance.
#
# Usage in route files:
#
#   from fastapi import Request
#   from core.rate_limit import limiter
#
#   @router.post("/login")
#   @limiter.limit("10/minute")
#   async def login(request: Request, body: LoginRequest):
#       ...
#
# The limiter MUST also be attached to the FastAPI app in main.py:
#
#   from core.rate_limit import limiter
#   from slowapi.errors import RateLimitExceeded
#   from slowapi import _rate_limit_exceeded_handler
#
#   app.state.limiter = limiter
#   app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
#
# Key limits applied to auth endpoints:
#   - POST /auth/login           → 10 requests / minute  per IP
#   - POST /auth/register        →  5 requests / minute  per IP
#   - GET  /auth/admin-access    →  5 requests / minute  per IP
#
# These are intentionally conservative.  Legitimate users should never hit
# them during normal use; the limits only bite credential-stuffing scripts
# and brute-force scanners.

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
