import psycopg2
import os

DATABASE_URL = os.environ["DATABASE_URL"]

def connect():
    return psycopg2.connect(DATABASE_URL)

def save_signal(symbol, side, price):

    conn = connect()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO signals(symbol,side,price,version)
        VALUES(%s,%s,%s,%s)
        """,
        (symbol,side,price,"EMA9")
    )

    conn.commit()

    cur.close()
    conn.close()


def get_open_position(symbol):

    conn = connect()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT side
        FROM signals
        WHERE symbol=%s
        ORDER BY id DESC
        LIMIT 1
        """,
        (symbol,)
    )

    row = cur.fetchone()

    cur.close()
    conn.close()

    if row:
        return row[0]

    return None
