import os
import time
import json
import re

from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import FakeEmbeddings
from langchain_groq import ChatGroq

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

VECTORSTORE = None
RETRIEVER = None


# -------------------------
# BUILD VECTOR STORE
# -------------------------
def build_vectorstore():
    file_path = os.path.join(BASE_DIR, "ai_knowledge", "incidents.txt")

    if not os.path.exists(file_path):
        raise Exception("incidents.txt NOT FOUND")

    loader = TextLoader(file_path)
    docs = loader.load()

    embeddings = FakeEmbeddings(size=384)

    return FAISS.from_documents(docs, embeddings)


# -------------------------
# INIT RAG
# -------------------------
def init_rag():
    global VECTORSTORE, RETRIEVER

    start = time.time()

    VECTORSTORE = build_vectorstore()
    RETRIEVER = VECTORSTORE.as_retriever()

    print(f"✅ RAG initialized in {round(time.time() - start, 2)}s")


# -------------------------
# CLEAN JSON FROM LLM OUTPUT
# -------------------------
def extract_json(text):
    try:
        # remove markdown if present
        text = text.strip()
        text = re.sub(r"```json|```", "", text).strip()

        # find JSON block
        start = text.find("{")
        end = text.rfind("}") + 1

        if start != -1 and end != -1:
            return json.loads(text[start:end])

    except Exception as e:
        print("⚠️ JSON extraction failed:", e)

    return None


# -------------------------
# ANALYZE WITH LLM
# -------------------------
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
You are an ERP monitoring AI system for enterprise integrations (Oracle NetSuite, SAP)

Analyze the event and return ONLY valid JSON.

Context:
{context}

Event:
Retry Count: {event["retry_count"]}
Delay Minutes: {event["delay_minutes"]}
System: {event["system"]}

STRICT RULES:
- Output ONLY JSON
- No explanations
- No markdown
- No extra text

FORMAT:
{{
  "root_cause": "Short precise cause (max 1 sentence)",
  "impact": "Business impact (SLA breach, delays, revenue impact)",
  "recommendation": "Specific/Exact actionable fix (include config/API/retry/logs)"
}}
"""

    response = llm.invoke(prompt)

    llm_time = round(time.time() - start_llm, 2)
    total_time = round(time.time() - start_total, 2)

    print(f"📊 RAG: {rag_time}s | LLM: {llm_time}s | TOTAL: {total_time}s")

    raw_output = response.content
    print("🧠 RAW LLM OUTPUT:", raw_output)

    # -------- SAFE PARSE ----------
    parsed = extract_json(raw_output)

    if parsed:
        return {
            "root_cause": parsed.get("root_cause", "").strip(),
            "impact": parsed.get("impact", "").strip(),
            "recommendation": parsed.get("recommendation", "").strip(),
            "rag_time": rag_time,
            "llm_time": llm_time,
            "total_time": total_time
        }

    # -------- FALLBACK ----------
    print("⚠️ Using fallback response")

    return {
        "root_cause": raw_output.strip(),
        "impact": "Potential SLA breach or system delay",
        "recommendation": "Check logs, retry configuration, and API health",
        "rag_time": rag_time,
        "llm_time": llm_time,
        "total_time": total_time
    }