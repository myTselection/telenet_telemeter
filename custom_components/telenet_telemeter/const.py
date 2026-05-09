DOMAIN = "telenet_telemeter"
NAME = "Telenet Telemeter"

PROVIDER_TELENET = "Telenet"
PROVIDER_BASE = "BASE"
PROVIDERS = [PROVIDER_TELENET, PROVIDER_BASE]

PROVIDER_NAMES = {
    PROVIDER_TELENET: "Telenet Telemeter",
    PROVIDER_BASE: "BASE Telemeter",
}

PROVIDER_CONFIG = {
    PROVIDER_TELENET: {
        "api_url":          "https://api.prd.telenet.be",
        "secure_url":       "https://secure.telenet.be",
        "login_callback":   "telenet_be",
        "authorization_url":"https://api.prd.telenet.be/ocapi/login/authorization/telenet_be?lang=nl&style_hint=care&targetUrl=https://www2.telenet.be/residential/nl/mytelenet/",
        "origin":           "https://www2.telenet.be",
        "referrer":         "https://www2.telenet.be",
        "alt_referer":      "https://www2.telenet.be/residential/nl/mijn-telenet/",
        "maintenance_url":  "https://api.prd.telenet.be/omapi/public/publicconfigs/maintenance_ocapi",
    },
    PROVIDER_BASE: {
        "api_url":          "https://api.prd.base.be",
        "secure_url":       "https://secure.base.be",
        "login_callback":   "base_be",
        "authorization_url":"https://api.prd.base.be/ocapi/login/authorization/base_be?lang=nl&style_hint=care&targetUrl=https://www.base.be/",
        "origin":           "https://www.base.be",
        "referrer":         "https://www.base.be",
        "alt_referer":      "https://www.base.be/",
        "maintenance_url":  "https://api.prd.base.be/omapi/public/publicconfigs/maintenance_ocapi",
    },
}
