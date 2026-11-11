# OpenWA WhatsApp for Home Assistant

[![Quality gate](https://sonarcloud.io/api/project_badges/quality_gate?project=smarquina_openwa-HA)](https://sonarcloud.io/summary/new_code?id=smarquina_openwa-HA)
[![Validation](https://github.com/smarquina/openwa-HA/actions/workflows/validation.yml/badge.svg?branch=main)](https://github.com/smarquina/openwa-HA/actions/workflows/validation.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.10%2B-blue?logo=homeassistant)](https://www.home-assistant.io/)

Send WhatsApp text notifications from Home Assistant through a self-hosted [OpenWA API gateway](https://github.com/rmyndharis/OpenWA). The integration connects to an existing OpenWA instance over HTTP or HTTPS.

## Requirements

- Home Assistant 2026.10 or later.
- A running [rmyndharis/OpenWA](https://github.com/rmyndharis/OpenWA) instance, accessible from Home Assistant. Follow the [OpenWA Docker installation guide](https://docs.open-wa.org/getting-started/install-docker) to deploy it with Docker or Portainer.
- An OpenWA session linked to WhatsApp and in the `ready` state.
- An OpenWA API key with permission to read the selected session and send messages. Use an operator key scoped to the intended session and chats where supported.
- The session ID and the WhatsApp chat IDs that will receive notifications.

OpenWA is an external service. Its API and dashboard normally use TCP port `2785`. Keep the API accessible to Home Assistant on your private network and use HTTPS when available. OpenWA requires its own outbound connection to WhatsApp.

## Install

On Home Assistant 2026.11 or later, open the repository in the Marketplace:

[![Open OpenWA WhatsApp in your Home Assistant Marketplace](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=smarquina&repository=openwa-HA&category=integration)

For an existing HACS installation:

[![Open OpenWA WhatsApp in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=smarquina&repository=openwa-HA&category=integration)

Install the integration and restart Home Assistant. Then add it:

[![Add OpenWA WhatsApp to Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=openwa_whatsapp)

The buttons open your configured instance through My Home Assistant. The repository button opens the installation page. The integration must be installed and loaded before starting its configuration flow.

To install manually, copy `custom_components/openwa_whatsapp` from this repository into `/config/custom_components/openwa_whatsapp`, then restart Home Assistant.

## OpenWA setup

1. Deploy and start the [OpenWA Docker instance](https://docs.open-wa.org/getting-started/install-docker). Preserve its data and session storage across container restarts.
2. Open the OpenWA dashboard at `http://OPENWA_HOST:2785` or your configured HTTPS address.
3. Create a session, start it and link WhatsApp using the QR code. The integration uses the session ID, which may differ from its display name.
4. Create an API key with operator permissions. Where available, restrict the key to the selected session and the recipients that should receive notifications.
5. Make the API reachable from Home Assistant. Use the URL of the OpenWA server, without the `/api` suffix.

For server configuration and endpoints, see the [OpenWA Docker documentation](https://docs.open-wa.org/getting-started/install-docker), the [API reference](https://docs.open-wa.org/api-reference), and the [OpenWA API specification](https://github.com/rmyndharis/OpenWA/blob/main/docs/06-api-specification.md).

## Configure the integration

In Home Assistant, open **Settings → Devices & services → Add integration** and select **OpenWA WhatsApp**.

| Field | Value |
|---|---|
| OpenWA base URL | Origin of the OpenWA API, such as `https://openwa.example` or `http://192.168.1.20:2785`. Do not append `/api`. |
| API key | OpenWA API key with access to the selected session and permission to send messages. |
| Session ID | The ID of the linked OpenWA session. |
| Allow unencrypted HTTP to a private IP | Enable only when using HTTP with a private IP address. HTTPS is the default. |

The integration checks that the selected session is ready. To change the connection settings, open the integration entry and select **Reconfigure**. Home Assistant stores the API key in the integration configuration.

## Send a message

Use the `openwa_whatsapp.send_message` action in an automation, script or **Developer Tools → Actions**.

```yaml
action: openwa_whatsapp.send_message
data:
  chat_id: "15551234567@c.us"
  message: "The washing machine has finished."
```

| Field | Required | Description |
|---|---|---|
| `chat_id` | Yes | WhatsApp individual or group chat ID. Individual IDs use the international number followed by `@c.us`. Group IDs end in `@g.us`. |
| `message` | Yes | Text to send, up to 4,096 characters. |
| `entry_id` | When multiple entries are loaded | Home Assistant configuration entry ID identifying the OpenWA instance. |

The integration calls the OpenWA REST API with `X-API-Key` and sends text to `POST /api/sessions/{session_id}/messages/send-text`. OpenWA's acceptance of a message does not confirm delivery to the recipient.

## Remove

Remove the integration entry under **Settings → Devices & services**. Uninstall it through Marketplace or HACS, or remove `/config/custom_components/openwa_whatsapp` after a manual installation. Restart Home Assistant. The OpenWA instance and its session data are managed separately.

## License

This project is distributed under the [MIT License](LICENSE).
