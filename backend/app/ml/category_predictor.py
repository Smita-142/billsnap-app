class CategoryPredictor:
    async def predict(self, sanitized_text: str) -> dict:
        raise NotImplementedError("Category prediction is not configured.")
