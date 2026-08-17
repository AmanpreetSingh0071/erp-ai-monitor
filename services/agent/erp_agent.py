"""
LangGraph Autonomous Agent for ERP failure triage.

Replaces the raw run_ai() thread call in backend/main.py.

Graph: retrieve_context → diagnose → route_decision → log_to_db → END

Routing thresholds (confidence_score returned by LLM):
  >= 0.85  →  AUTO_REMEDIATE   (high confidence, safe to act without human)
  >= 0.60  →  INVESTIGATE      (medium confidence, flag for analyst review)
  <  0.60  →  ESCALATE         (low confidence, route to senior engineer)
"""

import os
import json
import time
import re
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq

from backend.database import get_connection
import services.ai.rag_root_cause as _rag
from services.ai.rag_root_cause import extract_json


# -------------------------
# AGENT STATE
# -------------------------
class AgentState(TypedDict):
    transaction_id: str
    event: dict
    rag_context: str
    diagnosis: Optional[dict]           # root_cause, impact, recommendation, confidence_score
    confidence_score: float
    routing_decision: str               # AUTO_REMEDIATE | INVESTIGATE | ESCALATE
    timing: dict                        # rag_time, llm_time, total_time


# -------------------------
# NODE 1: RETRIEVE CONTEXT
# -------------------------
def retrieve_context(state: AgentState) -> AgentState:
    event = state["event"]
    query = (
        f"retry {event['retry_count']} "
        f"delay {event['delay_minutes']} "
        f"system {event['system']}"
    )

    start = time.time()
    docs = _rag.RETRIEVER.invoke(query)
    rag_time = round(time.time() - start, 2)

    state["rag_context"] = "\n".join([d.page_content for d in docs])
    state["timing"] = {"rag_time": rag_time}

    print(f"📚 RAG retrieved {len(docs)} docs in {rag_time}s")
    return state


# -------------------------
# NODE 2: DIAGNOSE
# -------------------------
def diagnose(state: AgentState) -> AgentState:
    event = state["event"]
    context = state["rag_context"]

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise Exception("GROQ_API_KEY NOT SET")

    llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=api_key)

    prompt = f"""You are an ERP monitoring AI agent for enterprise integrations (Oracle NetSuite, SAP, EDI).

Analyze the ERP failure event and return ONLY valid JSON — no markdown, no explanation.

Historical incident context:
{context}

Event details:
  System:        {event["system"]}
  Partner:       {event["partner"]}
  Retry Count:   {event["retry_count"]}
  Delay Minutes: {event["delay_minutes"]}

Before assigning a confidence_score, reason through these questions:
1. Does the historical context contain an incident with the SAME system, similar retry count AND similar delay? If yes to all three, score 0.85+
2. Does the context match on system only, or are the retry/delay values quite different? Score 0.60-0.84
3. Is the event pattern not present in context at all, or is this a novel failure type? Score below 0.60

Be honest about uncertainty. Do NOT default to 1.00. Most events should score between 0.60 and 0.90.

Scoring reference:
- 0.85-1.00: strong match on system + retry + delay + known fix — use sparingly
- 0.60-0.84: partial match — system matches but pattern differs somewhat
- 0.00-0.59: weak or no match — novel event, human review required

Return this exact JSON structure with a numeric confidence_score between 0.00 and 1.00:
{{
  "root_cause": "One precise sentence describing the root cause",
  "impact": "Business impact — SLA breach, delays, revenue risk, etc.",
  "recommendation": "Specific actionable fix with config/API/log references",
  "confidence_score": 0.75
}}"""

    start = time.time()
    response = llm.invoke(prompt)
    llm_time = round(time.time() - start, 2)

    print(f"🧠 LLM responded in {llm_time}s")
    print(f"🧠 RAW LLM OUTPUT: {response.content}")

    parsed = extract_json(response.content)

    timing = state.get("timing", {})
    timing["llm_time"] = llm_time

    if parsed and "root_cause" in parsed:
        raw_score = parsed.get("confidence_score", 0.5)
        try:
            score = float(raw_score)
            score = max(0.0, min(1.0, score))
        except (TypeError, ValueError):
            score = 0.5

        state["diagnosis"] = {
            "root_cause": str(parsed.get("root_cause", "")).strip(),
            "impact": str(parsed.get("impact", "")).strip(),
            "recommendation": str(parsed.get("recommendation", "")).strip(),
            "confidence_score": score,
        }
        state["confidence_score"] = score
    else:
        # Fallback: treat entire response as root_cause with low confidence
        print("⚠️ JSON parse failed — using fallback diagnosis")
        state["diagnosis"] = {
            "root_cause": response.content.strip(),
            "impact": "Potential SLA breach or system delay",
            "recommendation": "Check logs, retry configuration, and API health",
            "confidence_score": 0.4,
        }
        state["confidence_score"] = 0.4

    state["timing"] = timing
    return state


