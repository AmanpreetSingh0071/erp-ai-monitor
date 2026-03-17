from fastapi import FastAPI
from database import get_connection
from fastapi.middleware.cors import CORSMiddleware

import pandas as pd
import json
import joblib

from pydantic import BaseModel
from services.ai.rag_root_cause import analyze_with_llm
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
# Load ML model
# -------------------------
model = joblib.load("models/anomaly_model.pkl")


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
    return {"message": "ERP AI Monitoring API running"}


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
# 🔥 NEW: Ingestion API (Kafka replacement)
# -------------------------
@app.post("/ingest")
def ingest_event(event: Event):

    conn = get_connection()
    cursor = conn.cursor()

    event_dict = event.dict()

    # -------------------------
    # Rule Engine
    # -------------------------
    violations = evaluate_rules(event_dict)

    # -------------------------
    # ML Prediction
    # -------------------------
    features = pd.DataFrame([{
        "retry_count": event.retry_count,
        "delay_minutes": event.delay_minutes
    }])

    prediction = model.predict(features)
    is_anomaly = prediction[0] == -1

    # -------------------------
    # If issue detected
    # -------------------------
    if violations or is_anomaly:

        root_cause = analyze_with_llm(event_dict)

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