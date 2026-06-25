"""Vercel Python entrypoint.

Vercel's @vercel/python runtime serves the ASGI ``app`` exported here. The whole
FastAPI app (pages, static, API) is routed through this single function.
"""

import os
import sys

# Make the repo root importable so `import app...` works on Vercel.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402,F401
