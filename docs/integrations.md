# Framework Integrations

AgentMemoryDB provides drop-in integrations for the two most popular AI agent frameworks.

---

## LangChain Integration

Install dependencies:

```bash
pip install langchain-core langchain-openai agentmemodb
```

Import:

```python
import agentmemodb
from agentmemodb.integrations.langchain import (
    AgentMemoryDBChatHistory,
    AgentMemoryDBRetriever,
    AgentMemoryDBConversationMemory,
    create_memory_tool,
)

db = agentmemodb.Client()  # or HttpClient for the Docker server
```

---

### 1. Chat Message History

`AgentMemoryDBChatHistory` is a drop-in replacement for any LangChain `BaseChatMessageHistory`. Messages are persisted as `episodic` memories and survive process restarts.

```python
from agentmemodb.integrations.langchain import AgentMemoryDBChatHistory

# Create or resume a session
history = AgentMemoryDBChatHistory(
    client=db,
    user_id="user-1",
    session_id="session-abc",  # deterministic = resumes on restart
)

# Add messages
history.add_user_message("What is the capital of France?")
history.add_ai_message("The capital of France is Paris.")
history.add_user_message("What's the population?")

# Retrieve history
for msg in history.messages:
    role = "Human" if hasattr(msg, 'content') and type(msg).__name__ == 'HumanMessage' else "AI"
    print(f"{role}: {msg.content}")

# Clear session
history.clear()
```

**Connecting to `RunnableWithMessageHistory`** (modern LangChain):

```python
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o")

def get_history(session_id: str) -> AgentMemoryDBChatHistory:
    return AgentMemoryDBChatHistory(
        client=db,
        user_id="user-1",
        session_id=session_id,
    )

chain_with_history = RunnableWithMessageHistory(
    llm,
    get_history,
    input_messages_key="input",
    history_messages_key="history",
)

response = chain_with_history.invoke(
    {"input": "What's my favorite language?"},
    config={"configurable": {"session_id": "session-abc"}},
)
print(response.content)
```

---

### 2. Retriever

`AgentMemoryDBRetriever` performs semantic search over stored memories and returns LangChain `Document` objects. Plug it into any `RetrievalQA`, `ConversationalRetrievalChain`, or `create_retrieval_chain`.

```python
from agentmemodb.integrations.langchain import AgentMemoryDBRetriever

retriever = AgentMemoryDBRetriever(
    client=db,
    user_id="user-1",
    top_k=5,
    memory_types=["semantic"],   # optional filter
    score_threshold=0.3,          # exclude low-relevance memories
)

# Retrieve relevant documents
docs = retriever.invoke("What programming languages does the user prefer?")

for doc in docs:
    print(f"[{doc.metadata['score']:.3f}] {doc.metadata['memory_key']}: {doc.page_content}")
```

**With RetrievalQA:**

```python
from langchain.chains import RetrievalQA
from langchain_openai import ChatOpenAI

qa_chain = RetrievalQA.from_chain_type(
    llm=ChatOpenAI(model="gpt-4o"),
    retriever=retriever,
)

answer = qa_chain.invoke({"query": "What tools does Alice prefer?"})
print(answer["result"])
```

**With `create_retrieval_chain` (LCEL):**

```python
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o")

prompt = ChatPromptTemplate.from_messages([
    ("system", "Answer questions using this memory context:\n\n{context}"),
    ("human", "{input}"),
])

doc_chain = create_stuff_documents_chain(llm, prompt)
chain = create_retrieval_chain(retriever, doc_chain)

result = chain.invoke({"input": "What is Alice's preferred backend framework?"})
print(result["answer"])
```

---

### 3. Memory Tool (for Agents)

`create_memory_tool` gives a LangChain agent the ability to store and recall memories dynamically during execution.

```python
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from agentmemodb.integrations.langchain import create_memory_tool

# Create the tool
memory_tool = create_memory_tool(
    client=db,
    user_id="user-1",
    tool_name="memory_store_and_recall",
    top_k=5,
)

# The tool accepts JSON input:
# Store: {"action": "store", "key": "pref:language", "content": "Prefers Python"}
# Recall: {"action": "recall", "query": "What language does user prefer?"}

llm = ChatOpenAI(model="gpt-4o")
tools = [memory_tool]

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant with persistent memory. "
               "Use the memory tool to store important facts and recall them later."),
    ("human", "{input}"),
    MessagesPlaceholder("agent_scratchpad"),
])

agent = create_openai_tools_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

# The agent will automatically store and recall memories
response = executor.invoke({"input": "Remember that I prefer async Python patterns."})
print(response["output"])

# Later session
response = executor.invoke({"input": "What are my Python preferences?"})
print(response["output"])
```

---

### 4. Conversation Memory (Legacy Chains)

`AgentMemoryDBConversationMemory` supports older LangChain chains that use the `memory=` parameter. It combines chat history with semantic retrieval of relevant long-term memories.