# -------------------------
# NODE 3: ROUTE DECISION
# -------------------------
def route_decision(state: AgentState) -> AgentState:
    score = state["confidence_score"]

    if score >= 0.85:
        decision = "AUTO_REMEDIATE"
    elif score >= 0.60:
        decision = "INVESTIGATE"
    else:
        decision = "ESCALATE"

    state["routing_decision"] = decision
    print(f"🔀 Routed → {decision} (confidence={score:.2f})")
    return state


# -------------------------
# NODE 4: LOG TO DATABASE
# -------------------------
def log_to_db(state: AgentState) -> AgentState:
    tx_id = state["transaction_id"]
    diagnosis = state["diagnosis"]
    decision = state["routing_decision"]
    score = state["confidence_score"]
    timing = state.get("timing", {})

    result_payload = {
        **diagnosis,
        "agent_decision": decision,
        "rag_time": timing.get("rag_time"),
        "llm_time": timing.get("llm_time"),
    }
    result_str = json.dumps(result_payload)

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            ALTER TABLE exceptions
            ADD COLUMN IF NOT EXISTS agent_decision VARCHAR(20),
            ADD COLUMN IF NOT EXISTS confidence_score FLOAT
        """)

        cursor.execute(
            """
            UPDATE exceptions
            SET root_cause       = %s,
                ai_status        = 'DONE',
                agent_decision   = %s,
                confidence_score = %s,
                updated_at       = NOW()
            WHERE transaction_id = %s
            """,
            (result_str, decision, score, tx_id),
        )

        conn.commit()
        print(f"✅ Agent DB update DONE for {tx_id}")

    except Exception as e:
        print(f"❌ log_to_db failed for {tx_id}: {e}")
        try:
            if conn and cursor:
                cursor.execute(
                    """
                    UPDATE exceptions
                    SET root_cause = %s,
                        ai_status  = 'DONE',
                        updated_at = NOW()
                    WHERE transaction_id = %s
                    """,
                    (result_str, tx_id),
                )
                conn.commit()
        except Exception as fallback_err:
            print(f"❌ Fallback DB update also failed: {fallback_err}")

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return state


# -------------------------
# BUILD GRAPH
# -------------------------
def _build_graph() -> object:
    graph = StateGraph(AgentState)

    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("diagnose", diagnose)
    graph.add_node("route_decision", route_decision)
    graph.add_node("log_to_db", log_to_db)

    graph.set_entry_point("retrieve_context")
    graph.add_edge("retrieve_context", "diagnose")
    graph.add_edge("diagnose", "route_decision")
    graph.add_edge("route_decision", "log_to_db")
    graph.add_edge("log_to_db", END)

    return graph.compile()


# -------------------------
# PUBLIC API
# -------------------------
AGENT = None


def init_agent():
    """Build and compile the LangGraph agent. Call once at startup after init_rag()."""
    global AGENT
    AGENT = _build_graph()
    print("✅ LangGraph agent initialized")


def run_agent(transaction_id: str, event: dict) -> dict:
    """
    Run the full agent pipeline for one ERP event.

    Returns the final AgentState so callers can inspect routing_decision,
    confidence_score and diagnosis without hitting the DB again.

    Raises if the agent is not initialized (init_agent() must be called first).
    """
    if AGENT is None:
        raise Exception("Agent not initialized — call init_agent() first")

    start = time.time()

    initial_state: AgentState = {
        "transaction_id": transaction_id,
        "event": event,
        "rag_context": "",
        "diagnosis": None,
        "confidence_score": 0.0,
        "routing_decision": "",
        "timing": {},
    }

    final_state = AGENT.invoke(initial_state)

    total = round(time.time() - start, 2)
    print(
        f"🤖 Agent DONE for {transaction_id} | "
        f"decision={final_state['routing_decision']} | "
        f"confidence={final_state['confidence_score']:.2f} | "
        f"total={total}s"
    )

    return final_state