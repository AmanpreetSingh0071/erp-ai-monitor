from fastapi import FastAPI
from database import get_connection
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="ERP AI Monitoring API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # allow all origins for development
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"message": "ERP AI Monitoring API running"}


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


@app.get("/metrics")
def get_metrics():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM exceptions")
    total = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM exceptions
        WHERE rule_violation='HIGH_RETRY'
    """)
    high_retry = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM exceptions
        WHERE rule_violation='SLA_DELAY'
    """)
    sla_delay = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    return {
        "total_violations": total,
        "high_retry": high_retry,
        "sla_delay": sla_delay
    }

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

@app.get("/health")
def health():
    return {"status": "running"}