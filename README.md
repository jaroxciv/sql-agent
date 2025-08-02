# SQL Agent with LangGraph

This repository demonstrates how to build a SQL agent using **LangGraph**, a
framework for orchestrating large language models via graphs.  The agent
translates natural‑language questions into SQL, executes the queries against
a database and persists its conversation state between interactions using
LangGraph’s checkpointing framework.  Because the agent stores its state after
each step, you can ask follow‑up questions in the same thread and it will
remember prior context.

## Features

- Implements a text‑to‑SQL agent using the LangGraph graph API.
- Persists short‑term memory between interactions via a SQLite‑backed
  checkpointer (`SqliteSaver`).
- Interactive command‑line interface for asking questions over a SQL database.
- Compatible with any chat model supporting tool calling (e.g. OpenAI GPT‑4).
- Includes example configuration for the [`Chinook`](https://www.sqlitetutorial.net/sqlite-sample-database/) sample database.

## Installation

This project requires **Python 3.10+**.

1. Clone the repository and change into its directory:

   ```bash
   git clone https://github.com/jaroxciv/sql-agent.git
   cd sql-agent
   ```

2. Install the dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Set your chat model API key as an environment variable.  The example code
   uses OpenAI models, so you’ll need an `OPENAI_API_KEY`:

   ```bash
   export OPENAI_API_KEY=sk-...
   ```

4. Download a SQLite database.  To follow along with the example you can
   download the **Chinook** sample database:

   ```bash
   python -c "import requests; url='https://storage.googleapis.com/benchmarks-artifacts/chinook/Chinook.db'; open('Chinook.db','wb').write(requests.get(url).content)"
   ```

## Usage

Run the interactive CLI using the database you downloaded:

```bash
python app.py --db-uri sqlite:///Chinook.db --state-path state.db
```

On the first run the program creates a small `state.db` file to persist
the agent’s memory.  Use the same `--state-path` and `--thread-id` for
subsequent runs to continue a conversation.

Once started you can type natural language questions about the data.  For
example:

```
Which genre on average has the longest tracks?
```

The agent will translate your question into SQL, execute the query and
return the result.  Thanks to the checkpointer, you can ask follow‑up
questions without losing context:

```
What about the shortest tracks?
```

## Architecture

The agent is implemented in `sql_agent.py` using the LangGraph graph API.  It
defines several nodes:

- **list_tables** – calls the `sql_db_list_tables` tool to obtain the available
  tables.
- **call_get_schema** – instructs the chat model to call the schema tool for
  relevant tables.
- **get_schema** – runs the `sql_db_schema` tool to fetch table schemas.
- **generate_query** – asks the chat model to propose a SQL query using the
  `sql_db_query` tool.
- **check_query** – double‑checks and rewrites the SQL if necessary using the
  `sql_db_query_checker` tool.
- **run_query** – executes the final SQL query.

These nodes are connected with conditional edges so that invalid queries are
corrected.  The graph is compiled with a checkpointer:

```python
checkpointer = SqliteSaver(sqlite3.connect(state_path))
agent = builder.compile(checkpointer=checkpointer)
```

When you invoke the agent you must supply a `thread_id` in the configuration.
The agent stores its state after each super‑step.  On subsequent calls with
the same `thread_id` it resumes from the previous state, providing
short‑term memory for your application.

See `sql_agent.py` and `app.py` for implementation details.
