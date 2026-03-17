import os
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

VECTORSTORE = None
RETRIEVER = None


def build_vectorstore():
    file_path = os.path.join(BASE_DIR, "ai_knowledge", "incidents.txt")

    print("📄 Loading knowledge from:", file_path)

    loader = TextLoader(file_path)
    docs = loader.load()

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"}   # 🔥 IMPORTANT (avoid GPU)
    )

    return FAISS.from_documents(docs, embeddings)


def init_rag():
    global VECTORSTORE, RETRIEVER

    if VECTORSTORE is not None:
        return

    print("🔄 Building vectorstore...")

    VECTORSTORE = build_vectorstore()
    RETRIEVER = VECTORSTORE.as_retriever()

    print("✅ Vectorstore ready")


def analyze_with_llm(event):
    global RETRIEVER

    # 🔥 LAZY LOAD (CRITICAL FIX)
    if RETRIEVER is None:
        print("⚡ Lazy loading RAG...")
        init_rag()

    docs = RETRIEVER.invoke(
        f"retry count {event['retry_count']} delay {event['delay_minutes']}"
    )

    context = "\n".join([d.page_content for d in docs])

    try:
        llm = ChatGroq(
            model="llama-3.1-8b-instant",
            api_key=os.getenv("GROQ_API_KEY")
        )

        prompt = f"""
You are an ERP monitoring AI.

Context:
{context}

Event:
Retry Count: {event["retry_count"]}
Delay Minutes: {event["delay_minutes"]}
System: {event["system"]}

Explain the most likely root cause.
"""

        response = llm.invoke(prompt)
        return response.content

    except Exception as e:
        print("❌ LLM failed:", e)
        return "Fallback: Possible delay or integration issue"