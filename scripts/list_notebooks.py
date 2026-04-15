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
    parser = argparse.ArgumentParser(description="List available NotebookLM notebooks.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Return notebooks as JSON for programmatic consumers.",
    )
    return parser


async def main() -> None:
    args = build_parser().parse_args()
    config = load_config()

    async with await NotebookLMClient.from_storage(str(config.auth_storage_path)) as client:
        notebooks = await client.notebooks.list()
        notebook_rows = [
            {
                "id": nb.id,
                "title": getattr(nb, "title", "(Untitled notebook)"),
            }
            for nb in notebooks
        ]

        if args.json:
            print(json.dumps(notebook_rows))
            return

        print(f"Found {len(notebooks)} notebooks:\n")

        for index, notebook in enumerate(notebook_rows, start=1):
            print(f"{index}.")
            print(f"   id:    {notebook['id']}")
            print(f"   title: {notebook['title']}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
