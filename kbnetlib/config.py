"""Local install config (~/.kbnet/config.json) + hub control config."""
import json
import os


def kbnet_home():
    return os.environ.get("KBNET_HOME", os.path.expanduser("~/.kbnet"))


def paths():
    home = kbnet_home()
    return {
        "home": home,
        "config": os.path.join(home, "config.json"),
        "exchange": os.path.join(home, "exchange"),
        "tool": os.path.join(home, "tool"),
        "ssh_key": os.path.join(home, "id_kbnet"),
    }


def load_local():
    p = paths()
    with open(p["config"], encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("exchange_path", p["exchange"])
    for key in ("peer", "vault_path"):
        if not cfg.get(key):
            raise SystemExit(f"kbnet: '{key}' missing from {p['config']} — re-run the installer")
    return cfg


CONTROL_DEFAULTS = {
    "disabled": False,
    "tool_ref": "main",
    "extra_personal_callouts": [],
    "sync_folders_override": None,
    "sources_ttl_days": 14,
    "max_request_results": 50,
    "max_source_file_mb": 5,
}


def load_control(exchange_path):
    ctl = dict(CONTROL_DEFAULTS)
    try:
        with open(os.path.join(exchange_path, "control", "config.json"), encoding="utf-8") as f:
            ctl.update(json.load(f))
    except (OSError, ValueError):
        pass
    return ctl
