# -----------------------------
# Imports
# -----------------------------
import argparse
import asyncio
import json

from notebooklm import NotebookLMClient
from notebooklm_automation.config import load_config


# -----------------------------
# Main
# -----------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List NotebookLM sources for a notebook.")
    parser.add_argument(
        "--notebook-id",
        default=None,
        help="Override the NotebookLM notebook ID used for listing sources.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Return sources as JSON for programmatic consumers.",
    )
    return parser


async def main() -> None:
    args = build_parser().parse_args()
    config = load_config(notebook_id=args.notebook_id)

    if not config.default_notebook_id:
        raise ValueError(
            "DEFAULT_NOTEBOOK_ID is missing from .env. Set it before running list_sources.py."
        )

    async with await NotebookLMClient.from_storage(str(config.auth_storage_path)) as client:
        sources = await client.sources.list(config.default_notebook_id)
        source_rows = [
            {
                "id": src.id,
                "title": src.title,
                "kind": src.kind,
            }
            for src in sources
        ]

        if args.json:
            print(json.dumps(source_rows))
            return

        print(f"Found {len(sources)} sources:\n")

        for index, src in enumerate(sources, start=1):
            print(f"{index}.")
            print(f"   id:    {src.id}")
            print(f"   title: {src.title}")
            print(f"   kind:  {src.kind}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
