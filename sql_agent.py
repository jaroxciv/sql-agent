"""Module defining a LangGraph‑based SQL agent with checkpointed memory.

This module exposes a single function, :func:`create_sql_agent`, which
constructs a LangGraph graph that can translate natural language questions
about a SQL database into executable SQL, execute those queries and persist
its state between invocations.  The resulting graph, when invoked with a
`thread_id`, will remember previous interactions thanks to the SQLite‑backed
checkpointer.
"""

from __future__ import annotations

import sqlite3
from typing import Dict, Literal

from langchain.chat_models import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.prebuilt import ToolNode

# Import the SqliteSaver checkpointer from langgraph‑checkpoint‑sqlite.  This
# package needs to be installed separately from langgraph itself.  Using a
# SQLite backend gives the agent persistent memory across sessions.  For
# temporary in‑memory checkpoints you can import InMemorySaver from
# langgraph.checkpoint.memory instead.
from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore
from langchain_core.runnables.graph import CurveStyle, MermaidDrawMethod, NodeStyles
import io
from contextlib import redirect_stdout


def create_sql_agent(
    llm: ChatOpenAI,
    db_uri: str,
    state_path: str,
    top_k: int = 5,
):
    """Create a SQL agent graph and its associated database instance.

    Parameters
    ----------
    llm : ChatOpenAI
        The chat model used to generate tool calls and responses.
    db_uri : str
        SQLAlchemy‑style URI pointing at the database (e.g. ``sqlite:///Chinook.db``).
    state_path : str
        Path to a SQLite file used to persist graph state via checkpoints.
    top_k : int, optional
        Maximum number of rows to return when generating SQL queries, by default 5.

    Returns
    -------
    tuple
        A two‑tuple ``(graph, db)`` where ``graph`` is a compiled
        LangGraph instance and ``db`` is the underlying :class:`SQLDatabase`.
    """
    # Initialize the SQL database wrapper and obtain tools for interacting with it.
    db = SQLDatabase.from_uri(db_uri)
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    tools = toolkit.get_tools()

    # Extract individual tools by name.
    list_tables_tool = next(tool for tool in tools if tool.name == "sql_db_list_tables")
    get_schema_tool = next(tool for tool in tools if tool.name == "sql_db_schema")
    run_query_tool = next(tool for tool in tools if tool.name == "sql_db_query")

    # Define the node that lists the available tables.  This node calls the
    # ``sql_db_list_tables`` tool and returns an AI message summarizing the result.
    def list_tables(state: MessagesState) -> Dict[str, list]:
        tool_call = {
            "name": "sql_db_list_tables",
            "args": {},
            "id": "list_tables_call",
            "type": "tool_call",
        }
        tool_call_message = AIMessage(content="", tool_calls=[tool_call])
        # Invoke the tool synchronously; LangGraph will call this in a thread.
        tool_message = list_tables_tool.invoke(tool_call)
        response = AIMessage(content=f"Available tables: {tool_message.content}")
        return {"messages": [tool_call_message, tool_message, response]}

    # This node instructs the LLM to call the schema tool for the relevant tables.
    def call_get_schema(state: MessagesState) -> Dict[str, list]:
        llm_with_tools = llm.bind_tools([get_schema_tool], tool_choice="any")
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    # System prompt for generating a SQL query.  It describes how to form queries
    # and includes instructions to limit results and avoid dangerous operations.
    generate_query_prompt = f"""
    You are an agent designed to interact with a SQL database.
    Given an input question, create a syntactically correct {db.dialect} query to run,
    then look at the results of the query and return the answer. Unless the user
    specifies a specific number of examples they wish to obtain, always limit your
    query to at most {top_k} results.

    You can order the results by a relevant column to return the most interesting
    examples in the database. Never query for all the columns from a specific table,
    only ask for the relevant columns given the question.

    DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.) to the
    database.
    """

    def generate_query(state: MessagesState) -> Dict[str, list]:
        system_message = {"role": "system", "content": generate_query_prompt}
        # Bind the run_query_tool but allow the LLM to decide whether to call it.
        llm_with_tools = llm.bind_tools([run_query_tool])
        response = llm_with_tools.invoke([system_message] + state["messages"])
        return {"messages": [response]}

    # System prompt to double check SQL.  If mistakes are detected, the model will
    # rewrite the query; otherwise it simply repeats the original.
    check_query_prompt = f"""
    You are a SQL expert with a strong attention to detail.
    Double check the {db.dialect} query for common mistakes, including:
    - Using NOT IN with NULL values
    - Using UNION when UNION ALL should have been used
    - Using BETWEEN for exclusive ranges
    - Data type mismatch in predicates
    - Properly quoting identifiers
    - Using the correct number of arguments for functions
    - Casting to the correct data type
    - Using the proper columns for joins

    If there are any of the above mistakes, rewrite the query. If there are no
    mistakes, just reproduce the original query.

    You will call the appropriate tool to execute the query after running this
    check.
    """

    def check_query(state: MessagesState) -> Dict[str, list]:
        system_message = {"role": "system", "content": check_query_prompt}
        # The last message contains a tool call with the generated query.
        last_msg = state["messages"][-1]
        tool_call = last_msg.tool_calls[0]
        user_message = {"role": "user", "content": tool_call["args"]["query"]}
        llm_with_tools = llm.bind_tools([run_query_tool], tool_choice="any")
        response = llm_with_tools.invoke([system_message, user_message])
        # Preserve the tool call identifier so the next node associates it correctly.
        response.id = last_msg.id
        return {"messages": [response]}

    # Build the graph by adding nodes and connecting them.
    builder = StateGraph(MessagesState)
    builder.add_node(list_tables)
    builder.add_node(call_get_schema)
    builder.add_node(ToolNode([get_schema_tool], name="get_schema"), "get_schema")
    builder.add_node(generate_query)
    builder.add_node(check_query)
    builder.add_node(ToolNode([run_query_tool], name="run_query"), "run_query")

    # Define the flow between nodes.  After listing tables, we get the schema,
    # generate a query, possibly check it and then run the query.
    builder.add_edge(START, "list_tables")
    builder.add_edge("list_tables", "call_get_schema")
    builder.add_edge("call_get_schema", "get_schema")
    builder.add_edge("get_schema", "generate_query")

    # At the generate_query node we either finish (if no tool call is present)
    # or proceed to check_query.  The presence of tool_calls indicates a query
    # has been produced.
    def should_continue(state: MessagesState) -> Literal[END, "check_query"]:
        last_message = state["messages"][-1]
        if not last_message.tool_calls:
            return END
        return "check_query"

    builder.add_conditional_edges("generate_query", should_continue)
    builder.add_edge("check_query", "run_query")
    builder.add_edge("run_query", "generate_query")

    # Compile the graph with a persistent checkpointer.  The SQLite saver stores
    # the state in a local file so the agent can remember across runs.
    checkpointer = SqliteSaver(sqlite3.connect(state_path))
    graph = builder.compile(checkpointer=checkpointer)

    # Save a visualization of the agent graph.
    # Note: The original request was to save a PNG image of the graph.
    # However, the required dependencies (py-mermaid, mermaid-cli) are not
    # available in the current environment. As a fallback, I'm saving the
    # graph in two formats:
    # 1. An ASCII art representation in `graph.txt`.
    # 2. A MermaidJS definition in `graph.mermaid`, which can be used to
    #    generate a diagram using online editors or local tools.
    with open("graph.txt", "w") as f:
        f.write(graph.get_graph().draw_ascii())

    with open("graph.png", "wb") as f:
        try:
            f.write(graph.get_graph().draw_mermaid_png())
        except Exception as e:
            # As a fallback, save the mermaid diagram definition
            with open("graph.mermaid", "w") as f_mermaid:
                f_mermaid.write(graph.get_graph().draw_mermaid())
            # also write a text file explaining the situation
            with open("graph.txt", "w") as f_text:
                f_text.write("Could not generate graph.png. Please use graph.mermaid to generate the diagram.\n\n")
                f_text.write(str(e))
                f_text.write("\n\nAscii representation:\n\n")
                f_text.write(graph.get_graph().draw_ascii())


    return graph, db
