import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

print("🚀 APP STARTING...")

from fastapi import FastAPI, BackgroundTasks
from backend.database import get_connection
from fastapi.middleware.cors import CORSMiddleware

import pandas as pd
import json
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
        init_rag()
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
# BACKGROUND AI TASK
# -------------------------
def run_ai(transaction_id, event_dict):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        result = analyze_with_llm(event_dict)

        cursor.execute(
            """
            UPDATE exceptions
            SET root_cause=%s, ai_status='DONE'
            WHERE transaction_id=%s
            """,
            (result["root_cause"], transaction_id)
        )

    except Exception as e:
        print("❌ AI FAILED:", e)

        cursor.execute(
            """
            UPDATE exceptions
            SET root_cause=%s, ai_status='FAILED'
            WHERE transaction_id=%s
            """,
            (str(e), transaction_id)
        )

    conn.commit()
    cursor.close()
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

    conn = get_connection()
    cursor = conn.cursor()

    event_dict = event.dict()

    violations = evaluate_rules(event_dict)

    is_anomaly = False
    if model:
        try:
            features = pd.DataFrame([{
                "retry_count": event.retry_count,
                "delay_minutes": event.delay_minutes
            }])
            prediction = model.predict(features)
            is_anomaly = prediction[0] == -1
        except Exception as e:
            print("ML failed:", e)

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

        # 🔥 BACKGROUND AI
        bg.add_task(run_ai, event.transaction_id, event_dict)

    cursor.close()
    conn.close()

    return {"status": "queued", "transaction_id": event.transaction_id}


# -------------------------
# DEBUG ENDPOINTS
# -------------------------

@app.get("/test-groq")
def test_groq():
    try:
        start = time.time()

        from langchain_groq import ChatGroq

        llm = ChatGroq(
            model="llama-3.1-8b-instant",
            api_key=os.getenv("GROQ_API_KEY")
        )

        response = llm.invoke("Say OK")

        return {
            "status": "success",
            "response": response.content,
            "latency": round(time.time() - start, 2)
        }

    except Exception as e:
        return {"status": "failed", "error": str(e)}


@app.get("/test-rag")
def test_rag():
    try:
        result = analyze_with_llm({
            "retry_count": 5,
            "delay_minutes": 20,
            "system": "SAP"
        })

        return {
            "status": "success",
            "timings": result
        }

    except Exception as e:
        return {"status": "failed", "error": str(e)}


@app.get("/ai-status/{tx_id}")
def ai_status(tx_id: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT ai_status, root_cause FROM exceptions WHERE transaction_id=%s",
        (tx_id,)
    )

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    if not row:
        return {"error": "not found"}

    return {
        "status": row[0],
        "root_cause": row[1]
    }