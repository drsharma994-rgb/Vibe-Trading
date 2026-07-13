"""Cross-venue futures + gold scanner HTTP routes for the Web UI.

Mounted by ``agent/api_server.py`` via ``register_scanner_routes(app, ...)``.

Routes:
- ``GET /scanner/run`` — run the CoinDCX + Delta Exchange futures + gold
  scanner (``agent/src/skills/crypto-gold-scanner/scanner.py``) together with
  its confluence/confirmation layer, and return ranked setups as JSON.

This endpoint performs READ-ONLY market analysis. It never authenticates to
an exchange, never submits or cancels orders on any venue, and its output is
informational only -- not investment advice.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import Depends, FastAPI, HTTPException, Query

logger = logging.getLogger(__name__)

AuthDep = Callable[..., Awaitable[Any] | Any]

_SCANNER_PATH = (
    Path(__file__).resolve().parents[1] / "skills" / "crypto-gold-scanner" / "scanner.py"
)

_module_cache: Any = None


def _get_scanner_module() -> Any:
    """Import ``scanner.py`` by file path.

    Its parent directory (``crypto-gold-scanner``) uses a hyphen, which is
    not a valid character in a dotted Python package name, so a normal
    ``import`` statement cannot reach it -- ``importlib`` is used instead.
    Cached at module scope after the first successful load.
    """
    global _module_cache
    if _module_cache is None:
        spec = importlib.util.spec_from_file_location(
            "crypto_gold_scanner_scanner", _SCANNER_PATH
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load scanner module from {_SCANNER_PATH}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _module_cache = module
    return _module_cache


def register_scanner_routes(
    app: FastAPI,
    require_auth: AuthDep | None = None,
) -> None:
    """Mount the scanner routes onto ``app``.

    Args:
        app: The host FastAPI app.
        require_auth: Header-auth dependency for JSON endpoints.

    For backwards compatibility, when the dependency callable is not passed
    explicitly we resolve it from the host ``api_server`` module via
    ``sys.modules``. Prefer the explicit form in new call sites.
    """
    if require_auth is None:
        import sys as _sys

        host = _sys.modules.get("api_server") or _sys.modules.get("agent.api_server")
        if host is None:  # pragma: no cover — only triggers on weird import setups
            raise RuntimeError(
                "register_scanner_routes: api_server module not in sys.modules; "
                "ensure api_server is imported before calling this function"
            )
        require_auth = host.require_auth

    # -----------------------------------------------------------------------
    # GET /scanner/run
    # -----------------------------------------------------------------------

    @app.get("/scanner/run", dependencies=[Depends(require_auth)])
    async def run_scanner(
        max_coindcx: int = Query(15, ge=1, le=50),
        max_delta: int = Query(15, ge=1, le=50),
        include_gold: bool = Query(True),
        timeframe_minutes: str = Query("60"),
        higher_timeframe_minutes: str = Query("240"),
        min_rr: float = Query(2.0, ge=0.5, le=10.0),
        solid_only: bool = Query(False),
    ) -> dict[str, Any]:
        """Run the CoinDCX + Delta + gold confluence scanner.

        Read-only market analysis only -- no orders are ever placed on any
        venue. Results are informational, not investment advice.
        """
        try:
            module = await asyncio.to_thread(_get_scanner_module)
            rows = await asyncio.to_thread(
                module.scan_with_confluence,
                max_coindcx,
                max_delta,
                include_gold,
                timeframe_minutes,
                higher_timeframe_minutes,
                min_rr,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("scanner run failed")
            raise HTTPException(status_code=502, detail=f"scanner failed: {exc}") from exc

        if solid_only:
            rows = [r for r in rows if r.get("is_solid")]

        return {
            "count": len(rows),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "setups": rows,
            "disclaimer": (
                "Read-only market analysis. Not investment advice. "
                "No orders are placed on any venue."
            ),
        }
