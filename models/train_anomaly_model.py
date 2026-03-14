import pandas as pd
from sklearn.ensemble import IsolationForest
import joblib
import random

# generate synthetic training data
data = []

for _ in range(1000):
    data.append({
        "retry_count": random.randint(0,5),
        "delay_minutes": random.randint(0,20)
    })

df = pd.DataFrame(data)

model = IsolationForest(contamination=0.05)

model.fit(df)

joblib.dump(model, "models/anomaly_model.pkl")

print("Model trained and saved.")