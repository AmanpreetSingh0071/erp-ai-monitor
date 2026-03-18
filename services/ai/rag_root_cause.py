import os
import time

from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import FakeEmbeddings
from langchain_groq import ChatGroq

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

VECTORSTORE = None
RETRIEVER = None


def build_vectorstore():
    file_path = os.path.join(BASE_DIR, "ai_knowledge", "incidents.txt")

    if not os.path.exists(file_path):
        raise Exception("incidents.txt NOT FOUND")

    loader = TextLoader(file_path)
    docs = loader.load()

    embeddings = FakeEmbeddings(size=384)

    return FAISS.from_documents(docs, embeddings)


def init_rag():
    global VECTORSTORE, RETRIEVER

    start = time.time()

    VECTORSTORE = build_vectorstore()
    RETRIEVER = VECTORSTORE.as_retriever()

    print(f"✅ RAG initialized in {round(time.time() - start, 2)}s")


def analyze_with_llm(event):
    if RETRIEVER is None:
        raise Exception("RAG NOT INITIALIZED")

    start_total = time.time()

    # -------- RAG retrieval ----------
    start_rag = time.time()

    docs = RETRIEVER.invoke(
        f"retry {event['retry_count']} delay {event['delay_minutes']} system {event['system']}"
    )

    rag_time = round(time.time() - start_rag, 2)

    context = "\n".join([d.page_content for d in docs])

    # -------- LLM ----------
    start_llm = time.time()

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise Exception("GROQ_API_KEY NOT SET")

    llm = ChatGroq(
        model="llama-3.1-8b-instant",
        api_key=api_key
    )

    prompt = f"""
You are an ERP monitoring AI.

Context:
{context}

Event:
Retry Count: {event["retry_count"]}
Delay Minutes: {event["delay_minutes"]}
System: {event["system"]}

Explain the most likely root cause in 1-2 lines.
"""

    response = llm.invoke(prompt)

    llm_time = round(time.time() - start_llm, 2)
    total_time = round(time.time() - start_total, 2)

    print(f"📊 RAG: {rag_time}s | LLM: {llm_time}s | TOTAL: {total_time}s")

    return {
        "root_cause": response.content,
        "rag_time": rag_time,
        "llm_time": llm_time,
        "total_time": total_time
    }