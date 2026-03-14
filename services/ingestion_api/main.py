from fastapi import FastAPI
from kafka import KafkaProducer
import json

app = FastAPI()

producer = KafkaProducer(
    bootstrap_servers="localhost:9092",
    value_serializer=lambda v: json.dumps(v).encode("utf-8")
)

@app.get("/")
def health_check():
    return {"status": "ERP monitoring API running"}

@app.post("/event")
def ingest_event(event: dict):

    producer.send("erp-events", event)

    return {
        "status": "event received",
        "event": event
    }