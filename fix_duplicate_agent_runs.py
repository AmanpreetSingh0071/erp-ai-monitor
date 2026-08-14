"""
Stop duplicate agent runs in backend/main.py.

PROBLEM
    Two code paths spawn run_ai():
      1. the /ingest and /simulate routes, immediately after inserting the row
      2. retry_pending_ai(), the 10s background poller

    Only the poller claimed rows. The ingest path left the row at PENDING while
    the agent was running, so the very next poll saw it as unclaimed work and
    spawned a second thread for the same transaction. Both ran, both called the
    LLM, and the row was processed twice — doubling token spend against the
    70B's 100k/day limit.

FIX
    Make run_ai() the single claim point. It atomically flips the row
    PENDING -> PROCESSING and only proceeds if it won that race; a losing thread
    exits immediately. The poller goes back to a plain SELECT, because the claim
    now happens downstream. The stale reclaim stays as the safety net for runs
    that die mid-flight.

Run from the repo root:
    python fix_duplicate_agent_runs.py
"""

import sys
from pathlib import Path

MAIN = Path("backend/main.py")

CLAIM_HELPER = '''
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
        print(f"\\u26a0\\ufe0f  Claim failed for {transaction_id}: {e}")
        # Fail open: better to risk a duplicate than to drop the work entirely.
        return True
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


'''

OLD_RUN_AI_HEAD = '''def run_ai(transaction_id, event_dict):
    """Entry point for background threads — delegates to the LangGraph agent."""

    print(f"🤖 Agent STARTED for {transaction_id}")
    with _agent_semaphore:'''

NEW_RUN_AI_HEAD = '''def run_ai(transaction_id, event_dict):
    """Entry point for background threads — delegates to the LangGraph agent."""

    # Single claim point. If another thread already owns this transaction we
    # stop here rather than queueing behind the semaphore and re-running it.
    if not claim_transaction(transaction_id):
        print(f"⏭️  Skipping {transaction_id} — already being processed")
        return

    print(f"🤖 Agent STARTED for {transaction_id}")
    with _agent_semaphore:'''

OLD_WORKER_CLAIM = '''    # Claim rows atomically: mark them PROCESSING as we select them, so the
    # next poll (10s later) does not spawn duplicate threads for work that is
    # already queued behind the agent semaphore.
    cursor.execute(
        """
        UPDATE exceptions
        SET ai_status='PROCESSING', updated_at=NOW()
        WHERE transaction_id IN (
            SELECT transaction_id
            FROM exceptions
            WHERE ai_status='PENDING'
            ORDER BY created_at
            LIMIT 5
            FOR UPDATE SKIP LOCKED
        )
        RETURNING transaction_id, event_data
        """
    )

    rows = cursor.fetchall()
    conn.commit()'''

NEW_WORKER_SELECT = '''    conn.commit()

    # Plain select — run_ai() claims each row, so the poller does not need to.
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

    rows = cursor.fetchall()'''


def main():
    if not MAIN.exists():
        sys.exit("Run this from the repo root (the folder containing backend/).")

    src = MAIN.read_text()

    if "def claim_transaction" in src:
        sys.exit("Already patched — claim_transaction() is present.")

    if OLD_RUN_AI_HEAD not in src:
        sys.exit("run_ai() header not found — file differs from what this patch expects.")
    if OLD_WORKER_CLAIM not in src:
        sys.exit("Worker claim block not found — did the earlier patch apply?")

    # insert helper immediately before run_ai
    marker = "def run_ai(transaction_id, event_dict):"
    src = src.replace(marker, CLAIM_HELPER.lstrip("\n") + marker, 1)

    src = src.replace(OLD_RUN_AI_HEAD, NEW_RUN_AI_HEAD, 1)
    src = src.replace(OLD_WORKER_CLAIM, NEW_WORKER_SELECT, 1)

    MAIN.write_text(src)
    print("Patched backend/main.py")
    print("  - claim_transaction(): atomic PENDING -> PROCESSING gate")
    print("  - run_ai(): claims before running, exits if it loses the race")
    print("  - retry_pending_ai(): back to a plain SELECT; stale reclaim kept")
    print("\nExpect in the logs: one 'Agent STARTED' and one 'Agent DONE' per")
    print("transaction, with occasional 'Skipping ... already being processed'.")


if __name__ == "__main__":
    main()
