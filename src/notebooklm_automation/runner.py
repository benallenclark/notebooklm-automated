# -----------------------------
# Imports
# -----------------------------
import asyncio
import logging
import time

from notebooklm import NotebookLMClient
from notebooklm_automation.source_config import ACTIVE_SOURCE_IDS
from notebooklm_automation.config import AppConfig
from notebooklm_automation.models import Concept, PromptTemplate
from notebooklm_automation.notebooklm_service import NotebookLMService
from notebooklm_automation.storage import (
    append_manifest,
    append_prompt_section,
    build_concept_output_path,
    initialize_concept_file,
)
from notebooklm_automation.template_loader import load_concepts, load_prompt_templates


# -----------------------------
# Runner
# -----------------------------
class StudyBatchRunner:
    """
    Orchestrates the full batch run:
    concepts x prompts -> NotebookLM -> one markdown file per concept
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.logger = logging.getLogger(__name__)

    async def run(
        self,
        limit_concepts: int | None = None,
        limit_prompts: int | None = None,
        overwrite: bool = False,
        dry_run: bool = False,
    ) -> None:
        concepts = load_concepts(self.config.concepts_csv)
        prompts = load_prompt_templates(self.config.prompts_dir)

        if limit_concepts is not None:
            concepts = concepts[:limit_concepts]

        if limit_prompts is not None:
            prompts = prompts[:limit_prompts]

        total_concepts = len(concepts)
        total_prompts = len(prompts)

        self.logger.info("Loaded %s concepts and %s prompts.", total_concepts, total_prompts)

        if dry_run:
            self._print_dry_run_preview(concepts, prompts)
            return

        async with await NotebookLMClient.from_storage() as client:
            service = NotebookLMService(client)

            for concept_index, concept in enumerate(concepts, start=1):
                notebook_id = concept.notebook_id or self.config.default_notebook_id

                if not notebook_id:
                    raise ValueError(
                        f"No notebook ID found for concept '{concept.name}'. "
                        "Set DEFAULT_NOTEBOOK_ID in .env or provide notebook_id in the CSV."
                    )

                await self._run_concept(
                    service=service,
                    concept=concept,
                    prompts=prompts,
                    notebook_id=notebook_id,
                    overwrite=overwrite,
                    concept_index=concept_index,
                    total_concepts=total_concepts,
                    total_prompts=total_prompts,
                )

    async def _run_concept(
        self,
        service: NotebookLMService,
        concept: Concept,
        prompts: list[PromptTemplate],
        notebook_id: str,
        overwrite: bool,
        concept_index: int,
        total_concepts: int,
        total_prompts: int,
    ) -> None:
        concept_output_path = build_concept_output_path(self.config.output_dir, concept)

        if concept_output_path.exists() and not overwrite:
            self.logger.info(
                "[Concept %s/%s] %s | skipping existing file",
                concept_index,
                total_concepts,
                concept.name,
            )
            return

        self.logger.info(
            "[Concept %s/%s] %s | starting",
            concept_index,
            total_concepts,
            concept.name,
        )

        initialize_concept_file(concept_output_path, concept)

        for prompt_index, prompt in enumerate(prompts, start=1):
            rendered_prompt = prompt.render(concept.name)

            success = False
            last_error: str | None = None
            total_attempts = self.config.retries + 1

            for attempt in range(1, total_attempts + 1):
                retries_left = total_attempts - attempt

                try:
                    self.logger.info(
                        "[Concept %s/%s] %s | [Prompt %s/%s] %s | attempt %s/%s | retries left: %s",
                        concept_index,
                        total_concepts,
                        concept.name,
                        prompt_index,
                        total_prompts,
                        prompt.title,
                        attempt,
                        total_attempts,
                        retries_left,
                    )

                    started = time.perf_counter()

                    answer = await service.ask(
                        notebook_id,
                        rendered_prompt,
                        source_ids=ACTIVE_SOURCE_IDS,
                    )

                    elapsed = time.perf_counter() - started

                    append_prompt_section(
                        output_path=concept_output_path,
                        prompt=prompt,
                        rendered_prompt=rendered_prompt,
                        answer=answer,
                    )

                    append_manifest(
                        output_dir=self.config.output_dir,
                        concept=concept,
                        prompt=prompt,
                        status="success",
                        output_path=concept_output_path,
                    )

                    self.logger.info(
                        "[Concept %s/%s] %s | [Prompt %s/%s] %s | success in %.1fs",
                        concept_index,
                        total_concepts,
                        concept.name,
                        prompt_index,
                        total_prompts,
                        prompt.title,
                        elapsed,
                    )

                    success = True
                    break

                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                    self.logger.exception(
                        "[Concept %s/%s] %s | [Prompt %s/%s] %s | attempt %s/%s | failed | %s",
                        concept_index,
                        total_concepts,
                        concept.name,
                        prompt_index,
                        total_prompts,
                        prompt.title,
                        attempt,
                        total_attempts,
                        last_error,
                    )

                    if retries_left > 0:
                        await asyncio.sleep(self.config.delay_seconds)

            if not success:
                append_manifest(
                    output_dir=self.config.output_dir,
                    concept=concept,
                    prompt=prompt,
                    status="failed",
                    output_path=concept_output_path,
                    error=last_error,
                )

                self.logger.error(
                    "[Concept %s/%s] %s | [Prompt %s/%s] %s | final failure",
                    concept_index,
                    total_concepts,
                    concept.name,
                    prompt_index,
                    total_prompts,
                    prompt.title,
                )

            await asyncio.sleep(self.config.delay_seconds)

    def _print_dry_run_preview(
        self,
        concepts: list[Concept],
        prompts: list[PromptTemplate],
    ) -> None:
        total_concepts = len(concepts)
        total_prompts = len(prompts)

        for concept_index, concept in enumerate(concepts, start=1):
            concept_output_path = build_concept_output_path(self.config.output_dir, concept)
            self.logger.info(
                "[DRY RUN] [Concept %s/%s] %s | prompts=%s | output=%s",
                concept_index,
                total_concepts,
                concept.name,
                total_prompts,
                concept_output_path,
            )
