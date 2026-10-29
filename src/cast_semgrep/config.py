"""Local configuration. Credentials are never written to the database or logs."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        result[key.strip()] = value
    return result


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: Path
    db_path: Path
    cast_username: str
    cast_password: str
    cast_request_interval: float
    openai_api_key: str = field(default="", repr=False)

    @property
    def cast_credentials_available(self) -> bool:
        return bool(self.cast_username and self.cast_password)


def load_settings() -> Settings:
    values = _read_dotenv(PROJECT_ROOT / ".env")

    def get(name: str, default: str = "") -> str:
        return os.environ.get(name, values.get(name, default))

    def local_path(value: str) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else PROJECT_ROOT / path

    return Settings(
        project_root=PROJECT_ROOT,
        data_dir=local_path(get("COMPARATOR_DATA_DIR", "data/raw")),
        db_path=local_path(get("COMPARATOR_DB", "data/comparator.sqlite3")),
        cast_username=get("CAST_USERNAME"),
        cast_password=get("CAST_PASSWORD"),
        cast_request_interval=max(0.0, float(get("CAST_REQUEST_INTERVAL", "0.35"))),
        openai_api_key=get("OPENAI_API_KEY").strip(),
    )
