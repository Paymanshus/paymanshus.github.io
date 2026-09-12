"""HTTP port + turn-detector gating used by the Railway deploy.

Run: cd agent && .venv/bin/python -m pytest tests/test_deploy_env.py -q
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Importing main loads plugins; keep this file small and env-only.
os.environ.setdefault("LIVEKIT_URL", "wss://test.livekit.cloud")
os.environ.setdefault("LIVEKIT_API_KEY", "test")
os.environ.setdefault("LIVEKIT_API_SECRET", "test-secret-value")

import main  # noqa: E402


def test_http_port_prefers_token_server_port(monkeypatch):
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.setenv("TOKEN_SERVER_PORT", "9000")
    monkeypatch.setenv("PORT", "1234")
    assert main.http_listen_port() == 9000


def test_http_port_prefers_railway_port(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("TOKEN_SERVER_PORT", "8080")
    monkeypatch.setenv("PORT", "1234")
    assert main.http_listen_port() == 1234


def test_http_port_falls_back_to_platform_port(monkeypatch):
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("TOKEN_SERVER_PORT", raising=False)
    monkeypatch.setenv("PORT", "8081")
    assert main.http_listen_port() == 8081


def test_http_port_defaults_to_8080(monkeypatch):
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("TOKEN_SERVER_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    assert main.http_listen_port() == 8080


def test_turn_detector_explicit_false_on_railway(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("VOICE_TURN_DETECTOR", "false")
    assert main.use_turn_detector() is False


def test_turn_detector_explicit_true_on_railway(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("VOICE_TURN_DETECTOR", "true")
    assert main.use_turn_detector() is True


def test_turn_detector_defaults_off_on_railway(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("VOICE_TURN_DETECTOR", raising=False)
    assert main.use_turn_detector() is False


def test_turn_detector_defaults_on_locally(monkeypatch):
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("VOICE_TURN_DETECTOR", raising=False)
    assert main.use_turn_detector() is True


def test_idle_processes_default_zero(monkeypatch):
    monkeypatch.delenv("AGENT_IDLE_PROCESSES", raising=False)
    assert main.idle_process_count() == 0


def test_idle_processes_explicit(monkeypatch):
    monkeypatch.setenv("AGENT_IDLE_PROCESSES", "1")
    assert main.idle_process_count() == 1
