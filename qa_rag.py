from typing import TypedDict, Annotated

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
import ddgs
import os
from dotenv import load_dotenv

# -------------------------
# IMPORT YOUR RAG FUNCTION
# -------------------------

from rag_pipeline import get_collection


def hybrid_search(query: str, top_k: int = 5):
    collection = get_collection()

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        include=["metadatas", "documents", "distances"],
    )

    docs = []
    for metadata, document, distance in zip(
        results["metadatas"][0],
        results["documents"][0],
        results["distances"][0],
    ):
        item = dict(metadata)
        item["summary"] = document
        item["score"] = round((1 - distance) * 100, 1)
        docs.append(item)

    return docs

# -------------------------
# GROQ
# -------------------------
load_dotenv()
llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    groq_api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.2,
)

# -------------------------
# TOOL 1 : ESG RAG
# -------------------------
@tool
def esg_rag_tool(query: str):
    """
    Search ESG knowledge base using ChromaDB.
    Use for company-specific regulations,
    compliance analysis,
    jurisdiction-specific ESG requirements.
    """

    docs = hybrid_search(query, top_k=5)

    context = []

    for d in docs:
        context.append(
            {
                "title": d.get("title"),
                "regulation": d.get("regulation_name"),
                "jurisdiction": d.get("jurisdiction"),
                "regulator": d.get("regulator"),
                "summary": d.get("summary"),
                "score": d.get("score"),
            }
        )
        print("\n--- Retrieved Document ---")
        print("---- rag callled ---")
        print(d.get("title"))

    return context


# -------------------------
# TOOL 2 : WEB SEARCH
# -------------------------
@tool
def duckduckgo_tool(query: str):
    """
    Search the web for general ESG knowledge.
    Use for:
    - What is TCFD?
    - What is ESRS?
    - What is CBAM?
    - Latest ESG news
    """

    results = []

    with ddgs.DDGS() as ddgs_client:

        for r in ddgs_client.text(
            query,
            max_results=5
        ):

            results.append(
                {
                    "title": r["title"],
                    "body": r["body"],
                }
            )
            print("\n--- DuckDuckGo Result ---")
            print(r["title"])

    return results


# -------------------------
# TOOLS
# -------------------------
tools = [
    esg_rag_tool,
    duckduckgo_tool,
]

llm_with_tools = llm.bind_tools(tools)

# -------------------------
# STATE
# -------------------------
class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# -------------------------
# SYSTEM PROMPT
# -------------------------
SYSTEM_PROMPT = """
You are an ESG Regulatory Intelligence Assistant.

TOOL USAGE:

Use esg_rag_tool when:
- company specific questions
- compliance reports
- regulations affecting companies
- sector specific ESG impact
- jurisdiction based compliance

Examples:
- What regulations affect UK asset managers?
- Generate compliance report for a steel company
- ESG risks for renewable energy company

Use duckduckgo_tool when:
- What is TCFD?
- What is ESRS?
- What is ISSB?
- What is CBAM?
- Latest ESG news
- General ESG concepts

Always choose the best tool.

After receiving tool results:
1. Analyze results
2. Explain clearly
3. Mention regulations
4. Mention recommended actions

If user asks for a compliance report:

Return ONLY in this format:

Risk Level:
Applicable Regulations:
Regulators:
Reporting Requirements:
Recommended Actions:
Priority:
"""


# -------------------------
# CHAT NODE
# -------------------------
def chat_node(state: ChatState):

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        *state["messages"]
    ]

    response = llm_with_tools.invoke(messages)

    return {
        "messages": [response]
    }


# -------------------------
# GRAPH
# -------------------------
graph = StateGraph(ChatState)

graph.add_node(
    "chat_node",
    chat_node
)

graph.add_node(
    "tools",
    ToolNode(tools)
)

graph.add_edge(
    START,
    "chat_node"
)

graph.add_conditional_edges(
    "chat_node",
    tools_condition
)

graph.add_edge(
    "tools",
    "chat_node"
)

agent = graph.compile()

# -------------------------
# CLI
# -------------------------
if __name__ == "__main__":

    print("=" * 60)
    print("ESG AI AGENT")
    print("=" * 60)

    while True:

        question = input("\nAsk ESG Question: ")

        if question.lower() == "exit":
            break

        result = agent.invoke(
            {
                "messages": [
                    HumanMessage(content=question)
                ]
            }
        )

        print("\n" + "=" * 60)

        print(
            result["messages"][-1].content
        )

        print("=" * 60)
