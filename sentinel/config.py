import yaml
import os
import sys

DEFAULT_CONFIG = {
    "name": "My-Server",
    "alerts": {
        "telegram": {
            "token": None,
            "chat_id": None,
        },
        "levels": {
            "info":     {"enabled": True},
            "warning":  {"enabled": True, "cooldown": 900},
            "critical": {"enabled": True, "cooldown": 300},
        }
    },
    "monitors": {
        "resources": {
            "cpu":         {"enabled": True, "warning": 60, "critical": 85},
            "ram":         {"enabled": True, "warning": 60, "critical": 85},
            "disk":        {"enabled": True, "warning": 75, "critical": 90},
            "temperature": {"enabled": True, "warning": 70, "critical": 85},
            "network":     {
                "enabled":            True,
                "check_dns":          True,
                "check_outbound":     True,
                "bandwidth_warning":  80,
            },
            "processes": {
                "enabled": True,
                "watch":   [],
            },
            "logs": {
                "enabled": True,
                "watch":   [],
            },
        },
        "docker":      {"enabled": False},
        "postgresql":  {"enabled": False},
        "mysql":       {"enabled": False},
        "services":    [],
        "custom":      [],
    }
}


def deep_merge(base, override):
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load(path="sentinel.yml"):
    if not os.path.exists(path):
        print(f"[Sentinel] Config file not found: {path}")
        print(f"[Sentinel] Run 'sentinel init' to create one.")
        sys.exit(1)

    with open(path, "r") as f:
        user_config = yaml.safe_load(f) or {}

    config = deep_merge(DEFAULT_CONFIG, user_config)

    token   = config["alerts"]["telegram"]["token"]
    chat_id = config["alerts"]["telegram"]["chat_id"]

    if not token or not chat_id:
        print("[Sentinel] Missing Telegram token or chat_id in config.")
        print("[Sentinel] Run 'sentinel init' to set them up.")
        sys.exit(1)

    return config
