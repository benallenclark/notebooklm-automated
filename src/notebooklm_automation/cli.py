# -----------------------------
# Imports
# -----------------------------
import argparse
import asyncio
from datetime import datetime
import logging

from notebooklm_automation.config import load_config
from notebooklm_automation.runner import StudyBatchRunner


# -----------------------------
# Logging
# -----------------------------
def configure_logging(logs_dir) -> None:
    """
    Configure clean console/file logging for the app.
    """
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Remove old handlers so logs do not duplicate
    root_logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(message)s")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)

    # Silence noisy transport logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


# -----------------------------
# CLI parser
# -----------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run batches of concept prompts against NotebookLM."
    )

    parser.add_argument(
        "--limit-concepts",
        type=int,
        default=None,
        help="Only run the first N concepts.",
    )
    parser.add_argument(
        "--limit-prompts",
        type=int,
        default=None,
        help="Only run the first N prompt templates.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files instead of skipping them.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would run without contacting NotebookLM.",
    )

    return parser


# -----------------------------
# Entry point
# -----------------------------
def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    config = load_config()
    configure_logging(config.logs_dir)

    runner = StudyBatchRunner(config)

    asyncio.run(
        runner.run(
            limit_concepts=args.limit_concepts,
            limit_prompts=args.limit_prompts,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
