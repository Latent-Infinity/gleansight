from pathlib import Path

from pydantic import JsonValue

from papers.app.ports import ConverterResult, LLMResponse
from papers.infra.lancedb.index import LanceDBConfig


class Embedder:
    def model_name(self) -> str:
        return "fake"

    def dimension(self) -> int:
        return 1

    def embed(self, text: str) -> list[float]:
        return [float(len(text))]


class Converter:
    def version(self) -> str:
        return "fake-v1"

    def pdf_to_markdown(self, pdf_path: Path) -> ConverterResult:
        return ConverterResult(
            True, "# Adaptive learning\n" + "Evidence from a local PDF. " * 10, None, None
        )


class Index:
    """Isolated in-memory provider used to exercise application integration."""

    def __init__(self, config: LanceDBConfig) -> None:
        self.vectors: dict[str, list[float]] = {}

    def reset(self) -> None:
        self.vectors.clear()

    def upsert(self, paper_id: str, embedding: list[float]) -> None:
        self.vectors[paper_id] = embedding

    def query(
        self, embedding: list[float], limit: int, *, allowed_ids: set[str] | None = None
    ) -> list[tuple[str, float]]:
        return [(key, 1.0) for key in self.vectors if allowed_ids is None or key in allowed_ids][
            :limit
        ]


class LLM:
    def __init__(self) -> None:
        self.responses: list[str] = []

    def complete(
        self,
        *,
        prompt: str,
        profile: dict[str, JsonValue],
        model: str,
        timeout_s: int | None = None,
    ) -> LLMResponse:
        return LLMResponse(
            self.responses.pop(0) if self.responses else "Grounded answer", 10, 5, None
        )


class Scholar:
    def search(
        self,
        query: str,
        filters: dict[str, JsonValue],
        max_results: int,
        page_size: int,
        offset: int = 0,
    ) -> list[dict[str, JsonValue]]:
        return [
            {
                "source_paper_id": f"s2-{offset}",
                "title": "Discovered locally",
                "authors": [],
                "external_ids": {"DOI": "10.123/fake"},
            }
        ]
