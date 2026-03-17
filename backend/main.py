import sys
import os

# Fix import path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

print("🚀 APP STARTING...")

from fastapi import FastAPI
from backend.database import get_connection
from fastapi.middleware.cors import CORSMiddleware

import pandas as pd
import json
import joblib
from pydantic import BaseModel

from services.rule_engine.rule_engine import evaluate_rules


# -------------------------
# App
# -------------------------
app = FastAPI(title="ERP AI Monitoring API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Global Model
# -------------------------
model = None


# -------------------------
# STARTUP (MODEL ONLY - NON BLOCKING)
# -------------------------
@app.on_event("startup")
def startup_event():
    global model

    print("🚀 FastAPI startup triggered")

    try:
        model_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "models",
            "anomaly_model.pkl"
        )

        print("📦 Model path:", model_path)

        if os.path.exists(model_path):
            model = joblib.load(model_path)
            print("✅ Model loaded")
        else:
            print("⚠️ Model NOT found — running without ML")

    except Exception as e:
        print("❌ Model load failed:", e)


# -------------------------
# Event Schema
# -------------------------
class Event(BaseModel):
    transaction_id: str
    system: str
    partner: str
    retry_count: int
    delay_minutes: int


# -------------------------
# Routes
# -------------------------
@app.get("/")
def home():
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "running"}


@app.get("/metrics")
def get_metrics():
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


@app.get("/violations")
def get_violations():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT transaction_id, rule_violation, created_at
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
            "created_at": r[2]
        }
        for r in rows
    ]


@app.get("/violations/distribution")
def violations_distribution():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT rule_violation, COUNT(*)
        FROM exceptions
        GROUP BY rule_violation
    """)

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return {r[0]: r[1] for r in rows}


@app.get("/insights")
def get_insights():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT transaction_id, rule_violation, root_cause, created_at
        FROM exceptions
        WHERE root_cause IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 10
    """)

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return [
        {
            "transaction_id": r[0],
            "rule_violation": r[1],
            "root_cause": r[2],
            "created_at": r[3]
        }
        for r in rows
    ]


# -------------------------
# Ingestion API
# -------------------------
@app.post("/ingest")
def ingest_event(event: Event):

    print("🔥 /ingest called")

    conn = get_connection()
    cursor = conn.cursor()

    event_dict = event.dict()

    # -------------------------
    # Rule Engine
    # -------------------------
    violations = evaluate_rules(event_dict)

    # -------------------------
    # ML Detection
    # -------------------------
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

    # -------------------------
    # Process only if issue
    # -------------------------
    if violations or is_anomaly:

        # ✅ LAZY LOAD RAG HERE (NO STARTUP BLOCK)
        try:
            from services.ai.rag_root_cause import analyze_with_llm
            root_cause = analyze_with_llm(event_dict)
        except Exception as e:
            print("LLM failed:", e)
            root_cause = "Fallback: Possible delay or integration issue"

        # -------------------------
        # Save to DB
        # -------------------------
        if violations:
            for rule in violations:
                cursor.execute(
                    """
                    INSERT INTO exceptions (
                        transaction_id,
                        rule_violation,
                        event_data,
                        root_cause,
                        anomaly
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        event.transaction_id,
                        rule,
                        json.dumps(event_dict),
                        root_cause,
                        is_anomaly
                    )
                )
        else:
            cursor.execute(
                """
                INSERT INTO exceptions (
                    transaction_id,
                    rule_violation,
                    event_data,
                    root_cause,
                    anomaly
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    event.transaction_id,
                    "ML_ANOMALY",
                    json.dumps(event_dict),
                    root_cause,
                    True
                )
            )

        conn.commit()

    cursor.close()
    conn.close()

    return {"status": "processed"}