import psycopg2

def get_connection():
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="erp_monitor",
        user="postgres",
        password="postgres"
    )
    return conn