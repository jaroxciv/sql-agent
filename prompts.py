class PromptManager:
    def __init__(self, prompts: dict):
        self.prompts = prompts

    def sql_prompt(self, db, schema, question, followup_context, filters, examples):
        return self.prompts["sql"].format(
            db=db,
            schema=schema,
            question=question,
            followup_context=followup_context,
            filters=filters,
            examples=examples,
        )

    def memory_prompt(self, question, summary):
        return self.prompts["memory"].format(question=question, summary=summary)

    def summary_prompt(self, question, sql_query, query_result):
        return self.prompts["summary"].format(
            question=question, sql_query=sql_query, query_result=query_result
        )

    def relevance_prompt(self, question, schema):
        return self.prompts["relevance"].format(schema=schema, question=question)
