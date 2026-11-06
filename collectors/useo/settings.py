"""Configuração via variáveis de ambiente (GitHub Secrets no cron, .env local)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(RuntimeError):
    pass


def load_dotenv(path: Path | None = None) -> None:
    """Carrega um .env simples (CHAVE=valor) sem sobrescrever o ambiente."""
    path = path or REPO_ROOT / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"variável de ambiente {name} não definida (veja .env.example)")
    return value


@dataclass(frozen=True)
class SupabaseSettings:
    url: str
    service_key: str

    @classmethod
    def from_env(cls) -> SupabaseSettings:
        return cls(
            url=_require("SUPABASE_URL").rstrip("/"),
            service_key=_require("SUPABASE_SERVICE_KEY"),
        )


@dataclass(frozen=True)
class DataForSeoSettings:
    login: str
    password: str

    @classmethod
    def from_env(cls) -> DataForSeoSettings:
        return cls(login=_require("DATAFORSEO_LOGIN"), password=_require("DATAFORSEO_PASSWORD"))


def cost_alert_usd() -> float:
    return float(os.environ.get("USEO_COST_ALERT_USD", "5"))
