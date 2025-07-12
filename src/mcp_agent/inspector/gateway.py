"""Gateway module for mcp-agent-inspector."""

from __future__ import annotations

import atexit
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from fastapi import APIRouter, FastAPI
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles

if TYPE_CHECKING:  # pragma: no cover
    import uvicorn  # noqa: F401

from .version import __version__

# Create the router with the inspector prefix
_router = APIRouter(prefix="/_inspector")


@_router.get("/health", include_in_schema=False)
async def health() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({"name": "mcp-agent-inspector", "version": __version__})


def _run_local_uvicorn(app: FastAPI) -> None:
    """Run a local Uvicorn server in a background thread."""
    import uvicorn
    
    port = int(os.getenv("INSPECTOR_PORT", "7800"))
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        lifespan="off",
        log_level="warning",
    )
    server = uvicorn.Server(config)
    
    # Register cleanup handler
    def shutdown() -> None:
        server.should_exit = True
    
    atexit.register(shutdown)
    
    # Run in background thread
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    
    print(f"Inspector running at http://127.0.0.1:{port}/_inspector/ui")


def mount(
    app: Optional[FastAPI] = None,
    *,
    expose: bool = False,
    auth: Optional[Any] = None,
    port: int = 7800,
) -> None:
    """
    Mount the inspector on an existing FastAPI application.
    
    Args:
        app: Optional FastAPI application instance. If None, will spawn internal server.
        expose: If True, allow external connections (default: False, localhost only)
        auth: Authentication provider (for future use in 6-production)
        port: Port to bind to when running standalone (default: 7800)
    
    Returns:
        None
        
    Raises:
        NotImplementedError: If expose=True or auth is provided (future features)
    
    Examples:
        >>> from mcp_agent.inspector import mount
        >>> from mcp_agent import MCPApp
        >>> 
        >>> app = MCPApp()
        >>> mount(app)  # Inspector available at http://localhost:7800/_inspector/ui
        
        >>> # Standalone mode
        >>> mount()  # Spawns internal server at http://localhost:7800/_inspector/ui
    """
    if expose:
        # Future milestone feature
        raise NotImplementedError(
            "External exposure not yet implemented (milestone 6-production)"
        )
    
    if auth is not None:
        # Future milestone feature
        raise NotImplementedError(
            "Authentication not yet implemented (milestone 6-production)"
        )
    
    # Find UI static files directory
    # Navigate to project root, then to the UI dist directory
    project_root = Path(__file__).resolve().parents[3]  # src/mcp_agent/inspector/gateway.py -> project root
    ui_dist_path = project_root / "packages" / "inspector_ui" / "dist"
    
    if app is not None:
        # Mount on existing FastAPI app
        app.include_router(_router)
        
        # Serve static UI files if they exist
        if ui_dist_path.exists():
            app.mount("/_inspector/ui", StaticFiles(directory=str(ui_dist_path), html=True), name="inspector-ui")
    else:
        # Create minimal FastAPI app and run standalone
        standalone_app = FastAPI(
            title="mcp-agent-inspector",
            version=__version__,
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
        )
        standalone_app.include_router(_router)
        
        # Serve static UI files if they exist
        if ui_dist_path.exists():
            standalone_app.mount("/_inspector/ui", StaticFiles(directory=str(ui_dist_path), html=True), name="inspector-ui")
        
        _run_local_uvicorn(standalone_app)