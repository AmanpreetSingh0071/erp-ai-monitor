import sys
import os
import time
import json
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

print("🚀 APP STARTING...")

from fastapi import FastAPI, BackgroundTasks, WebSocket
from backend.database import get_connection
from fastapi.middleware.cors import CORSMiddleware

import pandas as pd
import joblib
from pydantic import BaseModel

from services.rule_engine.rule_engine import evaluate_rules
from services.ai.rag_root_cause import init_rag, analyze_with_llm

app = FastAPI(title="ERP AI Monitoring API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

model = None
active_connections = []


# -------------------------
# STARTUP
# -------------------------
@app.on_event("startup")
def startup_event():
    global model

    print("🔄 Loading ML model...")

    try:
        model_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "models",
            "anomaly_model.pkl"
        )

        if os.path.exists(model_path):
            model = joblib.load(model_path)
            print("✅ Model loaded")
        else:
            print("⚠️ Model missing")

    except Exception as e:
        print("❌ Model load error:", e)

    try:
        print("🔄 Initializing RAG...")
        init_rag()
        print("✅ RAG ready")
    except Exception as e:
        print("❌ RAG init failed:", e)


# -------------------------
# Schema
# -------------------------
class Event(BaseModel):
    transaction_id: str
    system: str
    partner: str
    retry_count: int
    delay_minutes: int


# -------------------------
# WEBSOCKET
# -------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)

    try:
        while True:
            await websocket.receive_text()
    except:
        active_connections.remove(websocket)


async def notify_clients():
    for ws in active_connections:
        await ws.send_text("new_event")


# -------------------------
# BACKGROUND AI TASK
# -------------------------
def run_ai(transaction_id, event_dict):

    print(f"🤖 AI STARTED for {transaction_id}")

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        result = analyze_with_llm(event_dict)

        # ✅ ALWAYS JSON
        result_str = json.dumps(result)

        cursor.execute(
            """
            UPDATE exceptions
            SET root_cause=%s, ai_status='DONE'
            WHERE transaction_id=%s
            """,
            (result_str, transaction_id)
        )

        conn.commit()
        print("✅ AI UPDATE DONE")

    except Exception as e:
        print("❌ AI FAILED:", e)

        if cursor:
            cursor.execute(
                """
                UPDATE exceptions
                SET root_cause=%s, ai_status='FAILED'
                WHERE transaction_id=%s
                """,
                (str(e), transaction_id)
            )
            conn.commit()

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# -------------------------
# ROUTES
# -------------------------
@app.get("/")
def home():
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "running"}


@app.post("/ingest")
def ingest_event(event: Event, bg: BackgroundTasks):

    print("🔥 INGEST STARTED")

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        event_dict = event.dict()

        violations = evaluate_rules(event_dict)

        is_anomaly = False

        if model:
            features = pd.DataFrame([{
                "retry_count": event.retry_count,
                "delay_minutes": event.delay_minutes
            }])
            prediction = model.predict(features)

            # ✅ FIX numpy.bool_
            is_anomaly = bool(prediction[0] == -1)

        if violations or is_anomaly:

            cursor.execute(
                """
                INSERT INTO exceptions (
                    transaction_id,
                    rule_violation,
                    event_data,
                    anomaly,
                    ai_status
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    event.transaction_id,
                    violations[0] if violations else "ML_ANOMALY",
                    json.dumps(event_dict),
                    is_anomaly,
                    "PENDING"
                )
            )

            conn.commit()

            # 🔥 Background AI
            bg.add_task(run_ai, event.transaction_id, event_dict)

            # 🔥 WebSocket notify
            asyncio.create_task(notify_clients())

        return {"status": "queued"}

    except Exception as e:
        print("❌ INGEST FAILED:", e)
        return {"error": str(e)}

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# -------------------------
# SYSTEM HEALTH
# -------------------------
@app.get("/system-health")
def system_health():
    import time

    try:
        conn = get_connection()
        conn.close()
        db_status = "OK"
    except:
        db_status = "FAIL"

    try:
        start = time.time()
        from langchain_groq import ChatGroq

        llm = ChatGroq(
            model="llama-3.1-8b-instant",
            api_key=os.getenv("GROQ_API_KEY")
        )
        llm.invoke("OK")

        latency = round(time.time() - start, 2)
        ai_status = "OK"
    except:
        ai_status = "FAIL"
        latency = None

    return {
        "db": db_status,
        "ai": ai_status,
        "latency": latency
    }


# -------------------------
# METRICS (FIXED 404)
# -------------------------
@app.get("/metrics")
def metrics():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM exceptions")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM exceptions WHERE rule_violation='HIGH_RETRY'")
    high_retry = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM exceptions WHERE rule_violation='SLA_DELAY'")
    sla_delay = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    return {
        "total_violations": total,
        "high_retry": high_retry,
        "sla_delay": sla_delay
    }


# -------------------------
# INSIGHTS
# -------------------------
@app.get("/insights")
def insights():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT transaction_id, rule_violation, root_cause, ai_status, created_at
        FROM exceptions
        ORDER BY created_at DESC
        LIMIT 20
    """)

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return [
        {
            "transaction_id": r[0],
            "rule_violation": r[1],
            "root_cause": r[2],
            "ai_status": r[3],
            "created_at": r[4]
        }
        for r in rows
    ]