# 🛰️ AI SQL Analytics Chatbot — Chinook Demo

**Chat with your Postgres database and get actionable business insights powered by LLMs!**  
This project demonstrates a modern, modular AI SQL assistant using the classic Chinook dataset, Postgres, Streamlit, and OpenAI/Mistral LLMs — engineered for clarity, extensibility, and real business value.

---

## 🚀 Features

- **Conversational SQL Analytics**  
  Ask questions in natural language and get both the SQL query and a manager-ready summary.

- **Advanced Prompt Engineering**  
  Customizable prompt templates with examples and detailed schema notes, reducing hallucination.

- **Memory & Context Handling**  
  Postgres-backed LangGraph checkpointer for LLM session memory (no stateless chat!).

- **Schema Extraction**  
  Automated extraction of tables, columns, and sample values using Pydantic models.

- **Production-Ready Architecture**  
  - Modular agent and prompt manager classes  
  - Dockerized Postgres with PgAdmin for easy setup  
  - Extensible LLM client system (supports OpenAI, Mistral, etc.)  
  - Secure config via `.env`

- **Plug-and-play for your own data**  
  Swap in your schema or connect a new database — agent will adapt!

---

## 🖼️ Demo

**Example 1: Who was the top sales agent by total invoice sales in 2023?**

<details>
  <summary>Show Answer</summary>

  **Summarized Analysis:**
  - The top sales agent by total invoice sales in 2023 is Jane Peacock with a total sales amount of 184.34.
  - The second-highest is Steve Johnson (159.47).
  - The third is Margaret Park (125.77).

  **Insights & Implications:**
  - Jane Peacock's performance significantly outpaces her peers, suggesting effective sales strategies or a strong customer base.
  - The gap highlights where targeted training could help.
</details>

**Example 2: Which playlist contains the highest number of tracks, and how many tracks does it have?**

<details>
  <summary>Show Answer</summary>

  **Summarized Analysis:**
  - "Music" playlist: 3290 tracks (the largest by far)
  - "90’s Music": 1477 tracks
  - "TV Shows": 213 tracks
  - Several others with 1–75 tracks

  **Insights & Implications:**
  - The "Music" playlist dominates and could be leveraged for promotions or user engagement.
</details>

**Example 3: List all customers from Brazil, including their full names and total amount spent.**

<details>
  <summary>Show Answer</summary>

  **Summarized Analysis:**
  - 5 customers from Brazil
  - Most have spent 37.62; one spent 39.62

  **Insights & Implications:**
  - Consistent spending pattern, opportunity for targeted upselling.
</details>

---

## 🛠️ Quickstart

### 1. Clone & Install

```bash
git clone https://github.com/jaroxciv/sql-agent.git
cd sql-agent

# Initialize uv project and virtual environment
uv init
uv venv

# Activate the virtual environment
# On Unix/Mac:
source .venv/bin/activate
# On Windows (Command Prompt):
.venv\Scripts\activate
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# Sync dependencies
uv sync
```

### 2. Run the Dockerized Database


```bash
cd docker
docker compose up -d --build
```

### 3. Configure `.env`

```bash
DB_TYPE=postgresql
DB_HOST=localhost
DB_PORT=5432
DB_USER=chinook
DB_PASSWORD=chinook
DB_NAME=chinook
LLM_API_KEY=sk-...          # Your OpenAI or Mistral API key
LLM_MODEL=gpt-4o            # Or your preferred model
MEMORY_SCHEMA=public
MAX_ROWS=30
```

### 4. Launch the App

```bash
streamlit run app.py
```

Open [localhost:8501](http://localhost:8501/) in your browser.

### ⚡ Architecture

```text
docker/
  ├─ docker-compose.yaml       # Spins up Postgres + PgAdmin
  ├─ init.sql                  # Chinook database schema/data
llm_clients/                   # Swappable LLM client classes (OpenAI, Mistral, etc.)
agents.py                      # Modular SQL Agent logic
app.py                         # Streamlit UI
data_models.py                 # Pydantic schema models for safe/clear DB introspection
db_knowledge.py                # Chinook table relationships & example queries
default_prompts.json           # Prompt templates with schema, notes, examples
llm_memory.py                  # Postgres-backed session memory
prompts.py                     # Prompt manager to inject into Langgraph nodes
requirements.txt
utils.py                       # Data dictionary extraction, prompt loading, etc.
```

### 🧠 Extending or Adapting

- Change to your own database:

Update init.sql, .env, and re-extract the schema (see extract_data_dictionary).

- Switch LLM:

Add a client in llm_clients/ and set in .env.

- Add prompt templates or demo examples:

Update default_prompts.json and db_notes.py.

- Production deploy:

Add HTTPS, secrets management, and cloud hosting as needed.

### 📄 License & Attribution

- Chinook sample db by [lerocha](https://github.com/lerocha/chinook-database)
- Made with ❤️ by Javi Alfaro