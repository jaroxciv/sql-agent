import json
import time
import functools
import traceback
import time
import functools
import traceback
from typing import List, Dict, Any, Optional
from sqlalchemy import Engine, text

from prompts import PromptManager
from data_models import format_schema_for_prompt, serialize_filters

from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from langmem.short_term import SummarizationNode
from langgraph.graph import StateGraph, MessagesState


# 🔁 Shared State
class AgentState(MessagesState):
    question: str
    sql_query: str
    query_result: List[Dict[str, Any]]
    query_result_str: str
    answer: str
    summary: str
    data_dictionary_json: str
    is_error: bool = False
    prev_question: str = ""
    prev_sql: str = ""
    prev_summary: str = ""
    error_type: str = None
    error_message: str = None
    traceback: str = None


def measure_node_time(node_fn):
    """
    Decorator to log execution time of agent nodes using logger.debug().
    """
    @functools.wraps(node_fn)
    def wrapper(self, state: AgentState, *args, **kwargs):
        start = time.time()
        result = node_fn(self, state, *args, **kwargs)
        elapsed = time.time() - start
        node_name = node_fn.__name__
        self.logger.debug(f"Node [{node_name}] executed in {elapsed:.3f} seconds.")
        return result
    return wrapper

def handle_node_errors(node_fn):
    """
    Decorator for standardizing error responses from agent nodes.
    Captures function name, exception details, and original state.
    """
    @functools.wraps(node_fn)
    def wrapper(self, state: AgentState, *args, **kwargs):
        try:
            return node_fn(self, state, *args, **kwargs)
        except Exception as e:
            fn_name = node_fn.__name__
            err_msg = f"[{fn_name}] Error: {e}"
            tb = traceback.format_exc()
            self.logger.error(f"{err_msg}\n{tb}")
            # Return a full update, not just error keys
            new_state = dict(state)
            new_state.update({
                "is_error": True,
                "error_type": fn_name + "_error",
                "error_message": str(e),
                "traceback": tb,
                "answer": f"Failed to execute: [{fn_name}] - {e}"
            })
            return new_state
    return wrapper

