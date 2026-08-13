"""
Two production fixes for erp-ai-monitor.

FIX 1 - services/ai/rag_root_cause.py
    TextLoader loads incidents.txt as ONE document, so FAISS holds a single
    chunk and "retrieval" returns the whole knowledge base every call
    (~2,759 tokens per agent run). Splitting on INCIDENT: boundaries gives 21
    chunks and genuine top-3 retrieval, cutting the prompt to ~399 tokens.
    That is ~7x more agent runs per day against the 70B's 100k token/day cap.

FIX 2 - backend/main.py
    retry_pending_ai() selects rows WHERE ai_status='PENDING' and spawns a
    thread per row, but never marks them as claimed. The worker re-polls every
    10s while Semaphore(1) serialises agents, so the same transactions get
    queued again and again behind the semaphore. Claiming rows atomically
    (PENDING -> PROCESSING) stops the duplicate spawning; a stale reclaim puts
    rows back to PENDING if a run dies mid-flight.

Run from the repo root:
    python fix_rag_and_worker.py
"""

import re
import sys
from pathlib import Path

RAG = Path("services/ai/rag_root_cause.py")
MAIN = Path("backend/main.py")


def patch_rag():
    src = RAG.read_text()
    changed = []

    if "RecursiveCharacterTextSplitter" in src:
        print("  rag: splitter already present, skipping")
    else:
        # add the import next to the existing loader import
        if "from langchain_community.document_loaders import TextLoader" in src:
            src = src.replace(
                "from langchain_community.document_loaders import TextLoader",
                "from langchain_community.document_loaders import TextLoader\n"
                "from langchain_text_splitters import RecursiveCharacterTextSplitter",
                1,
            )
        else:
            src = "from langchain_text_splitters import RecursiveCharacterTextSplitter\n" + src
        changed.append("import")

        old = """    loader = TextLoader(file_path)
    docs = loader.load()

    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    return FAISS.from_documents(docs, embeddings)"""

        new = """    loader = TextLoader(file_path)
    docs = loader.load()

    # Split into one chunk per incident. Without this the whole knowledge base
    # is a single document, so retrieval returns everything and the prompt
    # carries ~2,700 tokens on every agent call.
    splitter = RecursiveCharacterTextSplitter(
        separators=["\\nINCIDENT:", "\\n=== ", "\\n\\n", "\\n"],
        chunk_size=600,
        chunk_overlap=60,
    )
    chunks = splitter.split_documents(docs)
    print(f"\\U0001F4DA Knowledge base split into {len(chunks)} chunks")

    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    return FAISS.from_documents(chunks, embeddings)"""

        if old not in src:
            sys.exit("  rag: build_vectorstore body not found — file differs from expected")
        src = src.replace(old, new, 1)
        changed.append("chunking")

    if 'as_retriever(search_kwargs={"k": 3})' in src:
        print("  rag: k already set, skipping")
    else:
        if "RETRIEVER = VECTORSTORE.as_retriever()" not in src:
            sys.exit("  rag: as_retriever() call not found")
        src = src.replace(
            "RETRIEVER = VECTORSTORE.as_retriever()",
            'RETRIEVER = VECTORSTORE.as_retriever(search_kwargs={"k": 3})',
            1,
        )
        changed.append("k=3")

    if changed:
        RAG.write_text(src)
        print(f"  rag: patched ({', '.join(changed)})")


def patch_main():
    src = MAIN.read_text()

    if "ai_status='PROCESSING'" in src or 'ai_status=\'PROCESSING\'' in src:
        print("  main: worker already claims rows, skipping")
        return

    old = """    cursor.execute(
        \"\"\"
        SELECT transaction_id, event_data
        FROM exceptions
        WHERE ai_status='PENDING'
        LIMIT 5
        \"\"\"
    )

    rows = cursor.fetchall()"""

    new = """    # Reclaim anything left PROCESSING by a run that died mid-flight.
    cursor.execute(
        \"\"\"
        UPDATE exceptions
        SET ai_status='PENDING'
        WHERE ai_status='PROCESSING'
          AND updated_at < NOW() - INTERVAL '10 minutes'
        \"\"\"
    )

    # Claim rows atomically: mark them PROCESSING as we select them, so the
    # next poll (10s later) does not spawn duplicate threads for work that is
    # already queued behind the agent semaphore.
    cursor.execute(
        \"\"\"
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
        \"\"\"
    )

    rows = cursor.fetchall()
    conn.commit()"""

    if old not in src:
        sys.exit("  main: retry_pending_ai body not found — file differs from expected")

    src = src.replace(old, new, 1)
    MAIN.write_text(src)
    print("  main: patched (atomic claim + stale reclaim)")


def main():
    if not RAG.exists() or not MAIN.exists():
        sys.exit("Run this from the repo root (the folder containing services/ and backend/).")
    print("Patching:")
    patch_rag()
    patch_main()
    print("\nDone. Next:")
    print("  git diff --stat")
    print("  # start the backend locally and confirm the KB splits into 21 chunks")
    print("  # then commit and let Render redeploy")


if __name__ == "__main__":
    main()
