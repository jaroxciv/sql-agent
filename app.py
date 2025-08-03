import os
import uuid
import atexit
import streamlit as st
from loguru import logger
from dotenv import load_dotenv
from sqlalchemy import create_engine

from agents import SQLAgent
from db_knowledge import chinook_notes, sql_examples
from llm_clients import build_client
from utils import extract_data_dictionary, load_prompts
from llm_memory import build_checkpointer

# --- Streamlit & App Title ---
st.set_page_config(page_title="Chat with your Database", page_icon=":speech_balloon:")
st.title("Chat with your Database")

load_dotenv()

# --- DB credentials (Postgres only) ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "chinook")
DB_PASSWORD = os.getenv("DB_PASSWORD", "chinook")
DB_NAME = os.getenv("DB_NAME", "chinook")
MAX_ROWS = int(os.getenv("MAX_ROWS", "30"))

# --- SQLAlchemy URI (Postgres for both engine and memory) ---
DB_URI = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# --- LLM credentials ---
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL")

if not LLM_API_KEY:
    st.error("Missing LLM_API_KEY in environment.")
    st.stop()
if not LLM_MODEL:
    st.error("Missing LLM_MODEL in environment.")
    st.stop()

# --- MEMORY (LLM memory/checkpoint) config ---
MEMORY_DB_URI = os.getenv("MEMORY_DB_URI", f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
MEMORY_SCHEMA = os.getenv("MEMORY_SCHEMA", "public")

# --- Build LLM client and SQL agent ---
llm_client = build_client(
    url="",
    api_key=LLM_API_KEY,
    model=LLM_MODEL
)

# --- Build memory checkpointer using Postgres ---
checkpointer, pool = build_checkpointer(MEMORY_DB_URI, schema=MEMORY_SCHEMA)
atexit.register(pool.close)

agent = SQLAgent(
    llm_client=llm_client,
    llm_maxrows=MAX_ROWS,
    llm_memory_checkpointer=checkpointer,
    prompts=load_prompts("default_prompts.json"),
    logger=logger,
    sql_examples=sql_examples
)

# --- Build SQLAlchemy engine and extract data dictionary ---
try:
    engine = create_engine(DB_URI)
    data_dict_model = extract_data_dictionary(engine, db_label="PostgreSQL")
    data_dict_model.notes = chinook_notes
    data_dict_json = data_dict_model.model_dump_json()
except Exception as e:
    st.error(f"Database connection failed: {e}")
    st.stop()

# --- Streamlit session state ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- Display chat history ---
for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])
    if msg["role"] == "assistant" and msg.get("sql_query"):
        with st.expander("Show generated SQL query"):
            st.code(msg["sql_query"], language="sql")

# --- Main chat loop ---
if prompt := st.chat_input():
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    result = agent.run_with_input(
        question=prompt,
        session_id=st.session_state.session_id,
        data_dictionary_json=data_dict_json,
        datasource_engine=engine
    )

    answer = result.get("answer", "Sorry, I couldn't process that.")
    sql_query = result.get("sql_query", "")
    # Append both answer and sql_query to the message
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sql_query": sql_query
    })
    st.chat_message("assistant").write(answer)
    if sql_query:
        with st.expander("Show generated SQL query"):
            st.code(sql_query, language="sql")

