from dotenv import load_dotenv
load_dotenv()

import sys
import os
import time
import json
import asyncio
import threading
_agent_semaphore = threading.Semaphore(1)
import random

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

print("APP STARTING...")

from fastapi import FastAPI, BackgroundTasks, WebSocket
from backend.database import get_connection
from fastapi.middleware.cors import CORSMiddleware

import pandas as pd
import joblib
from pydantic import BaseModel

from services.rule_engine.rule_engine import evaluate_rules
from services.ai.rag_root_cause import init_rag
from services.agent.erp_agent import init_agent, run_agent

app = FastAPI(title="ERP AI Monitoring API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

model = None
active_connections = []


# -------------------------
# STARTUP
# -------------------------
@app.on_event("startup")
def startup_event():
    global model

    print("Training detection model...")

    # Trained in-process rather than loaded from a pickle. Training is
    # deterministic (seed 42) and takes milliseconds, so the served model is
    # provably the one described in Section 3.3 and Appendix B, rather than
    # whatever pickle happens to be present. It also removes a scikit-learn
    # version coupling between the training machine and the deployment.
    try:
        import importlib.util

        _tam_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "models",
            "train_anomaly_model.py",
        )
        _spec = importlib.util.spec_from_file_location("train_anomaly_model", _tam_path)
        _tam = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_tam)

        model, _samples = _tam.train()
        print(
            f"OK: Model trained: L-region, {_tam.N_SAMPLES} samples, "
            f"{_tam.N_ESTIMATORS} estimators, seed {_tam.RANDOM_SEED}"
        )

    except Exception as e:
        print("ERROR: Model training error:", e)

    try:
        print("Initializing RAG...")
        init_rag()
        print("OK: RAG ready")
    except Exception as e:
        print("ERROR: RAG init failed:", e)

    try:
        print("Initializing LangGraph agent...")
        init_agent()
    except Exception as e:
        print("ERROR: Agent init failed:", e)

    # Ensure agent columns exist (idempotent migration)
    try:
        _conn = get_connection()
        _cur = _conn.cursor()
        _cur.execute("""
            ALTER TABLE exceptions
            ADD COLUMN IF NOT EXISTS agent_decision VARCHAR(20),
            ADD COLUMN IF NOT EXISTS confidence_score FLOAT
        """)
        _conn.commit()
        _cur.close()
        _conn.close()
        print("OK: DB columns verified")
    except Exception as e:
        print("ERROR: DB migration failed:", e)

    def background_worker():
        retry_delay = 10

        while True:
            try:
                retry_pending_ai()
                retry_delay = 10

            except Exception as e:
                print("ERROR: Worker error:", e)
                retry_delay = min(retry_delay * 2, 300)  # exponential backoff (max 5 min)

            time.sleep(retry_delay)

    threading.Thread(target=background_worker, daemon=True).start()


# -------------------------
# SCHEMA
# -------------------------
class Event(BaseModel):
    transaction_id: str
    system: str
    partner: str
    retry_count: int
    delay_minutes: int


# -------------------------
# WEBSOCKET
# -------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)

    try:
        while True:
            await websocket.receive_text()
    except:
        active_connections.remove(websocket)


async def notify_clients():
    for ws in active_connections:
        await ws.send_text("new_event")


