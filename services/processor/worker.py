import joblib
import pandas as pd
import psycopg2
import json

from services.ai.rag_root_cause import analyze_with_llm
from services.alerts.alert_service import send_alert
from services.rule_engine.rule_engine import evaluate_rules
from kafka import KafkaConsumer

# load ML model
model = joblib.load("models/anomaly_model.pkl")

# database connection
conn = psycopg2.connect(
    dbname="erp_monitor",
    user="postgres",
    password="postgres",
    host="localhost",
    port=5432
)

cursor = conn.cursor()

# kafka consumer
consumer = KafkaConsumer(
    "erp-events",
    bootstrap_servers="localhost:9092",
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    auto_offset_reset="latest",
    enable_auto_commit=True,
    group_id="erp-monitor-group"
)

print("Worker started. Waiting for events...")

for message in consumer:

    event = message.value
    print("Event received:", event)

    # -------------------------
    # Rule Engine
    # -------------------------
    violations = evaluate_rules(event)

    if violations:
        print("Rule violations detected:", violations)
        send_alert(event, violations=violations)

        for rule in violations:
            cursor.execute(
                """
                INSERT INTO exceptions (transaction_id, rule_violation, event_data)
                VALUES (%s, %s, %s)
                """,
                (event["transaction_id"], rule, json.dumps(event))
            )

        conn.commit()

    # -------------------------
    # ML Anomaly Detection
    # -------------------------
    features = pd.DataFrame([{
        "retry_count": event["retry_count"],
        "delay_minutes": event["delay_minutes"]
    }])

    prediction = model.predict(features)

    if prediction[0] == -1:
        
        print("AI Anomaly detected:", event)

        cause = analyze_with_llm(event)

        print("\nAI Root Cause Analysis:")
        print(cause)
        
        send_alert(event, anomaly=True)