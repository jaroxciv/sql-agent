import streamlit as st
import uuid
from langchain_core.messages import AIMessage, HumanMessage
from langchain.chat_models import ChatOpenAI
from sql_agent import create_sql_agent

st.set_page_config(page_title="Chat with your Database", page_icon=":speech_balloon:")

st.title("Chat with your Database")

# Hardcoded values for simplicity
DB_URI = "sqlite:///Chinook.db"
STATE_PATH = "state.db"
MODEL = "gpt-3.5-turbo-0125"
TOP_K = 5

# Initialize the chat model
llm = ChatOpenAI(model=MODEL)

# Create the SQL agent graph
# This will also save the graph visualization
graph, db = create_sql_agent(
    llm=llm,
    db_uri=DB_URI,
    state_path=STATE_PATH,
    top_k=TOP_K,
)

# Initialize session state
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages
for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

# Chat input
if prompt := st.chat_input():
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    # Invoke the graph
    events = graph.stream(
        {"messages": [HumanMessage(content=prompt)]},
        config={"configurable": {"thread_id": st.session_state.session_id}},
        stream_mode="values",
    )

    final_answer = None
    for step in events:
        last = step["messages"][-1]
        if isinstance(last, AIMessage) and last.content:
            final_answer = last.content

    if final_answer:
        st.session_state.messages.append({"role": "assistant", "content": final_answer})
        st.chat_message("assistant").write(final_answer)
    else:
        st.session_state.messages.append({"role": "assistant", "content": "Sorry, I couldn't process that."})
        st.chat_message("assistant").write("Sorry, I couldn't process that.")
