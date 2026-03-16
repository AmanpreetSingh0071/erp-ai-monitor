import os
import psycopg2
from urllib.parse import urlparse

DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL environment variable not set")

    url = urlparse(DATABASE_URL)

    conn = psycopg2.connect(
        host=url.hostname,
        database=url.path[1:],   # remove leading '/'
        user=url.username,
        password=url.password,
        port=url.port
    )

    return conn