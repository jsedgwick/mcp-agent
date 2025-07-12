"""Pytest configuration for inspector tests."""

import os
import tempfile
from pathlib import Path
from typing import Iterator

import pytest


@pytest.fixture(autouse=True)
def enable_inspector():
    """Enable inspector for all tests in this directory."""
    original = os.environ.get("INSPECTOR_ENABLED")
    os.environ["INSPECTOR_ENABLED"] = "true"
    yield
    if original is None:
        os.environ.pop("INSPECTOR_ENABLED", None)
    else:
        os.environ["INSPECTOR_ENABLED"] = original


@pytest.fixture
def temp_traces_dir() -> Iterator[Path]:
    """Provide a temporary directory for trace files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original = os.environ.get("INSPECTOR_STORAGE__TRACES_DIR")
        os.environ["INSPECTOR_STORAGE__TRACES_DIR"] = tmpdir
        yield Path(tmpdir)
        if original is None:
            os.environ.pop("INSPECTOR_STORAGE__TRACES_DIR", None)
        else:
            os.environ["INSPECTOR_STORAGE__TRACES_DIR"] = original


@pytest.fixture
def free_port() -> int:
    """Get a free port for test isolation."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.fixture
def isolated_inspector_port(free_port: int) -> Iterator[int]:
    """Set a unique port for each test to avoid conflicts."""
    original = os.environ.get("INSPECTOR_PORT")
    os.environ["INSPECTOR_PORT"] = str(free_port)
    yield free_port
    if original is None:
        os.environ.pop("INSPECTOR_PORT", None)
    else:
        os.environ["INSPECTOR_PORT"] = original