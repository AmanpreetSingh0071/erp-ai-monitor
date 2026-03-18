import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, BackgroundTasks
from backend.database import get_connection
from fastapi.middleware.cors import CORSMiddleware

import pandas as pd
import json
import joblib
from pydantic import BaseModel

from services.rule_engine.rule_engine import evaluate_rules

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

    print("🚀 APP STARTING...")

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
            print("⚠️ Model not found")

    except Exception as e:
        print("❌ Model load failed:", e)


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
def process_ai(transaction_id, event_dict):
    print(f"🧠 Processing AI for {transaction_id}")

    try:
        from services.ai.rag_root_cause import analyze_with_llm
        root_cause = analyze_with_llm(event_dict)
    except Exception as e:
        print("❌ AI failed:", e)
        root_cause = "Fallback: AI failed"

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE exceptions
        SET root_cause=%s, ai_status='DONE'
        WHERE transaction_id=%s
        """,
        (root_cause, transaction_id)
    )

    conn.commit()
    cursor.close()
    conn.close()

    print(f"✅ AI completed for {transaction_id}")


# -------------------------
# Routes
# -------------------------
@app.get("/")
def home():
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "running"}


@app.get("/ai-status/{tx_id}")
def ai_status(tx_id: str):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT root_cause, ai_status FROM exceptions WHERE transaction_id=%s",
        (tx_id,)
    )

    row = cursor.fetchone()

    cursor.close()
    conn.close()

    if not row:
        return {"status": "NOT_FOUND"}

    return {
        "root_cause": row[0],
        "ai_status": row[1]
    }


# -------------------------
# DEBUG: GROQ TEST
# -------------------------
@app.get("/test-groq")
def test_groq():
    import os
    from langchain_groq import ChatGroq

    try:
        llm = ChatGroq(
            model="llama-3.1-8b-instant",
            api_key=os.getenv("GROQ_API_KEY")
        )

        response = llm.invoke("Say OK")

        return {"status": "success", "response": response.content}

    except Exception as e:
        return {"status": "error", "error": str(e)}


# -------------------------
# DEBUG: RAG TEST
# -------------------------
@app.get("/test-rag")
def test_rag():
    import time
    from services.ai.rag_root_cause import init_rag, RETRIEVER

    try:
        start = time.time()

        if RETRIEVER is None:
            init_rag()

        docs = RETRIEVER.invoke("retry delay issue")

        return {
            "status": "success",
            "docs_found": len(docs),
            "time_taken": time.time() - start
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}


# -------------------------
# DEBUG: FULL AI TEST
# -------------------------
@app.get("/test-ai")
def test_ai():
    from services.ai.rag_root_cause import analyze_with_llm

    try:
        result = analyze_with_llm({
            "retry_count": 10,
            "delay_minutes": 60,
            "system": "SAP"
        })

        return {"status": "success", "result": result}

    except Exception as e:
        return {"status": "error", "error": str(e)}


# -------------------------
# INGEST (ASYNC)
# -------------------------
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
                root_cause,
                anomaly,
                ai_status
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                event.transaction_id,
                violations[0] if violations else "ML_ANOMALY",
                json.dumps(event_dict),
                None,
                is_anomaly,
                "PENDING"
            )
        )

        conn.commit()

        bg.add_task(process_ai, event.transaction_id, event_dict)

    try:
        print("📡 Connecting to DB...")
        conn = get_connection()
        cursor = conn.cursor()
        print("✅ DB connected")
    except Exception as e:
        print("❌ DB CONNECTION FAILED:", e)
        return {"error": "DB connection failed"}

    return {"status": "queued", "transaction_id": event.transaction_id}