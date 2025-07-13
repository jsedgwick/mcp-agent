"""Inspector configuration settings with Pydantic models."""
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageSettings(BaseModel):
    """Storage configuration for Inspector traces."""
    
    traces_dir: str = Field(
        default_factory=lambda: str(Path("~/.mcp_traces").expanduser()),
        description="Directory for storing trace files"
    )
    max_trace_size: int = Field(
        default=100 * 1024 * 1024,  # 100MB
        description="Maximum size of a single trace file before rotation"
    )
    retention_days: int = Field(
        default=7,
        description="Number of days to retain trace files"
    )
    
    @field_validator('traces_dir', mode='after')
    @classmethod
    def expand_traces_dir(cls, v: str) -> str:
        """Expand ~ and environment variables in path."""
        return str(Path(v).expanduser())


class SecuritySettings(BaseModel):
    """Security configuration for Inspector."""
    
    auth_enabled: bool = Field(
        default=False,
        description="Enable session token authentication"
    )
    auth_token: Optional[str] = Field(
        default=None,
        description="Session authentication token"
    )
    cors_origins: List[str] = Field(
        default_factory=list,
        description="Allowed CORS origins"
    )


class PerformanceSettings(BaseModel):
    """Performance tuning settings."""
    
    sample_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Sampling rate for spans (0.0-1.0)"
    )
    max_sse_clients: int = Field(
        default=100,
        description="Maximum concurrent SSE connections"
    )
    sse_buffer_size: int = Field(
        default=1000,
        description="Event buffer size per SSE client"
    )


class DebugSettings(BaseModel):
    """Debug configuration."""
    
    debug: bool = Field(
        default=False,
        description="Enable debug logging"
    )
    verbose_spans: bool = Field(
        default=False,
        description="Include verbose span data"
    )


class InspectorSettings(BaseSettings):
    """Top-level Inspector configuration.
    
    Configuration precedence (later overrides earlier):
    1. Default values in this model
    2. Values from inspector: section in mcp_agent.config.yaml
    3. Environment variables prefixed with INSPECTOR_
    4. Runtime parameters passed to mount()
    
    Example YAML configuration:
    ```yaml
    inspector:
      enabled: true
      port: 7800
      host: "127.0.0.1"
      storage:
        traces_dir: "~/.mcp_traces"
        max_trace_size: 104857600  # 100MB
        retention_days: 7
      security:
        auth_enabled: false
        cors_origins: []
      performance:
        sample_rate: 1.0
      debug:
        debug: false
    ```
    
    Example environment variables:
    - INSPECTOR_ENABLED=true
    - INSPECTOR_PORT=7801
    - INSPECTOR_DEBUG__DEBUG=true  (nested fields use __)
    """
    
    enabled: bool = Field(
        default=False,
        description="Enable Inspector (default False for backward compatibility)"
    )
    port: int = Field(
        default=7800,
        description="Port for Inspector HTTP server"
    )
    host: str = Field(
        default="127.0.0.1",
        description="Host to bind Inspector server"
    )
    
    # Nested configuration sections
    storage: StorageSettings = Field(
        default_factory=StorageSettings,
        description="Storage configuration"
    )
    security: SecuritySettings = Field(
        default_factory=SecuritySettings,
        description="Security configuration"
    )
    performance: PerformanceSettings = Field(
        default_factory=PerformanceSettings,
        description="Performance tuning"
    )
    debug: DebugSettings = Field(
        default_factory=DebugSettings,
        description="Debug settings"
    )
    
    model_config = ConfigDict(
        env_prefix="INSPECTOR_",
        env_nested_delimiter="__",
        case_sensitive=False,
    )


def load_inspector_settings(
    config_dict: Optional[dict] = None
) -> InspectorSettings:
    """Load Inspector settings from multiple sources.
    
    Args:
        config_dict: Dictionary from YAML config file (inspector: section)
        
    Returns:
        Resolved InspectorSettings with all sources merged
    """
    # Pydantic's BaseSettings will automatically load from environment variables
    # if they are prefixed with `INSPECTOR_`.
    # It will also correctly merge the dictionary from the config file.
    if config_dict:
        return InspectorSettings(**config_dict)
    return InspectorSettings()