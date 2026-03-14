import random
import time
import requests

API_URL = "http://localhost:8000/event"

systems = ["EDI", "NetSuite", "SAP"]
partners = ["Vendor-A", "Vendor-B", "Vendor-C"]

while True:

    event = {
        "transaction_id": f"TX{random.randint(1000,9999)}",
        "system": random.choice(systems),
        "partner": random.choice(partners),
        "retry_count": random.randint(0,10),
        "delay_minutes": random.randint(0,60)
    }

    try:
        response = requests.post(API_URL, json=event)
        print("Sent event:", event)
    except Exception as e:
        print("Error sending event:", e)

    time.sleep(1)