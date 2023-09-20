{
    "config": {
        "title": "Telenet Telemeter",
        "step": {
            "user": {
                "description": "Setup a Telenet Telementer sensor, username and password are required. Please indicate if internet and/or mobile usage is to be tracked.",
                "data": {
                    "username": "Username",
                    "password": "Password",
					"internet": "Internet",
					"mobile": "Mobile"
                }
            },
            "edit": {
                "description": "Edit Setup a Telenet Telemeter sensor, username and password are required. Please indicate if internet and/or mobile usage is to be tracked.",
                "data": {
                    "username": "Username",
                    "password": "Password",
					"internet": "Internet",
					"mobile": "Mobile"
                }
            }

        },
        "error": {
            "missing username": "Please provide a valid Telenet username",
            "missing password": "Please provide a valid Telenet password",
            "missing internet": "Please indicate if internet usage is to be tracked",
            "missing mobile": "Please indicate if mobile usage is to be tracked",
            "missing data options handler": "Option handler failed",
            "no_valid_settings": "No valid settings, provide username, password, internet & mobile in ha config."
        }
    },
    "options": {
        "step": {
            "edit": {
                "description": "Edit setup a Telenet Telemeter sensor, username and password are required. Please indicate if internet and/or mobile usage is to be tracked.",
                "data": {
                    "username": "Username",
                    "password": "Password",
					"internet": "Internet",
					"mobile": "Mobile"
                }
            }
        },
        "error": {
            "missing username": "Please provide a valid Telenet username",
            "missing password": "Please provide a valid Telenet password",
            "missing internet": "Please indicate if internet usage is to be tracked",
            "missing mobile": "Please indicate if mobile usage is to be tracked",
            "missing data options handler": "Option handler failed",
            "no_valid_settings": "No valid settings, provide username, password, internet & mobile in ha config."
        }
    },
    "services": {
        "switch_wifi": {
            "name": "switch_wifi",
            "description": "Enable or disable the wifi.",
            "fields": {
                "enable": {
                    "name": "enable",
                    "description": "Yes to enable wifi, No to disable wifi"
                }
            }
        },
        "switch_wifree": {
            "name": "switch_wifree",
            "description": "Enable or disable the wifree (open shared wifi network that can be used by other Telenet users too).",
            "fields": {
                "enable": {
                    "name": "enable",
                    "description": "Yes to enable wifree, No to disable wifree"
                }
            }
        }
    }
}