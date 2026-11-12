class EmbeddingService:
    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError("Embeddings are disabled until sanitized bill text is available.")
