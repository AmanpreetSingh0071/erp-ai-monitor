import random
import time
import requests

API_URL = "https://erp-ai-monitor.onrender.com/ingest"

systems = ["EDI", "NetSuite", "SAP"]
partners = ["Vendor-A", "Vendor-B", "Vendor-C"]

for _ in range(10):

    event = {
        "transaction_id": f"TX{random.randint(1000,99999)}",
        "system": random.choice(systems),
        "partner": random.choice(partners),
        "retry_count": random.randint(0,15),
        "delay_minutes": random.randint(0,90)
    }

    try:
        response = requests.post(API_URL, json=event)
        print("Sent:", event, "| Status:", response.status_code)
    except Exception as e:
        print("Error sending event:", e)

    time.sleep(2)