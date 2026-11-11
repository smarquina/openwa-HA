"""Exercise the Home Assistant flow and the OpenWA send contract."""

import aiohttp
import pytest
import voluptuous as vol

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openwa_whatsapp.client import OpenWAError, validate_endpoint

DOMAIN = "openwa_whatsapp"
BASE = "https://openwa.example"
SESSION_URL = f"{BASE}/api/sessions/main"
SEND_URL = f"{SESSION_URL}/messages/send-text"
KEY = "test-secret-key"
CHAT = "15551234567@c.us"
MESSAGE = "Private test message"
CONFIG = {"base_url": BASE, "session_id": "main", "api_key": KEY, "allow_http": False}
JSON = {"Content-Type": "application/json"}
READY = {"id": "main", "status": "ready", "engineLoaded": True}


@pytest.mark.parametrize(
    ("url", "session", "opt_in", "error"),
    [
        ("https://user:password@openwa.example", "main", False, "invalid_url"),
        ("https://openwa.example/api", "main", False, "invalid_url"),
        ("https://openwa.example?token=secret", "main", False, "invalid_url"),
        ("https://openwa.example:0", "main", False, "invalid_url"),
        (BASE, "../other", False, "invalid_session_id"),
        ("http://192.168.1.20:2785", "main", False, "http_requires_opt_in"),
        ("http://openwa.local:2785", "main", True, "http_requires_private_ip"),
        ("http://8.8.8.8", "main", True, "http_requires_private_ip"),
    ],
)
def test_endpoint_restrictions(url, session, opt_in, error):
    with pytest.raises(OpenWAError, match=f"^{error}$"):
        validate_endpoint(url, KEY, session, opt_in)


def test_private_http_opt_in():
    url = "http://192.168.1.20:2785"
    assert str(validate_endpoint(url + "/", KEY, "main", True)) == url


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (401, {"message": KEY}, "invalid_auth"),
        (403, {}, "forbidden"),
        (404, {}, "session_not_found"),
        (200, {"id": "main", "status": "qr_ready"}, "session_not_ready"),
        (200, {**READY, "engineLoaded": False}, "session_not_ready"),
        (200, {"id": "other", "status": "ready"}, "invalid_response"),
        (200, [READY], "invalid_response"),
        (200, {**READY, "extra": "x" * 65536}, "invalid_response"),
        (302, {}, "invalid_response"),
    ],
)
async def test_flow_rejects_invalid_session(hass, aioclient_mock, status, body, error):
    aioclient_mock.get(
        SESSION_URL, status=status, json=body, headers={**JSON, "Location": "https://other.example"}
    )
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], CONFIG)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    assert len(aioclient_mock.mock_calls) == 1


