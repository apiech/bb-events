from __future__ import annotations

import atexit
import os
from pathlib import Path


def _load_env(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key and value and key not in os.environ:
            os.environ[key] = value

from bb_xml_api_client import BBXmlApiClient  # noqa: E402


_CLIENTS: dict[tuple[str | None, str | None], BBXmlApiClient] = {}


def get_client(
    username: str | None = None,
    security_code: str | None = None,
) -> BBXmlApiClient:
    _load_env()
    key = (username, security_code)
    client = _CLIENTS.get(key)
    if client is None:
        client = BBXmlApiClient(username=username, security_code=security_code)
        _CLIENTS[key] = client
    return client


def close_client() -> None:
    for client in list(_CLIENTS.values()):
        try:
            client.close()
        finally:
            pass
    _CLIENTS.clear()


atexit.register(close_client)
