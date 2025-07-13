"""Gateway module for mcp-agent-inspector."""

from __future__ import annotations

import atexit
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, List, Dict

from fastapi import APIRouter, FastAPI, Request
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles

if TYPE_CHECKING:  # pragma: no cover
    import uvicorn  # noqa: F401

from .version import __version__
from .sessions import list_sessions, SessionMeta
from .events import create_event_stream_response
from .settings import InspectorSettings, load_inspector_settings

# Create the router with the inspector prefix
_router = APIRouter(prefix="/_inspector")


@_router.get("/health", include_in_schema=False)
async def health() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({"name": "mcp-agent-inspector", "version": __version__})


@_router.get("/sessions")
async def get_sessions(request: Request) -> Dict[str, List[Dict[str, Any]]]:
    """List all sessions from trace files.
    
    Returns a list of session metadata objects sorted by start time (newest first).
    Sessions include both completed sessions from trace files and active sessions
    from the workflow registry (when available).
    """
    # Get settings from app state
    settings = getattr(request.app.state, 'inspector_settings', None)
    sessions = await list_sessions(settings)
    return {
        "sessions": [session.to_dict() for session in sessions]
    }


@_router.get("/events")
async def event_stream(request: Request):
    """Server-Sent Events stream for real-time updates.
    
    Provides real-time events including:
    - SessionStarted: When a new session begins
    - SessionFinished: When a session completes
    - WaitingOnSignal: When a workflow pauses for input
    - Heartbeat: Periodic updates with session metrics
    
    The stream uses SSE format with automatic reconnection support.
    """
    return await create_event_stream_response(request)


def _run_local_uvicorn(app: FastAPI, settings: InspectorSettings) -> None:
    """Run a local Uvicorn server in a background thread."""
    import uvicorn
    
    # Use settings, but allow INSPECTOR_PORT env var to override for test isolation
    port = int(os.getenv("INSPECTOR_PORT", str(settings.port)))
    config = uvicorn.Config(
        app,
        host=settings.host,
        port=port,
        lifespan="off",
        log_level="debug" if settings.debug.debug else "warning",
    )
    server = uvicorn.Server(config)
    
    # Register cleanup handler
    def shutdown() -> None:
        server.should_exit = True
    
    atexit.register(shutdown)
    
    # Run in background thread
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    
    print(f"Inspector running at http://{settings.host}:{port}/_inspector/ui")


def mount(
    app: Optional[FastAPI] = None,
    settings: Optional[InspectorSettings] = None,
) -> None:
    """
    Mount the inspector on an existing FastAPI application.
    
    Args:
        app: Optional FastAPI application instance. If None, will spawn internal server.
        settings: Optional InspectorSettings instance. If None, will load from config/env.
    
    Returns:
        None
        
    Raises:
        RuntimeError: If Inspector is disabled in settings
    
    Examples:
        >>> from mcp_agent.inspector import mount
        >>> from mcp_agent import MCPApp
        >>> 
        >>> app = MCPApp()
        >>> mount(app)  # Inspector available at http://localhost:7800/_inspector/ui
        
        >>> # With custom settings
        >>> from mcp_agent.inspector.settings import InspectorSettings
        >>> settings = InspectorSettings(port=8000, debug={"debug": True})
        >>> mount(app, settings)
        
        >>> # Standalone mode
        >>> mount()  # Spawns internal server at http://localhost:7800/_inspector/ui
    """
    # Load settings from config/env if not provided
    if settings is None:
        # Try to get config from app - handle both FastAPI and MCPApp
        config_dict = None
        
        # First try FastAPI style (app.state.config)
        if app and hasattr(app, 'state') and hasattr(app.state, 'config'):
            config = app.state.config
            if hasattr(config, 'inspector') and config.inspector:
                config_dict = config.inspector.dict() if hasattr(config.inspector, 'dict') else config.inspector
        
        # Then try MCPApp style (app.config or app._config)
        elif app and hasattr(app, 'config'):
            config = app.config
            if hasattr(config, 'inspector') and config.inspector:
                config_dict = config.inspector.dict() if hasattr(config.inspector, 'dict') else config.inspector
        
        elif app and hasattr(app, '_config'):
            config = app._config
            if hasattr(config, 'inspector') and config.inspector:
                config_dict = config.inspector.dict() if hasattr(config.inspector, 'dict') else config.inspector
        
        settings = load_inspector_settings(config_dict)
    
    # Check if Inspector is enabled
    if not settings.enabled:
        if os.getenv("INSPECTOR_ENABLED", "").lower() in ("true", "1", "yes"):
            # Override from environment
            settings.enabled = True
        else:
            # Respect the configuration
            return
    
    # Store settings in app.state for access by endpoints
    if app:
        # Only set state if app has a state attribute (FastAPI)
        if hasattr(app, 'state'):
            app.state.inspector_settings = settings
    
    # Find UI static files directory
    # Navigate to project root, then to the UI dist directory
    project_root = Path(__file__).resolve().parents[3]  # src/mcp_agent/inspector/gateway.py -> project root
    ui_dist_path = project_root / "packages" / "inspector_ui" / "dist"
    
    # Check if app is a FastAPI instance
    is_fastapi = app is not None and hasattr(app, 'include_router')
    
    if is_fastapi:
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
        standalone_app.state.inspector_settings = settings
        
        # Serve static UI files if they exist
        if ui_dist_path.exists():
            standalone_app.mount("/_inspector/ui", StaticFiles(directory=str(ui_dist_path), html=True), name="inspector-ui")
        
        _run_local_uvicorn(standalone_app, settings)
    
    # Register hook subscribers for span enrichment
    from .subscribers import register_all_subscribers
    register_all_subscribers()