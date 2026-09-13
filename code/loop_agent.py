# loop_agent.py — A ReAct-style loop with proper engineering
# From the blog: "From Loops to Graphs: The New Architecture of AI Agents"
# 
# Run: python loop_agent.py
# Requires: pip install openai

import os
import openai
import json

client = openai.OpenAI()

# ── Tools the agent can use ──────────────────────────────────
tools = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Search internal knowledge base for company data",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Perform a mathematical calculation",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Math expression to evaluate"}
                },
                "required": ["expression"]
            }
        }
    }
]


# ── Tool implementations ─────────────────────────────────────
def search_knowledge_base(query: str) -> str:
    """Simulated knowledge base — swap with your real data source"""
    kb = {
        "revenue": "Q3 2026 revenue was $4.2M, up 23% YoY",
        "employees": "Current headcount: 142 across 3 offices",
        "churn": "Monthly churn rate: 2.1%, down from 3.4% last quarter",
        "costs": "Q3 operating costs: $3.1M, infrastructure: $890K"
    }
    for key, value in kb.items():
        if key in query.lower():
            return value
    return f"No results found for: {query}"


def calculate(expression: str) -> str:
    """Evaluate math — use a safe parser (like numexpr) in production"""
    try:
        result = eval(expression)  # ⚠️ Use ast.literal_eval or numexpr in prod
        return str(result)
    except Exception as e:
        return f"Calculation error: {e}"


TOOL_MAP = {
    "search_knowledge_base": search_knowledge_base,
    "calculate": calculate,
}


# ── The loop engine ──────────────────────────────────────────
def run_agent_loop(
    user_query: str,
    max_iterations: int = 5,     # Hard bound: prevents infinite loops
    token_budget: int = 10_000,  # Cost control: prevents runaway spend
):
    """
    ReAct loop with proper engineering:
    ✅ Machine-checkable stop condition (no tool calls = done)
    ✅ Max iteration bound
    ✅ Token budget
    ✅ State tracking (messages list IS the state)
    """
    messages = [
        {"role": "system", "content": (
            "You are a helpful business analyst. Think step-by-step. "
            "Use tools when you need data. When you have enough "
            "information to answer, respond directly without calling tools."
        )},
        {"role": "user", "content": user_query}
    ]

    total_tokens = 0
    iteration_log = []  # ← Persistent state: tracks what happened each step

    for i in range(max_iterations):
        print(f"\n{'='*50}")
        print(f"  Iteration {i+1}/{max_iterations} | Tokens used: {total_tokens}")
        print(f"{'='*50}")

        response = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-5"),  # Or "gpt-6"
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        msg = response.choices[0].message
        total_tokens += response.usage.total_tokens

        # ── STOP CONDITION 1: Token budget exceeded ──
        if total_tokens > token_budget:
            print(f"\n⚠️  Token budget exceeded ({total_tokens}/{token_budget})")
            print(f"    Escalating to human review.")
            return {
                "status": "BUDGET_EXCEEDED",
                "partial_result": msg.content,
                "tokens_used": total_tokens,
                "iterations": i + 1,
                "log": iteration_log,
            }

        # ── STOP CONDITION 2: Agent finished (no tool calls) ──
        if not msg.tool_calls:
            print(f"\n✅ Agent completed in {i+1} iteration(s)")
            print(f"   Answer: {msg.content[:200]}...")
            return {
                "status": "COMPLETED",
                "result": msg.content,
                "tokens_used": total_tokens,
                "iterations": i + 1,
                "log": iteration_log,
            }

        # ── ACT: Execute tool calls ──
        messages.append(msg)
        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)
            print(f"  🔧 Tool: {fn_name}({fn_args})")

            result = TOOL_MAP[fn_name](**fn_args)
            print(f"  📄 Result: {result}")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

            # Track state
            iteration_log.append({
                "iteration": i + 1,
                "tool": fn_name,
                "args": fn_args,
                "result": result,
            })

    # ── STOP CONDITION 3: Max iterations hit ──
    print(f"\n⚠️  Max iterations reached ({max_iterations})")
    return {
        "status": "MAX_ITERATIONS",
        "partial_result": messages[-1].get("content", ""),
        "tokens_used": total_tokens,
        "iterations": max_iterations,
        "log": iteration_log,
    }


# ── Run it ───────────────────────────────────────────────────
if __name__ == "__main__":
    result = run_agent_loop(
        "What was our Q3 revenue and how much did it grow "
        "in absolute dollars compared to the same quarter last year?"
    )
    print(f"\nFinal status: {result['status']}")
    print(f"Tokens used: {result['tokens_used']}")
