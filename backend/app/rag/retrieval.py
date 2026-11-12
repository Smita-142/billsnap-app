class BillRetriever:
    async def retrieve(self, question: str, user_id: str) -> list[dict]:
        raise NotImplementedError("Retrieval is disabled until sanitized bill text and an authorized vector store are configured.")
