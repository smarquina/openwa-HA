"""Constants for the OpenWA WhatsApp integration."""

DOMAIN = "openwa_whatsapp"

CONF_BASE_URL = "base_url"
CONF_API_KEY = "api_key"
CONF_SESSION_ID = "session_id"
CONF_ALLOW_HTTP = "allow_http"
CONF_POLL_INTERVAL = "poll_interval"
DEFAULT_POLL_INTERVAL = 60
MIN_POLL_INTERVAL = 10
MAX_POLL_INTERVAL = 86400

SERVICE_SEND_MESSAGE = "send_message"

ATTR_CHAT_ID = "chat_id"
ATTR_MESSAGE = "message"
ATTR_ENTRY_ID = "entry_id"

DEFAULT_NAME = "OpenWA WhatsApp"
