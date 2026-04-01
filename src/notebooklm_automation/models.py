from dataclasses import dataclass


@dataclass(frozen=True)
class Concept:
    name: str
    notebook_id: str | None = None
    source_ids: list[str] | None = None


@dataclass(frozen=True)
class PromptTemplate:
    key: str
    title: str
    filename: str
    raw_text: str

    def render(self, concept: str) -> str:
        """
        Replace supported concept placeholders in the prompt template.
        """
        rendered = self.raw_text

        # Support your current prompt style
        rendered = rendered.replace("[Concept Name]", concept)

        # Also support the newer placeholder style
        rendered = rendered.replace("{concept}", concept)

        return rendered
