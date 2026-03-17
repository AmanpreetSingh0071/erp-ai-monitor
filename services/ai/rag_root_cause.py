import os

from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq


# -------------------------
# Resolve ROOT path (Render-safe)
# -------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
file_path = os.path.join(BASE_DIR, "ai_knowledge", "incidents.txt")

print("📄 INCIDENT FILE PATH:", file_path)
print("Exists:", os.path.exists(file_path))


# -------------------------
# Lazy vectorstore (avoid heavy load crash)
# -------------------------
vectorstore = None


def get_vectorstore():
    global vectorstore

    if vectorstore is None:
        try:
            print("🔄 Building vectorstore...")

            loader = TextLoader(file_path)
            docs = loader.load()

            embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2"
            )

            vectorstore = FAISS.from_documents(docs, embeddings)

            print("✅ Vectorstore ready")

        except Exception as e:
            print("❌ VECTORSTORE ERROR:", str(e))
            vectorstore = None

    return vectorstore


# -------------------------
# LLM Root Cause Analysis
# -------------------------
def analyze_with_llm(event):

    try:
        # -------------------------
        # Get context (RAG)
        # -------------------------
        vs = get_vectorstore()

        context = ""

        if vs:
            retriever = vs.as_retriever()

            docs = retriever.invoke(
                f"retry count {event['retry_count']} delay {event['delay_minutes']}"
            )

            context = "\n".join([d.page_content for d in docs])

        # -------------------------
        # LLM (Groq)
        # -------------------------
        groq_key = os.getenv("GROQ_API_KEY")

        if not groq_key:
            raise Exception("GROQ_API_KEY missing")

        llm = ChatGroq(
            model="llama-3.1-8b-instant",
            api_key=groq_key
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

        return response.content

    except Exception as e:
        print("❌ LLM ERROR:", str(e))

        # -------------------------
        # Fallback (VERY IMPORTANT)
        # -------------------------
        if event["retry_count"] > 5:
            return "High retry count indicates repeated failures, possibly due to integration or endpoint issues."

        if event["delay_minutes"] > 30:
            return "High delay suggests SLA breach, likely caused by processing backlog or system latency."

        return "Minor anomaly detected in ERP transaction processing."