async def test_flow_creates_entry_and_reconfigures_key(hass, aioclient_mock):
    aioclient_mock.get(SESSION_URL, json=READY, headers=JSON)
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], CONFIG)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.data["api_key"] == KEY

    flow = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    assert flow["type"] is FlowResultType.FORM
    assert not any(
        field.schema == "api_key" and field.default is not vol.UNDEFINED
        for field in flow["data_schema"].schema
    )
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {**CONFIG, "api_key": "replacement-test-key"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert entry.data["api_key"] == "replacement-test-key"


@pytest.fixture
async def configured(hass, aioclient_mock):
    entry = MockConfigEntry(domain=DOMAIN, data=CONFIG)
    entry.add_to_hass(hass)
    aioclient_mock.get(SESSION_URL, json=READY, headers=JSON)
    assert await hass.config_entries.async_setup(entry.entry_id)
    aioclient_mock.clear_requests()
    assert hass.services.has_service(DOMAIN, "send_message")
    assert not hass.services.has_service(DOMAIN, "start_session")
    return entry


async def _send(hass, **data):
    await hass.services.async_call(
        DOMAIN, "send_message", {"chat_id": CHAT, "message": MESSAGE, **data}, blocking=True
    )


async def test_send_after_transient_read_failure(hass, aioclient_mock, configured):
    async def respond_once(method, url, data):
        response.side_effect = None
        return transient

    transient = aioclient_mock.request("get", SESSION_URL, status=503)
    aioclient_mock.clear_requests()
    response = aioclient_mock.request(
        "get", SESSION_URL, json=READY, headers=JSON, side_effect=respond_once
    )
    aioclient_mock.post(SEND_URL, status=201, json={"messageId": "message-id"}, headers=JSON)
    await _send(hass)
    assert [call[0] for call in aioclient_mock.mock_calls] == ["GET", "GET", "POST"]
    _, _, payload, headers = aioclient_mock.mock_calls[-1]
    assert payload == {"chatId": CHAT, "text": MESSAGE}
    assert headers["X-API-Key"] == KEY


@pytest.mark.parametrize(
    ("status", "exc"),
    [
        (500, None),
        (503, None),
        (307, None),
        (201, None),
        (None, TimeoutError()),
        (None, aiohttp.ServerDisconnectedError()),
    ],
)
async def test_ambiguous_post_is_never_replayed(
    hass, aioclient_mock, configured, caplog, status, exc
):
    aioclient_mock.get(SESSION_URL, json=READY, headers=JSON)
    if exc is None:
        aioclient_mock.post(
            SEND_URL,
            status=status,
            json={"message": f"{KEY} {CHAT} {MESSAGE}"},
            headers={**JSON, "Location": "https://other.example"},
        )
    else:
        aioclient_mock.post(SEND_URL, exc=exc)
    with pytest.raises(ServiceValidationError) as failure:
        await _send(hass)
    assert failure.value.translation_key == "send_unknown"
    assert failure.value.__suppress_context__
    assert [call[0] for call in aioclient_mock.mock_calls] == ["GET", "POST"]
    for private in (KEY, CHAT, MESSAGE):
        assert private not in str(failure.value)
        assert private not in caplog.text


async def test_disconnected_session_never_posts(hass, aioclient_mock, configured):
    aioclient_mock.get(SESSION_URL, json={**READY, "status": "disconnected"}, headers=JSON)
    with pytest.raises(ServiceValidationError) as failure:
        await _send(hass)
    assert failure.value.translation_key == "session_not_ready"
    assert [call[0] for call in aioclient_mock.mock_calls] == ["GET"]


async def test_existing_http_entry_requires_consent(hass, aioclient_mock):
    config = {"base_url": "http://192.168.1.20:2785", "api_key": KEY, "session_id": "main"}
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert not aioclient_mock.mock_calls


async def test_legacy_http_can_be_reconfigured_in_place(hass, aioclient_mock):
    base = "http://192.168.1.20:2785"
    config = {"base_url": base, "api_key": KEY, "session_id": "main"}
    entry = MockConfigEntry(domain=DOMAIN, data=config)
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)

    aioclient_mock.get(f"{base}/api/sessions/main", json=READY, headers=JSON)
    flow = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {**config, "allow_http": True}
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.state.value == "loaded"
    assert entry.data["allow_http"] is True


async def test_read_retry_exhausted_never_posts(hass, aioclient_mock, configured):
    aioclient_mock.get(SESSION_URL, status=503)
    with pytest.raises(ServiceValidationError) as failure:
        await _send(hass)
    assert failure.value.translation_key == "cannot_connect"
    assert [call[0] for call in aioclient_mock.mock_calls] == ["GET", "GET"]


async def test_http_redirect_is_never_followed(hass, aioclient_mock, configured, monkeypatch):
    """Inspect aiohttp arguments for both session reads and message submissions."""
    client = configured.runtime_data._gateway
    request = client._http._request
    redirect_flags = []

    async def record_request(method, url, **kwargs):
        redirect_flags.append(kwargs.get("allow_redirects"))
        return await request(method, url, **kwargs)

    monkeypatch.setattr(client._http, "_request", record_request)
    aioclient_mock.get(SESSION_URL, json=READY, headers=JSON)
    aioclient_mock.post(SEND_URL, status=307, headers={"Location": "https://other.example"})
    with pytest.raises(ServiceValidationError):
        await _send(hass)
    assert redirect_flags == [False, False]


@pytest.mark.parametrize("data", [{"chat_id": "status@broadcast"}, {"message": " "}, {"message": "x" * 4097}])
async def test_invalid_action_data_never_reaches_openwa(hass, aioclient_mock, configured, data):
    with pytest.raises(vol.Invalid):
        await _send(hass, **data)
    assert not aioclient_mock.mock_calls


async def test_reauthentication_updates_existing_entry(hass, aioclient_mock, configured):
    aioclient_mock.get(SESSION_URL, json=READY, headers=JSON)
    flow = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reauth", "entry_id": configured.entry_id},
        data=dict(configured.data),
    )
    assert flow["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"api_key": "replacement-key"}
    )
    assert result["reason"] == "reauth_successful"
    assert configured.data["api_key"] == "replacement-key"


async def test_diagnostics_redact_secrets(hass, configured):
    from custom_components.openwa_whatsapp.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, configured)
    assert diagnostics["entry_state"] == "loaded"
    assert KEY not in str(diagnostics)
    assert BASE not in str(diagnostics)


async def test_setup_fails_when_api_is_unavailable(hass, aioclient_mock):
    entry = MockConfigEntry(domain=DOMAIN, data=CONFIG)
    entry.add_to_hass(hass)
    aioclient_mock.get(SESSION_URL, status=503)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state.value == "setup_retry"


