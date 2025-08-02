"""Command‑line interface for interacting with the SQL agent.

This script initializes the SQL agent graph, downloads or connects to the
specified database and enters an interactive loop.  It persists the
conversation state using the provided SQLite checkpoint file.  Run
`python app.py --help` for usage information.
"""
from __future__ import annotations

import argparse
import os
import uuid
from typing import Optional

from langchain.chat_models import ChatOpenAI

from sql_agent import create_sql_agent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an interactive SQL agent using LangGraph.")
    parser.add_argument(
        "--db-uri",
        type=str,
        required=True,
        help="SQLAlchemy database URI, e.g. sqlite:///Chinook.db",
    )
    parser.add_argument(
        "--state-path",
        type=str,
        default="state.db",
        help="Path to SQLite file used to persist the graph state (default: state.db).",
    )
    parser.add_argument(
        "--thread-id",
        type=str,
        default=None,
        help="Optional thread identifier to resume a previous conversation.  If omitted, a new one is generated.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-3.5-turbo-0125",
        help="Chat model identifier for LangChain's ChatOpenAI (default: gpt-3.5-turbo-0125).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Maximum number of rows to return when generating queries (default: 5).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Determine thread identifier.  Using a fixed thread ID across runs will
    # resume the same conversation.  Generate a random one otherwise.
    thread_id = args.thread_id or str(uuid.uuid4())

    # Initialize the chat model.  The OpenAI API key must be present in the
    # environment under OPENAI_API_KEY.  Other providers may be used by
    # adjusting the model and passing additional keyword arguments.
    llm = ChatOpenAI(model=args.model)

    # Create the SQL agent graph.  The ``create_sql_agent`` function
    # constructs the graph and returns both the compiled graph and the
    # underlying database instance (unused here but returned for completeness).
    graph, _db = create_sql_agent(
        llm=llm,
        db_uri=args.db_uri,
        state_path=args.state_path,
        top_k=args.top_k,
    )

    print(f"Connected to {args.db_uri}")
    print(f"Conversation thread ID: {thread_id}")
    print("Type 'exit' or press Ctrl+D to quit.\n")

    # Main REPL loop.  Each iteration sends the user's question into the graph
    # and streams back intermediate steps.  The final assistant response is
    # printed after the graph completes.
    while True:
        try:
            question = input("User> ")
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if question.strip().lower() in {"exit", "quit"}:
            break

        # Invoke the graph.  We use ``stream`` so that all intermediate steps
        # execute and the state is persisted.  Only the assistant messages
        # (non-tool messages) are printed at the end.
        events = graph.stream(
            {"messages": [{"role": "user", "content": question}]},
            config={"configurable": {"thread_id": thread_id}},
            stream_mode="values",
        )

        final_answer: Optional[str] = None
        for step in events:
            last = step["messages"][-1]
            # Only capture assistant messages (content-bearing outputs).  Tool
            # messages carry database results and are not shown directly.
            if last.role == "assistant" and last.content:
                final_answer = last.content

        if final_answer:
            print(f"Assistant> {final_answer}\n")
        else:
            print("Assistant> (no response)\n")


if __name__ == "__main__":
    main()