# -------------------------
# AI PROCESS (LangGraph agent)
# -------------------------
def claim_transaction(transaction_id):
    """Atomically take ownership of a transaction.

    Returns True if this thread won the claim, False if another thread is
    already processing it. This is the single gate for agent runs: both the
    ingest path and the retry poller call run_ai(), so the claim has to live
    here rather than in either caller.
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE exceptions
            SET ai_status='PROCESSING', updated_at=NOW()
            WHERE transaction_id=%s
              AND (ai_status IS NULL OR ai_status='PENDING')
            RETURNING transaction_id
            """,
            (transaction_id,),
        )
        won = cursor.fetchone() is not None
        conn.commit()
        return won
    except Exception as e:
        print(f"WARNING: Claim failed for {transaction_id}: {e}")
        # Fail open: better to risk a duplicate than to drop the work entirely.
        return True
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def run_ai(transaction_id, event_dict):
    """Entry point for background threads: delegates to the LangGraph agent."""

    # Single claim point. If another thread already owns this transaction we
    # stop here rather than queueing behind the semaphore and re-running it.
    if not claim_transaction(transaction_id):
        print(f"Skipping {transaction_id} — already being processed")
        return

    print(f"Agent STARTED for {transaction_id}")
    with _agent_semaphore:

        try:
            run_agent(transaction_id, event_dict)

        except Exception as e:
            print(f"ERROR: Agent FAILED for {transaction_id}: {e}")

            # Mark the row so the retry worker can pick it up
            conn = None
            cursor = None
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE exceptions
                    SET root_cause=%s,
                        ai_status='FAILED',
                        updated_at=NOW()
                    WHERE transaction_id=%s
                    """,
                    (str(e), transaction_id),
                )
                conn.commit()
            except Exception as db_err:
                print(f"ERROR: Could not mark FAILED in DB: {db_err}")
            finally:
                if cursor:
                    cursor.close()
                if conn:
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

    print("INGEST STARTED")

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        event_dict = event.dict()
        violations = evaluate_rules(event_dict)

        is_anomaly = False

        if model:
            features = pd.DataFrame([{
                "retry_count": event.retry_count,
                "delay_minutes": event.delay_minutes
            }])
            prediction = model.predict(features)
            is_anomaly = bool(prediction[0] == -1)

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

            threading.Thread(
                target=run_ai,
                args=(event.transaction_id, event_dict),
                daemon=True
            ).start()

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(notify_clients())
            except RuntimeError:
                pass

        return {"status": "queued"}

    except Exception as e:
        print("ERROR: INGEST FAILED:", e)
        return {"error": str(e)}

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# -------------------------
# SIMULATE TRAFFIC
# -------------------------
@app.post("/simulate")
def simulate_events():

    print("Simulating traffic...")

    conn = get_connection()
    cursor = conn.cursor()

    systems = ["EDI", "NetSuite", "SAP"]
    partners = ["Vendor-A", "Vendor-B", "Vendor-C"]

    for _ in range(5):
        event = {
            "transaction_id": f"TX{random.randint(10000,99999)}",
            "system": random.choice(systems),
            "partner": random.choice(partners),
            "retry_count": random.randint(0, 15),
            "delay_minutes": random.randint(0, 90)
        }

        violations = evaluate_rules(event)

        if violations:
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
                    event["transaction_id"],
                    violations[0],
                    json.dumps(event),
                    False,
                    "PENDING"
                )
            )

            threading.Thread(
                target=run_ai,
                args=(event["transaction_id"], event),
                daemon=True
            ).start()

    conn.commit()
    cursor.close()
    conn.close()

    return {"status": "simulated"}


# -------------------------
# RETRY WORKER
# -------------------------
def retry_pending_ai():
    print("Checking pending AI jobs...")

    conn = get_connection()
    cursor = conn.cursor()

    # Reclaim anything left PROCESSING by a run that died mid-flight.
    cursor.execute(
        """
        UPDATE exceptions
        SET ai_status='PENDING'
        WHERE ai_status='PROCESSING'
          AND updated_at < NOW() - INTERVAL '10 minutes'
        """
    )

    conn.commit()

    # Plain select: run_ai() claims each row, so the poller does not need to.
    # Anything already PROCESSING is skipped by the WHERE clause.
    cursor.execute(
        """
        SELECT transaction_id, event_data
        FROM exceptions
        WHERE ai_status='PENDING'
        ORDER BY created_at
        LIMIT 5
        """
    )

    rows = cursor.fetchall()

    for tx_id, event_data in rows:
        try:
            print(f"Retrying AI for {tx_id}")

            if not event_data:
                continue

            if isinstance(event_data, str):
                event_dict = json.loads(event_data)
            else:
                event_dict = event_data

            threading.Thread(
                target=run_ai,
                args=(tx_id, event_dict),
                daemon=True
            ).start()

        except Exception as e:
            print("ERROR: Retry failed:", e)

    cursor.close()
    conn.close()


# -------------------------
# SYSTEM HEALTH
# -------------------------
@app.get("/system-health")
def system_health():
    return {"db": "OK", "ai": "OK", "latency": 0.2}


# -------------------------
# METRICS
# -------------------------
@app.get("/metrics")
def metrics():
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

    return {"total_violations": total,"high_retry":high_retry,"sla_delay":sla_delay}


# -------------------------
# INSIGHTS
# -------------------------
@app.get("/insights")
def insights():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT transaction_id, rule_violation, root_cause, ai_status, created_at,
               agent_decision, confidence_score
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
            "root_cause": r[2],
            "ai_status": r[3],
            "created_at": r[4],
            "agent_decision": r[5],
            "confidence_score": r[6],
        }
        for r in rows
    ]