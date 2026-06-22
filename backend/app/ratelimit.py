"""Shared rate limiter instance for slowapi.

Imported by main.py (to register on app.state) and by route modules
(auth.py, admin.py) to apply @limiter.limit decorators. Keeping the
limiter in its own module avoids circular imports (main.py imports
routers, routers need the limiter).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