```python
from langchain.chains import ConversationChain
from langchain_openai import ChatOpenAI
from agentmemodb.integrations.langchain import AgentMemoryDBConversationMemory

memory = AgentMemoryDBConversationMemory(
    client=db,
    user_id="user-1",
    session_id="session-xyz",
    top_k=5,                             # retrieve top-5 relevant long-term memories
    relevant_memories_key="context",     # injected as {context} in prompt
    memory_key="history",                # injected as {history} in prompt
)

chain = ConversationChain(
    llm=ChatOpenAI(model="gpt-4o"),
    memory=memory,
    verbose=True,
)

response = chain.invoke({"input": "What language do I prefer for backend?"})
print(response["response"])
```

---

## LangGraph Integration

Install dependencies:

```bash
pip install langgraph agentmemodb
```

Import:

```python
import agentmemodb
from agentmemodb.integrations.langgraph import (
    AgentMemoryDBStore,
    AgentMemoryDBSaver,
)

db = agentmemodb.Client()
```

---

### 1. AgentMemoryDBStore — Persistent Knowledge for Nodes

`AgentMemoryDBStore` gives LangGraph nodes the ability to read and write persistent, searchable long-term memory. Unlike graph state (ephemeral per run), store memories survive across runs.

```python
store = AgentMemoryDBStore(
    client=db,
    user_id="user-1",
    namespace="agent",   # optional prefix for all keys
)
```

#### Writing memories

```python
# Store a single memory
store.put(
    key="pref:language",
    value="User prefers Python for backend development.",
    memory_type="semantic",
    scope="user",
    importance=0.85,
    metadata={"source": "user_stated"},
)

# Store multiple at once
store.put_many([
    {"key": "pref:framework", "content": "Prefers FastAPI", "importance": 0.8},
    {"key": "pref:testing", "content": "Uses pytest exclusively", "importance": 0.75},
])
```

#### Reading memories

```python
# Semantic search
results = store.search(
    "What does the user prefer for Python development?",
    top_k=5,
    memory_types=["semantic"],
)
for r in results:
    print(f"[{r.score:.3f}] {r.key}: {r.content}")

# Get formatted text block (perfect for prompt injection)
context = store.search_as_text(
    "user preferences for development tools",
    top_k=5,
)
print(context)
# - [pref:framework] Prefers FastAPI (relevance=0.92)
# - [pref:testing] Uses pytest (relevance=0.88)

# Get by exact key
mem = store.get("pref:language")

# List all
memories = store.list(memory_type="semantic", limit=50)

# Count
n = store.count()

# Delete
store.delete("pref:old-info")
```

#### Integrating into a LangGraph node

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated

class AgentState(TypedDict):
    input: str
    memory_context: str
    response: str

def retrieve_memory(state: AgentState) -> AgentState:
    """Retrieve relevant memories before responding."""
    context = store.search_as_text(state["input"], top_k=5)
    return {**state, "memory_context": context}

def generate_response(state: AgentState) -> AgentState:
    """Generate response using LLM + memory context."""
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model="gpt-4o")
    prompt = f"""Memory context:
{state['memory_context']}

User input: {state['input']}

Response:"""
    response = llm.invoke(prompt)
    return {**state, "response": response.content}

def store_insights(state: AgentState) -> AgentState:
    """Extract and store insights from this turn."""
    # In production, use an LLM to extract key facts
    if "prefer" in state["input"].lower():
        store.put(
            key=f"insight:{hash(state['input']) % 10000:04d}",
            value=state["input"],
            memory_type="semantic",
            importance=0.7,
        )
    return state

# Build the graph
graph = StateGraph(AgentState)
graph.add_node("retrieve", retrieve_memory)
graph.add_node("generate", generate_response)
graph.add_node("store", store_insights)

graph.set_entry_point("retrieve")
graph.add_edge("retrieve", "generate")
graph.add_edge("generate", "store")
graph.add_edge("store", END)

app = graph.compile()

result = app.invoke({"input": "I prefer async Python patterns."})
print(result["response"])
```

---

### 2. AgentMemoryDBSaver — Graph State Checkpoints

`AgentMemoryDBSaver` persists full LangGraph state snapshots, enabling:
- **Pause/Resume** — stop and restart graph execution at any point
- **Time-travel** — revisit any previous state
- **Branching** — fork execution from a checkpoint with different inputs
- **Audit trails** — complete history of all graph states

```python
from langgraph.graph import StateGraph
from agentmemodb.integrations.langgraph import AgentMemoryDBSaver

saver = AgentMemoryDBSaver(
    client=db,
    user_id="system",   # user context for checkpoint storage
)

# Compile graph with checkpointer
graph = StateGraph(AgentState)
# ... add nodes and edges ...
app = graph.compile(checkpointer=saver)

# Run with thread_id to enable checkpointing
config = {"configurable": {"thread_id": "thread-alice-session-1"}}

result = app.invoke({"input": "Hello"}, config)
```

#### Resuming from checkpoint

```python
# Get the latest checkpoint for a thread
checkpoint = saver.get({"configurable": {"thread_id": "thread-alice-session-1"}})