async def test_setup_starts_reauth_on_unauthorized(hass, aioclient_mock):
    entry = MockConfigEntry(domain=DOMAIN, data=CONFIG)
    entry.add_to_hass(hass)
    aioclient_mock.get(SESSION_URL, status=401)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert any(flow["context"]["source"] == "reauth" for flow in hass.config_entries.flow.async_progress())


async def test_reauth_rejects_bad_credentials(hass, aioclient_mock, configured):
    aioclient_mock.get(SESSION_URL, status=401)
    flow = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reauth", "entry_id": configured.entry_id},
        data=dict(configured.data),
    )
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"api_key": "bad-key"}
    )
    assert result["errors"] == {"base": "invalid_auth"}
    assert configured.data["api_key"] == KEY


async def test_unload_entry(hass, configured):
    assert await hass.config_entries.async_unload(configured.entry_id)
    assert configured.entry_id not in hass.data[DOMAIN]


async def test_multiple_entries_require_selection(hass, aioclient_mock, configured):
    other = MockConfigEntry(domain=DOMAIN, data=CONFIG)
    other.add_to_hass(hass)
    aioclient_mock.get(SESSION_URL, json=READY, headers=JSON)
    assert await hass.config_entries.async_setup(other.entry_id)
    with pytest.raises(ServiceValidationError) as failure:
        await _send(hass)
    assert failure.value.translation_key == "select_entry"


async def test_application_sends_once():
    from custom_components.openwa_whatsapp.application import SendNotification

    class Gateway:
        def __init__(self):
            self.calls = []

        async def async_check_session(self):
            self.calls.append("check")

        async def async_send_text(self, chat_id, message):
            self.calls.append((chat_id, message))

    gateway = Gateway()
    await SendNotification(gateway).execute(CHAT, MESSAGE)
    assert gateway.calls == ["check", (CHAT, MESSAGE)]


async def test_application_never_sends_when_check_fails():
    from custom_components.openwa_whatsapp.application import SendNotification

    class Gateway:
        async def async_check_session(self):
            raise OpenWAError("session_not_ready")

        async def async_send_text(self, chat_id, message):
            pytest.fail("Unexpected send")

    with pytest.raises(OpenWAError, match="session_not_ready"):
        await SendNotification(Gateway()).execute(CHAT, MESSAGE)


async def test_action_starts_reauth(hass, aioclient_mock, configured):
    aioclient_mock.get(SESSION_URL, status=401)
    with pytest.raises(ServiceValidationError) as failure:
        await _send(hass)
    assert failure.value.translation_key == "invalid_auth"
    await hass.async_block_till_done()
    assert any(flow["context"]["source"] == "reauth" for flow in hass.config_entries.flow.async_progress())


@pytest.mark.parametrize(("status", "error"), [(401, "invalid_auth"), (403, "forbidden"), (400, "send_rejected")])
async def test_send_rejection(hass, aioclient_mock, configured, status, error):
    aioclient_mock.get(SESSION_URL, json=READY, headers=JSON)
    aioclient_mock.post(SEND_URL, status=status)
    with pytest.raises(ServiceValidationError) as failure:
        await _send(hass)
    assert failure.value.translation_key == error
    assert len(aioclient_mock.mock_calls) == 2


@pytest.mark.parametrize("content,headers", [(b"garbage", JSON), (b"{}", {"Content-Type": "text/plain"})])
async def test_invalid_session_json(hass, aioclient_mock, content, headers):
    aioclient_mock.get(SESSION_URL, content=content, headers=headers)
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], CONFIG)
    assert result["errors"] == {"base": "invalid_response"}


def test_empty_key_rejected():
    with pytest.raises(OpenWAError, match="invalid_auth"):
        validate_endpoint(BASE, "", "main", False)


async def test_session_network_failure(hass, aioclient_mock, configured):
    aioclient_mock.get(SESSION_URL, exc=aiohttp.ServerDisconnectedError())
    with pytest.raises(ServiceValidationError) as failure:
        await _send(hass)
    assert failure.value.translation_key == "cannot_connect"


async def test_duplicate_config_entry(hass, aioclient_mock):
    aioclient_mock.get(SESSION_URL, json=READY, headers=JSON)
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], CONFIG)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], CONFIG)
    assert result["reason"] == "already_configured"


async def test_setup_handles_missing_session(hass, aioclient_mock):
    entry = MockConfigEntry(domain=DOMAIN, data=CONFIG)
    entry.add_to_hass(hass)
    aioclient_mock.get(SESSION_URL, status=404)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state.value == "setup_error"
