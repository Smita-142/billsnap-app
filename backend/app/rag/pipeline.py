class BillQuestionPipeline:
    def __init__(self, sql_analytics, retriever, answer_model):
        self.sql_analytics = sql_analytics
        self.retriever = retriever
        self.answer_model = answer_model

    async def ask(self, question: str, user_id: str) -> dict:
        raise NotImplementedError("The SQL plus RAG answer pipeline is not enabled.")