class SQLAgent:

    def __init__(
            self,
            llm_client,
            llm_maxrows: int,
            llm_memory_checkpointer,
            prompts: dict,
            logger,
            sql_examples: str = "",
            ) -> None:

        self.llm_client = llm_client
        self.max_rows = llm_maxrows
        self.checkpointer = llm_memory_checkpointer
        self.prompt_manager = PromptManager(prompts or {})
        self.logger = logger
        self.sql_examples = sql_examples

        self.summarization_node = SummarizationNode(
            token_counter=count_tokens_approximately,
            model=self.llm_client,
            max_tokens=self.llm_client.context_window_size, # Full context window for the model
            max_tokens_before_summary=int(self.llm_client.context_window_size * 0.1),  # Summarize after 10% of context window
            max_summary_tokens=2048, # Each summary capped at 2048 tokens (needs testing)
        )
    
    def relevance_router(self, state: AgentState):
        return state

    @measure_node_time
    def continue_to(self, state: AgentState):
        """
        Determines the next node in the workflow:
        - If user SQL is present, skip SQL generation.
        - Else, route via LLM-based relevance classification.
        - On error, defaults to memory response.
        """
        self.logger.debug(f"[continue_to] Question: {state.get('question')}")
        # # 1. User-provided SQL takes priority
        # if state.get("sql_query"):
        #     self.logger.debug("[continue_to] sql_query detected in state; routing to execute_query.")
        #     return "execute_query"
        # 2. Otherwise, use LLM to classify question relevance
        try:
            self.logger.debug(
                f"[continue_to] No sql_query; running relevance check for: {state.get('question')}"
                )
            data_dictionary_json = state.get("data_dictionary_json", "")
            _, formatted_schema = format_schema_for_prompt(data_dictionary_json)
            prompt = self.prompt_manager.relevance_prompt(
                schema=formatted_schema, question=state["question"]
                )
            messages = [SystemMessage(content=prompt)]
            response = self.llm_client.complete(messages)
            classification = response.content.strip().lower()
            self.logger.info(f"[continue_to] [Relevance Check]: {classification}")
            return "write_query" if classification == "relevant" else "generate_memory_response"
        except Exception as e:
            # Router node should always return a string
            # Log the error but return a default path
            self.logger.error(
                f"[continue_to] Exception: {e}. Defaulting to generate_memory_response.",
                exc_info=True
                )
            return "generate_memory_response"

    @measure_node_time
    @handle_node_errors
    def write_query(self, state: AgentState):

        if not state.get("data_dictionary_json"):
            raise ValueError("No data dictionary provided.")

        data_dictionary_json = state.get("data_dictionary_json", "")
        db, formatted_schema = format_schema_for_prompt(data_dictionary_json)

        filter_models = state.get("filters", [])
        filters_block = serialize_filters(filter_models)

        followup_context = ""
        if state.get("prev_question"):
            self.logger.info("[Write Query]: Using previous context for follow-up.")
            followup_context = (
                f"Previous question: {state.get('prev_question', '')}\n"
                f"Previous SQL: {state.get('prev_sql', '')}\n"
                f"Previous summary: {state.get('prev_summary', '')}\n"
                )

        sql_prompt = self.prompt_manager.sql_prompt(
            db=db, 
            schema=formatted_schema, 
            question=state["question"],
            followup_context=followup_context,
            filters=filters_block,
            examples=self.sql_examples,
            )

        messages = [
            SystemMessage(content=f"You are a {db} SQL expert. Follow all instructions strictly."),
            HumanMessage(content=sql_prompt)
        ]

        response = self.llm_client.complete(messages)
        raw_content = response.content.strip()
        cleaned_sql = (
            raw_content
            .replace("```", "")
            .replace("sql", "")
            .replace("SQL", "")
            .strip()
            )
        self.logger.debug(f"[write_query] SQL Query: {cleaned_sql}")

        return {
            "sql_query": cleaned_sql,
            "messages": [
                HumanMessage(content=state["question"]),
                AIMessage(content=raw_content)
                ],
            "is_error": False
        }

    @measure_node_time
    @handle_node_errors
    def execute_query(self, state: AgentState):
        with self.data_engine.connect() as conn:
            result = conn.execute(text(state["sql_query"]))
            rows = result.fetchall()

            # Use _mapping for cleaner dict conversion
            json_rows = [dict(row._mapping) for row in rows]
            self.logger.debug(f"[execute_query] Retrieved {len(json_rows)} rows.")

            # TRUNCATE for LLM
            truncated_rows = json_rows[:self.max_rows]
            total = len(json_rows)
            formatted_json_str = json.dumps(truncated_rows, indent=2, default=str)

            if total > self.max_rows:
                formatted_json_str += (
                    f"\n... [truncated: showing first {self.max_rows} of {total} rows]"
                )

            return {
                "query_result": json_rows,
                "query_result_str": formatted_json_str,
                "is_error": False
            }

    @measure_node_time
    @handle_node_errors
    def generate_summary(self, state: AgentState):
        prompt = self.prompt_manager.summary_prompt(
            question=state.get("question", ""),
            sql_query=state.get("sql_query", "N/A"),
            query_result=state.get("query_result_str", "No result")
        )
        messages = [SystemMessage(content=prompt)]
        response = self.llm_client.complete(messages=messages)
        content = response.content.strip()
        self.logger.debug(f"[generate_summary] Interpretation: {content}")

        return {
            "answer": content,
            "messages": [AIMessage(content=content)],
            "is_error": False,
            "prev_question": state.get("question", ""),
            "prev_sql": state.get("sql_query", ""),
            "prev_summary": content
        }

    @measure_node_time
    @handle_node_errors
    def generate_memory_response(self, state: AgentState):

        if not state.get("data_dictionary_json"):
            raise ValueError("No data dictionary provided.")

        prompt = self.prompt_manager.memory_prompt(
            state["question"], state.get("summary", "")
        )
        # Let SummarizationNode handle summarization/triggering
        summarized_state = self.summarization_node.invoke({"messages": state["messages"]})
        summarized_messages = summarized_state["summarized_messages"]

        # Debug: Print if summarization occurred
        if len(summarized_messages) < len(state["messages"]):
            self.logger.debug(f"[Memory Node]: Summarization occurred. "
                f"Messages reduced from {len(state['messages'])} to {len(summarized_messages)}.")
        else:
            self.logger.debug("[Memory Node]: No summarization performed.")

        # Add the prompt as the last HumanMessage
        messages = summarized_messages + [HumanMessage(content=prompt)]
        response = self.llm_client.complete(messages=messages)
        content = response.content.strip()
        self.logger.debug(f"[generate_memory_response] Interpretation: {content}")

        return {
            "answer": content,
            "messages": messages + [AIMessage(content=content)],
            "is_error": False,
            # carry forward previous context, do not update
            "prev_question": state.get("prev_question", ""),
            "prev_sql": state.get("prev_sql", ""),
            "prev_summary": state.get("prev_summary", ""),
        }

    @measure_node_time
    @handle_node_errors
    def assign_tags(self, state: AgentState):
        # Build the session history as a string
        session_history = state['messages'] ### TODO: optimise
        prompt = self.prompt_manager.tag_prompt(
            session_history=session_history,
            tag_list=self.tag_list,
            max_tags=self.max_tags
            )
        response = self.llm_client.complete([SystemMessage(content=prompt)])
        tags = []
        try:
            tags = [
                line.strip() for line in response.content.strip().splitlines() if line.strip()
                ]
            if self.max_tags > 0:
                tags = tags[:self.max_tags]
            self.logger.debug(f"[assign_tags] Tags generated: {tags}")
        except Exception as e:
            self.logger.error(f"[assign_tags] Failed to parse tags: {e}")
            tags = []

        state["tags"] = tags
        return state

    def build(self):
        builder = StateGraph(AgentState)
        builder.add_node("relevance_router", self.relevance_router)
        builder.add_node("write_query", self.write_query)
        builder.add_node("execute_query", self.execute_query)
        builder.add_node("generate_summary", self.generate_summary)
        builder.add_node("generate_memory_response", self.generate_memory_response)
        
        builder.set_entry_point("relevance_router")
        builder.add_conditional_edges("relevance_router", self.continue_to, {
            "write_query": "write_query",
            "execute_query": "execute_query",
            "generate_memory_response": "generate_memory_response"
        })

        builder.add_edge("write_query", "execute_query")
        builder.add_edge("execute_query", "generate_summary")

        builder.set_finish_point("generate_summary")
        builder.set_finish_point("generate_memory_response")

        return builder.compile(checkpointer=self.checkpointer)

    def run_with_input(
            self, 
            question: str, 
            session_id: str, 
            data_dictionary_json: str, 
            datasource_engine: Engine,
            ) -> dict:
        
        start = time.time()
        self.data_engine = datasource_engine
        
        graph = self.build()
        input_state = {
            "question": question,
            "data_dictionary_json": data_dictionary_json,
        }

        config = {"configurable": {"thread_id": session_id}}
        output = graph.invoke(input_state, config=config)

        elapsed = time.time() - start
        self.logger.debug(f"Agent run completed in {elapsed:.3f} seconds.")
        
        return {
            "question": question,
            "sql_query": output.get("sql_query", ""),
            "query_result": output.get("query_result", []),
            "query_result_str": output.get("query_result_str", ""),
            "answer": output.get("answer", ""),
            "is_error": output.get("is_error", False),
            "error_type": output.get("error_type", None),
            "error_message": output.get("error_message", None),
            "traceback": output.get("traceback", None)
        }

