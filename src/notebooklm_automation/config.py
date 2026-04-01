# -----------------------------
# Imports
# -----------------------------
from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class AppConfig:
    default_notebook_id: str | None
    concepts_csv: Path
    prompts_dir: Path
    output_dir: Path
    logs_dir: Path
    retries: int
    delay_seconds: float


def _resolve_path(raw_value: str, default_value: str) -> Path:
    raw = raw_value.strip() if raw_value else default_value
    path = Path(raw)

    if path.is_absolute():
        return path

    return PROJECT_ROOT / path


def load_config() -> AppConfig:
    return AppConfig(
        default_notebook_id=os.getenv("DEFAULT_NOTEBOOK_ID") or None,
        concepts_csv=_resolve_path(os.getenv("CONCEPTS_CSV", ""), "data/concepts.csv"),
        prompts_dir=_resolve_path(os.getenv("PROMPTS_DIR", ""), "prompts"),
        output_dir=_resolve_path(os.getenv("OUTPUT_DIR", ""), "output"),
        logs_dir=_resolve_path(os.getenv("LOGS_DIR", ""), "logs"),
        retries=int(os.getenv("RETRIES", "1")),
        delay_seconds=float(os.getenv("DELAY_SECONDS", "2.0")),
    )
