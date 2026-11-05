"""API keys: read from the environment or ~/.config/novelty-check/keys.json. Never printed."""

from __future__ import annotations

import json
import os
import stat

from . import util

ENV_NAMES = {
    "s2": ("S2_API_KEY", "SEMANTIC_SCHOLAR_API_KEY"),
    "openalex": ("OPENALEX_API_KEY",),
}
LABELS = {"s2": "Semantic Scholar", "openalex": "OpenAlex"}

_loaded: dict | None = None


def keys_path() -> str:
    return os.path.join(util.config_dir(), "keys.json")


def _file_keys() -> dict:
    try:
        with open(keys_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load() -> dict:
    """Return {name: (value, origin)} for every key that is set."""
    global _loaded
    if _loaded is not None:
        return _loaded
    found = {}
    file_keys = _file_keys()
    for name, env_names in ENV_NAMES.items():
        for env in env_names:
            if os.environ.get(env, "").strip():
                found[name] = (os.environ[env].strip(), "environment variable " + env)
                break
        else:
            if isinstance(file_keys.get(name), str) and file_keys[name].strip():
                found[name] = (file_keys[name].strip(), keys_path())
    _loaded = found
    return found


def get(name: str) -> str | None:
    entry = load().get(name)
    return entry[0] if entry else None


def origin(name: str) -> str | None:
    entry = load().get(name)
    return entry[1] if entry else None


def reset() -> None:
    global _loaded
    _loaded = None


def save(name: str, value: str) -> str:
    """Store a key in keys.json (directory 700, file 600). Returns the file path."""
    if name not in ENV_NAMES:
        raise ValueError("unknown key name: %s" % name)
    path = keys_path()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    data = _file_keys()
    data[name] = value.strip()
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    reset()
    return path


def file_mode_problem() -> str | None:
    """Return a warning if keys.json is readable by other users."""
    try:
        mode = os.stat(keys_path()).st_mode
    except OSError:
        return None
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        return "%s is readable by other users; run: chmod 600 %s" % (keys_path(), keys_path())
    return None
