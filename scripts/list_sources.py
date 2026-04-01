# -----------------------------
# Imports
# -----------------------------
import asyncio

from notebooklm import NotebookLMClient
from notebooklm_automation.config import load_config


# -----------------------------
# Main
# -----------------------------
async def main() -> None:
    config = load_config()

    if not config.default_notebook_id:
        raise ValueError(
            "DEFAULT_NOTEBOOK_ID is missing from .env. Set it before running list_sources.py."
        )

    async with await NotebookLMClient.from_storage(str(config.auth_storage_path)) as client:
        sources = await client.sources.list(config.default_notebook_id)

        print(f"Found {len(sources)} sources:\n")

        for index, src in enumerate(sources, start=1):
            print(f"{index}.")
            print(f"   id:    {src.id}")
            print(f"   title: {src.title}")
            print(f"   kind:  {src.kind}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
