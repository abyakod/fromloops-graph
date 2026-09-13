# graph_agent.py — A multi-agent graph with LangGraph
# From the blog: "From Loops to Graphs: The New Architecture of AI Agents"
#
# Run: python graph_agent.py
# Requires: pip install langgraph langchain-core

from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END, START


# ── 1. DEFINE SHARED STATE ──────────────────────────────────
# This is the key difference from loops:
# State is EXPLICIT, TYPED, and SHARED across all agents.

class AgentState(TypedDict):
    task: str              # What we're building
    research: str          # Findings from the researcher
    code: str              # Generated code
    review: str            # Review feedback
    revision_count: int    # How many revisions so far
    status: str            # Current workflow status


# ── 2. DEFINE AGENT NODES ───────────────────────────────────
# Each function is an independent "agent" — it reads state,
# does its work, and returns updated state.

def planner_agent(state: AgentState) -> AgentState:
    """Analyzes the task and creates an execution plan."""
    print("\n📋 Planner: Breaking down the task...")
    print(f"   Task: {state['task']}")

    # In production, this would be an LLM call that generates
    # a structured plan. Simplified here for clarity.
    return {
        **state,
        "status": "planned",
    }


def research_agent(state: AgentState) -> AgentState:
    """Gathers information relevant to the task."""
    print("\n🔍 Researcher: Gathering context and best practices...")

    # Simulated research — replace with RAG, web search, or docs lookup
    research = (
        f"Research findings for: {state['task']}\n"
        f"  • Found 3 relevant API patterns in the codebase\n"
        f"  • Best practice: use async/await for I/O operations\n"
        f"  • Error handling: implement exponential backoff\n"
        f"  • Similar solution exists in utils/http_client.py"
    )
    print(f"   {research}")

    return {**state, "research": research}


def coding_agent(state: AgentState) -> AgentState:
    """Writes code based on the plan and research."""
    revision = state.get("revision_count", 0)
    print(f"\n💻 Coder: Writing implementation (revision {revision})...")

    # In production, this would be an LLM call with the research
    # as context. The code improves on each revision because the
    # review feedback is in the state.
    if revision == 0:
        # First attempt: missing error handling and retries
        code = '''
import aiohttp
import asyncio

async def fetch_data(url: str) -> dict:
    """Fetch JSON data from an API endpoint."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()
'''
    else:
        # Improved version after review feedback
        code = '''
import aiohttp
import asyncio
import logging

logger = logging.getLogger(__name__)

async def fetch_data(url: str, max_retries: int = 3) -> dict:
    """Fetch JSON data with exponential backoff retry logic."""
    async with aiohttp.ClientSession() as session:
        for attempt in range(max_retries):
            try:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    logger.info(f"Successfully fetched from {url}")
                    return data
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                wait = 2 ** attempt
                logger.warning(
                    f"Attempt {attempt+1} failed: {e}. "
                    f"Retrying in {wait}s..."
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait)
        raise ConnectionError(
            f"Failed to fetch {url} after {max_retries} attempts"
        )
'''
    print(f"   Generated {len(code.strip().splitlines())} lines of code")
    return {**state, "code": code}


def review_agent(state: AgentState) -> AgentState:
    """Independently reviews the code for quality."""
    print("\n🔎 Reviewer: Analyzing code quality...")

    issues = []
    code = state["code"]

    # Automated checks — these are the "machine-checkable conditions"
    # from the Loop Engineering paper
    if "try" not in code:
        issues.append("Missing error handling (no try/except)")
    if "timeout" not in code.lower():
        issues.append("No timeout configured for HTTP calls")
    if "logging" not in code and "logger" not in code:
        issues.append("No logging for observability")
    if "retry" not in code.lower() and "backoff" not in code.lower():
        issues.append("No retry logic despite research recommending it")

    if issues:
        review = f"NEEDS_REVISION: {'; '.join(issues)}"
        print(f"   ❌ Found {len(issues)} issue(s):")
        for issue in issues:
            print(f"      • {issue}")
    else:
        review = (
            "APPROVED: Code follows best practices — "
            "async, error handling, retries, logging, timeouts."
        )
        print(f"   ✅ Code approved!")

    return {
        **state,
        "review": review,
        "revision_count": state.get("revision_count", 0) + 1,
    }


# ── 3. DEFINE ROUTING LOGIC ─────────────────────────────────
# This is the "judge" — it decides whether to loop back or finish.
# Note: this is a LOOP inside the GRAPH. Loop engineering becomes
# a primitive within graph engineering.

def should_revise(state: AgentState) -> Literal["coder", "end"]:
    """Route based on review outcome: revise or ship."""
    max_revisions = 3
    if (
        "NEEDS_REVISION" in state["review"]
        and state["revision_count"] < max_revisions
    ):
        print(
            f"\n🔄 Judge: Revision {state['revision_count']}"
            f"/{max_revisions} — sending back to coder"
        )
        return "coder"
    if state["revision_count"] >= max_revisions:
        print(f"\n⚠️  Judge: Max revisions reached — shipping as-is")
    else:
        print(
            f"\n✅ Judge: Approved after "
            f"{state['revision_count']} revision(s) — done!"
        )
    return "end"


# ── 4. BUILD THE GRAPH ──────────────────────────────────────
workflow = StateGraph(AgentState)

# Add nodes (agents)
workflow.add_node("planner", planner_agent)
workflow.add_node("researcher", research_agent)
workflow.add_node("coder", coding_agent)
workflow.add_node("reviewer", review_agent)

# Add edges (execution flow)
workflow.add_edge(START, "planner")           # Entry point
workflow.add_edge("planner", "researcher")    # Plan → Research
workflow.add_edge("researcher", "coder")      # Research → Code
workflow.add_edge("coder", "reviewer")        # Code → Review

# Conditional edge: the "graph" part
# Reviewer → Coder (retry loop) OR → END (done)
workflow.add_conditional_edges(
    "reviewer",
    should_revise,
    {"coder": "coder", "end": END},
)

# Compile the graph into a runnable app
app = workflow.compile()


# ── 5. EXECUTE ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  MULTI-AGENT GRAPH EXECUTION")
    print("=" * 60)

    result = app.invoke({
        "task": "Build an async data fetcher with retry logic",
        "research": "",
        "code": "",
        "review": "",
        "revision_count": 0,
        "status": "new",
    })

    print("\n" + "=" * 60)
    print("  FINAL RESULT")
    print("=" * 60)
    print(f"  Status:    {result['status']}")
    print(f"  Revisions: {result['revision_count']}")
    print(f"  Review:    {result['review']}")
    print(f"\n  Final code:\n{result['code']}")
