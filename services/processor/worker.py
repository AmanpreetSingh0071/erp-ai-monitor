"""
SUPERSEDED. Not part of the running system.

An earlier Kafka-based processing path, kept as a record of the design
decision described in the findings log. The deployed system uses in-process
background threads in backend/main.py instead. This module is not imported
anywhere and requires kafka, which is not in requirements.txt, so it cannot
run as shipped.

The detector is now trained in-process from models/train_anomaly_model.py
rather than loaded from a pickle, so that the served model provably matches
the parameters documented in Appendix B.
"""

import joblib
import pandas as pd
import psycopg2
import json
import os

from services.ai.rag_root_cause import analyze_with_llm
from services.alerts.alert_service import send_alert
from services.rule_engine.rule_engine import evaluate_rules
from kafka import KafkaConsumer
from urllib.parse import urlparse


# -------------------------
# Load ML model (once)
# -------------------------
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "train_anomaly_model",
    os.path.join(os.path.dirname(__file__), "..", "..", "models",
                 "train_anomaly_model.py"),
)
_tam = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_tam)
model, _ = _tam.train()


# -------------------------
# Database Connection
# -------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("DATABASE_URL is not set")

url = urlparse(DATABASE_URL)

conn = psycopg2.connect(
    host=url.hostname,
    database=url.path[1:],
    user=url.username,
    password=url.password,
    port=url.port
)

cursor = conn.cursor()


# -------------------------
# Kafka Consumer
# -------------------------
consumer = KafkaConsumer(
    "erp-events",
    bootstrap_servers="localhost:9092",
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    auto_offset_reset="latest",
    enable_auto_commit=True,
    group_id="erp-monitor-group"
)

print("Worker started. Waiting for events...")


# -------------------------
# Event Processing Loop
# -------------------------
while True:
    event = {
        "transaction_id": "TX9999",
        "system": "SAP",
        "partner": "Vendor-X",
        "retry_count": 10,
        "delay_minutes": 60
    }
    print("\nEvent received:", event)

    # -------------------------
    # Rule Engine
    # -------------------------
    violations = evaluate_rules(event)

    # -------------------------
    # ML Anomaly Detection
    # -------------------------
    features = pd.DataFrame([{
        "retry_count": event["retry_count"],
        "delay_minutes": event["delay_minutes"]
    }])

    prediction = model.predict(features)
    is_anomaly = prediction[0] == -1

    # -------------------------
    # Unified Handling
    # -------------------------
    if violations or is_anomaly:

        print("Issue detected:", {
            "violations": violations,
            "anomaly": is_anomaly
        })

        # -------------------------
        # LLM Root Cause Analysis
        # -------------------------
        ai_result = analyze_with_llm(event)

        print("\nAI Root Cause Analysis:")
        print(ai_result)

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
                        event["transaction_id"],
                        rule,
                        json.dumps(event),
                        ai_result,
                        is_anomaly
                    )
                )
        else:
            # anomaly only (no rule triggered)
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
                    event["transaction_id"],
                    "ML_ANOMALY",
                    json.dumps(event),
                    ai_result,
                    True
                )
            )

        conn.commit()

        # -------------------------
        # Send ONE alert
        # -------------------------
        send_alert(
            event,
            violations=violations,
            anomaly=is_anomaly,
            root_cause=ai_result
        )