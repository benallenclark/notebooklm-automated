# -----------------------------
# Imports
# -----------------------------
from typing import Any


# -----------------------------
# NotebookLM abstraction
# -----------------------------
class NotebookLMService:
    """
    Thin wrapper around notebooklm-py.

    Why this exists:
    - keeps third-party library calls in one place
    - makes future replacement easier
    - avoids leaking dependency details across your whole codebase
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    async def ask(
        self,
        notebook_id: str,
        prompt: str,
        source_ids: list[str] | None = None,
    ) -> str:
        """
        Send one prompt to one notebook and return the answer text.
        """
        result = await self._client.chat.ask(
            notebook_id,
            prompt,
            source_ids=source_ids,
        )

        answer = getattr(result, "answer", None)

        if not answer or not str(answer).strip():
            raise RuntimeError("NotebookLM returned an empty answer.")

        return str(answer).strip()
