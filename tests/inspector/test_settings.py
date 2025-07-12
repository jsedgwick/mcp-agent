"""Tests for Inspector configuration settings."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from mcp_agent.inspector.settings import (
    InspectorSettings,
    StorageSettings,
    SecuritySettings,
    PerformanceSettings,
    DebugSettings,
    load_inspector_settings,
)


class TestStorageSettings:
    """Test StorageSettings model."""
    
    def test_default_values(self):
        """Should have sensible defaults."""
        settings = StorageSettings()
        # The validator expands the path
        assert settings.traces_dir == str(Path("~/.mcp_traces").expanduser())
        assert settings.max_trace_size == 100 * 1024 * 1024  # 100MB
        assert settings.retention_days == 7
    
    def test_path_expansion(self):
        """Should expand ~ in paths."""
        settings = StorageSettings(traces_dir="~/my_traces")
        assert settings.traces_dir == str(Path("~/my_traces").expanduser())
        assert "~" not in settings.traces_dir
    
    def test_custom_values(self):
        """Should accept custom values."""
        settings = StorageSettings(
            traces_dir="/tmp/traces",
            max_trace_size=50 * 1024 * 1024,
            retention_days=30
        )
        assert settings.traces_dir == "/tmp/traces"
        assert settings.max_trace_size == 50 * 1024 * 1024
        assert settings.retention_days == 30


class TestSecuritySettings:
    """Test SecuritySettings model."""
    
    def test_default_values(self):
        """Should default to disabled auth."""
        settings = SecuritySettings()
        assert settings.auth_enabled is False
        assert settings.auth_token is None
        assert settings.cors_origins == []
    
    def test_with_auth(self):
        """Should accept auth configuration."""
        settings = SecuritySettings(
            auth_enabled=True,
            auth_token="secret-token",
            cors_origins=["https://example.com"]
        )
        assert settings.auth_enabled is True
        assert settings.auth_token == "secret-token"
        assert settings.cors_origins == ["https://example.com"]


class TestPerformanceSettings:
    """Test PerformanceSettings model."""
    
    def test_default_values(self):
        """Should have performance defaults."""
        settings = PerformanceSettings()
        assert settings.sample_rate == 1.0
        assert settings.max_sse_clients == 100
        assert settings.sse_buffer_size == 1000
    
    def test_sample_rate_validation(self):
        """Should validate sample rate range."""
        # Valid rates
        PerformanceSettings(sample_rate=0.0)
        PerformanceSettings(sample_rate=0.5)
        PerformanceSettings(sample_rate=1.0)
        
        # Invalid rates
        with pytest.raises(ValidationError):
            PerformanceSettings(sample_rate=-0.1)
        with pytest.raises(ValidationError):
            PerformanceSettings(sample_rate=1.1)


class TestDebugSettings:
    """Test DebugSettings model."""
    
    def test_default_values(self):
        """Should default to debug disabled."""
        settings = DebugSettings()
        assert settings.debug is False
        assert settings.verbose_spans is False
    
    def test_debug_enabled(self):
        """Should accept debug configuration."""
        settings = DebugSettings(debug=True, verbose_spans=True)
        assert settings.debug is True
        assert settings.verbose_spans is True


class TestInspectorSettings:
    """Test InspectorSettings model."""
    
    def test_default_values(self):
        """Should have all defaults configured."""
        settings = InspectorSettings()
        assert settings.enabled is False  # Backward compatibility
        assert settings.port == 7800
        assert settings.host == "127.0.0.1"
        assert isinstance(settings.storage, StorageSettings)
        assert isinstance(settings.security, SecuritySettings)
        assert isinstance(settings.performance, PerformanceSettings)
        assert isinstance(settings.debug, DebugSettings)
    
    def test_nested_configuration(self):
        """Should accept nested configuration."""
        settings = InspectorSettings(
            enabled=True,
            port=8000,
            storage={"traces_dir": "/tmp/traces"},
            security={"auth_enabled": True, "auth_token": "secret"},
            performance={"sample_rate": 0.5},
            debug={"debug": True}
        )
        assert settings.enabled is True
        assert settings.port == 8000
        assert settings.storage.traces_dir == "/tmp/traces"
        assert settings.security.auth_enabled is True
        assert settings.performance.sample_rate == 0.5
        assert settings.debug.debug is True
    
    def test_environment_variables(self, monkeypatch):
        """Should load from environment variables."""
        # Set environment variables
        monkeypatch.setenv("INSPECTOR_ENABLED", "true")
        monkeypatch.setenv("INSPECTOR_PORT", "8080")
        monkeypatch.setenv("INSPECTOR_HOST", "0.0.0.0")
        monkeypatch.setenv("INSPECTOR_STORAGE__TRACES_DIR", "/var/traces")
        monkeypatch.setenv("INSPECTOR_STORAGE__MAX_TRACE_SIZE", "52428800")  # 50MB
        monkeypatch.setenv("INSPECTOR_SECURITY__AUTH_ENABLED", "true")
        monkeypatch.setenv("INSPECTOR_DEBUG__DEBUG", "true")
        
        # Use load_inspector_settings which handles env vars
        settings = load_inspector_settings()
        assert settings.enabled is True
        assert settings.port == 8080
        assert settings.host == "0.0.0.0"
        assert settings.storage.traces_dir == "/var/traces"
        assert settings.storage.max_trace_size == 52428800
        assert settings.security.auth_enabled is True
        assert settings.debug.debug is True


class TestLoadInspectorSettings:
    """Test load_inspector_settings function."""
    
    def test_load_defaults(self, monkeypatch):
        """Should load with defaults."""
        # Temporarily unset the INSPECTOR_ENABLED env var set by conftest
        monkeypatch.delenv("INSPECTOR_ENABLED", raising=False)
        settings = load_inspector_settings()
        assert settings.enabled is False
        assert settings.port == 7800
    
    def test_load_from_config_dict(self):
        """Should load from config dictionary."""
        config = {
            "enabled": True,
            "port": 9000,
            "storage": {
                "traces_dir": "/custom/traces"
            }
        }
        settings = load_inspector_settings(config)
        assert settings.enabled is True
        assert settings.port == 9000
        assert settings.storage.traces_dir == "/custom/traces"
    
    def test_env_override_config(self, monkeypatch):
        """Environment variables should override config."""
        monkeypatch.setenv("INSPECTOR_PORT", "7777")
        
        config = {"port": 9000}
        settings = load_inspector_settings(config, env_override=True)
        assert settings.port == 7777  # Env overrides config
    
    def test_no_env_override(self, monkeypatch):
        """Should respect env_override=False."""
        monkeypatch.setenv("INSPECTOR_PORT", "7777")
        
        config = {"port": 9000}
        settings = load_inspector_settings(config, env_override=False)
        assert settings.port == 9000  # Config value used


def test_yaml_example_parses():
    """The YAML example in docstring should parse correctly."""
    yaml_config = {
        "enabled": True,
        "port": 7800,
        "host": "127.0.0.1",
        "storage": {
            "traces_dir": "~/.mcp_traces",
            "max_trace_size": 104857600,
            "retention_days": 7
        },
        "security": {
            "auth_enabled": False,
            "cors_origins": []
        },
        "performance": {
            "sample_rate": 1.0
        },
        "debug": {
            "debug": False
        }
    }
    
    settings = InspectorSettings(**yaml_config)
    assert settings.enabled is True
    assert settings.storage.max_trace_size == 104857600