# -----------------------------
# Imports
# -----------------------------
import asyncio
from notebooklm import NotebookLMClient

# -----------------------------
# Config
# -----------------------------
NOTEBOOK_ID = "d0a422ec-7d41-4dec-946d-ce378e6151af"
AUTH_STORAGE_PATH = ".notebooklm_state/storage_state.json"


# -----------------------------
# Main
# -----------------------------
async def main() -> None:
    async with await NotebookLMClient.from_storage(AUTH_STORAGE_PATH) as client:
        sources = await client.sources.list(NOTEBOOK_ID)

        print(f"Found {len(sources)} sources:\n")

        for index, src in enumerate(sources, start=1):
            print(f"{index}.")
            print(f"   id:    {src.id}")
            print(f"   title: {src.title}")
            print(f"   kind:  {src.kind}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
