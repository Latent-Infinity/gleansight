from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from papers.app import ports
from papers.domain.errors import ErrorCode, PipelineError


@dataclass(frozen=True)
class SentenceTransformerEmbedder(ports.Embedder):
    model_name_value: str
    dimension_value: int
    embed_func: Callable[[str], list[float]]

    def model_name(self) -> str:
        return self.model_name_value

    def dimension(self) -> int:
        return self.dimension_value

    def embed(self, text: str) -> list[float]:
        return self.embed_func(text)


def build_sentence_transformer_embedder(model_name: str) -> SentenceTransformerEmbedder:
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise PipelineError(
            ErrorCode.EMBEDDING_FAILED,
            "sentence-transformers not installed",
        ) from exc

    model = SentenceTransformer(model_name)
    dimension = model.get_sentence_embedding_dimension()

    def _embed(text: str) -> list[float]:
        return model.encode(text, normalize_embeddings=False).tolist()

    return SentenceTransformerEmbedder(
        model_name_value=model_name,
        dimension_value=dimension,
        embed_func=_embed,
    )
