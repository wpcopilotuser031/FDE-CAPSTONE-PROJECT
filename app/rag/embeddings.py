import hashlib
from typing import Iterable


class HashEmbeddingFunction:
    """Deterministic local embedding to avoid external model downloads."""

    def __init__(self, dimension: int = 128) -> None:
        self.dimension = dimension

    @staticmethod
    def name() -> str:
        return "hash-embedding"

    @staticmethod
    def build_from_config(config: dict) -> "HashEmbeddingFunction":
        return HashEmbeddingFunction(dimension=config.get("dimension", 128))

    def get_config(self) -> dict:
        return {"dimension": self.dimension}

    @staticmethod
    def default_space() -> str:
        return "cosine"

    @staticmethod
    def supported_spaces() -> list[str]:
        return ["cosine", "l2", "ip"]

    @staticmethod
    def is_legacy() -> bool:
        return False

    def _embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            vector[index] += 1.0

        norm = sum(value * value for value in vector) ** 0.5
        if norm > 0:
            vector = [value / norm for value in vector]
        return vector

    def __call__(self, input: Iterable[str]) -> list[list[float]]:
        return [self._embed_text(text) for text in input]
