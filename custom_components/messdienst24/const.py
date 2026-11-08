from datetime import timedelta

DOMAIN = "messdienst24"

BASE_URL = "https://legacy.messdienst24.de"
CONF_MD = "md"
DEFAULT_MD = "ex"

# The portal only publishes new readings a few times per month.
UPDATE_INTERVAL = timedelta(hours=6)

MANUFACTURER = "EXTERN Messdienst"
