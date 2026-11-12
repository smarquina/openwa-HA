"""Tests for the live OpenWA session check without network access."""

import io
import json
from email.message import Message
from urllib.error import URLError
from unittest.mock import Mock

import pytest

from scripts import check_openwa_session as check


@pytest.fixture
def credentials(monkeypatch):
    monkeypatch.setenv("OPENWA_BASE_URL", "https://openwa.example")
    monkeypatch.setenv("OPENWA_SESSION_ID", "main")
    monkeypatch.setenv("OPENWA_API_KEY", "test-key")


def response(body, content_type="application/json", status=200):
    result = io.BytesIO(body)
    result.status = status
    result.headers = Message()
    result.headers["Content-Type"] = content_type
    return result


def test_ready_session(credentials, monkeypatch, capsys):
    opener = Mock()
    opener.open.return_value = response(json.dumps({"id": "main", "status": "ready"}).encode())
    monkeypatch.setattr(check, "build_opener", lambda *_: opener)
    assert check.main() == 0
    assert "ready" in capsys.readouterr().out
    assert opener.open.call_count == 1


@pytest.mark.parametrize("body", [b"[]", b"not json", b'{}', b'x' * (check.MAX_RESPONSE_BYTES + 1)])
def test_invalid_response(credentials, monkeypatch, body, capsys):
    opener = Mock()
    opener.open.return_value = response(body)
    monkeypatch.setattr(check, "build_opener", lambda *_: opener)
    assert check.main() == 1
    assert "test-key" not in capsys.readouterr().err


def test_connection_failure(credentials, monkeypatch, capsys):
    opener = Mock()
    opener.open.side_effect = URLError("private test-key")
    monkeypatch.setattr(check, "build_opener", lambda *_: opener)
    assert check.main() == 1
    assert "test-key" not in capsys.readouterr().err


def test_invalid_settings_do_not_connect(credentials, monkeypatch):
    monkeypatch.setenv("OPENWA_BASE_URL", "http://openwa.example")
    opener = Mock()
    monkeypatch.setattr(check, "build_opener", opener)
    assert check.main() == 1
    opener.assert_not_called()


def test_redirects_are_rejected():
    assert check.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example") is None