# Get a specific checkpoint by ID
checkpoint = saver.get({
    "configurable": {
        "thread_id": "thread-alice-session-1",
        "checkpoint_id": "specific-checkpoint-uuid",
    }
})

# List all checkpoints for a thread
history = saver.list_thread_checkpoints("thread-alice-session-1")
for ckpt in history:
    print(f"  {ckpt['timestamp']}: checkpoint_id={ckpt['checkpoint_id']}")

# Resume from a specific checkpoint (time-travel)
result = app.invoke(
    None,  # None = resume from checkpoint
    config={
        "configurable": {
            "thread_id": "thread-alice-session-1",
            "checkpoint_id": "abc-123",
        }
    },
)
```

---

### 3. Complete LangGraph Agent Example

```python
"""
Full LangGraph agent with persistent memory (store) and
state checkpointing (saver).
"""
import agentmemodb
from agentmemodb.integrations.langgraph import AgentMemoryDBStore, AgentMemoryDBSaver
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from typing import TypedDict

# Setup
db = agentmemodb.Client(path="./agent_data")
store = AgentMemoryDBStore(client=db, user_id="alice", namespace="assistant")
saver = AgentMemoryDBSaver(client=db, user_id="system")

class State(TypedDict):
    input: str
    context: str
    output: str

def load_context(state: State) -> State:
    context = store.search_as_text(state["input"], top_k=5)
    return {**state, "context": context}

def respond(state: State) -> State:
    llm = ChatOpenAI(model="gpt-4o")
    prompt = f"Context from memory:\n{state['context']}\n\nUser: {state['input']}\nAssistant:"
    output = llm.invoke(prompt)
    return {**state, "output": output.content}

def memorize(state: State) -> State:
    if any(kw in state["input"].lower() for kw in ["prefer", "like", "love", "hate", "always", "never"]):
        store.put(
            key=f"learned:{abs(hash(state['input'])) % 100000:05d}",
            value=state["input"],
            memory_type="semantic",
            importance=0.75,
        )
    return state

# Build
graph = StateGraph(State)
graph.add_node("load", load_context)
graph.add_node("respond", respond)
graph.add_node("memorize", memorize)
graph.set_entry_point("load")
graph.add_edge("load", "respond")
graph.add_edge("respond", "memorize")
graph.add_edge("memorize", END)

app = graph.compile(checkpointer=saver)

# Run with persistent thread
config = {"configurable": {"thread_id": "alice-main"}}

turns = [
    "I always use pytest for testing Python code.",
    "FastAPI is my go-to framework for APIs.",
    "What do I prefer for backend development?",  # should recall context
]

for user_input in turns:
    result = app.invoke({"input": user_input}, config)
    print(f"User: {user_input}")
    print(f"Agent: {result['output']}\n")

db.close()
```

---

## TypeScript SDK

A TypeScript client is available in the `sdks/typescript/` directory.

### Installation

```bash
cd sdks/typescript
npm install
npm run build
```

Or copy the compiled output to your project:
```bash
npm install ./sdks/typescript
```

### Usage

```typescript
import { AgentMemoryDBClient } from 'agentmemodb-sdk';

const client = new AgentMemoryDBClient({
  baseUrl: 'http://localhost:8100',
  apiKey: 'amdb_your_key_here',  // optional
  timeout: 30000,
});

// Health check
const health = await client.health();

// Create user
const user = await client.createUser({ name: 'Alice' });
const userId = user.id;

// Store memory
const memory = await client.upsertMemory({
  userId,
  memoryKey: 'pref:language',
  memoryType: 'semantic',
  scope: 'user',
  content: 'Alice prefers TypeScript for frontend development.',
  importanceScore: 0.8,
  confidence: 0.9,
});

// Search memories
const results = await client.searchMemories({
  userId,
  queryText: 'What does Alice prefer for frontend?',
  topK: 5,
  explain: true,
});

for (const result of results.results) {
  console.log(`[${result.score?.finalScore.toFixed(3)}] ${result.memory.memoryKey}: ${result.memory.content}`);
}

// Export / Import
const exported = await client.exportMemories({ userId, includeVersions: true });
const imported = await client.importMemories({ userId: newUserId, data: exported, strategy: 'upsert' });
```

---

## Choosing the Right Integration

| Scenario | Recommended |
|---|---|
| New LangChain app with persistent memory | `AgentMemoryDBChatHistory` + `AgentMemoryDBRetriever` |
| LangChain agent that learns during execution | `create_memory_tool` |
| LangGraph agent with long-term knowledge | `AgentMemoryDBStore` |
| LangGraph multi-session or pause/resume | `AgentMemoryDBSaver` |
| Production system, high throughput | `app.sdk.client.AgentMemoryDBClient` (async) |
| Scripts, notebooks, quick experiments | `agentmemodb.Client` (embedded) |
| Frontend / Node.js | TypeScript SDK |
