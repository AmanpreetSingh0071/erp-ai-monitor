import os
import time
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

VECTORSTORE = None
RETRIEVER = None


def build_vectorstore():
    file_path = os.path.join(BASE_DIR, "ai_knowledge", "incidents.txt")

    print("📄 Loading knowledge:", file_path)

    loader = TextLoader(file_path)
    docs = loader.load()

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={"device": "cpu"}
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

    if RETRIEVER is None:
        print("⚡ Lazy loading RAG...")
        init_rag()

    # -------------------------
    # RAG timing
    # -------------------------
    rag_start = time.time()

    docs = RETRIEVER.invoke(
        f"retry count {event['retry_count']} delay {event['delay_minutes']}"
    )

    context = "\n".join([d.page_content for d in docs])

    print(f"📚 RAG time: {time.time() - rag_start:.2f}s")

    # -------------------------
    # GROQ timing
    # -------------------------
    print("🔑 GROQ KEY:", os.getenv("GROQ_API_KEY"))

    try:
        llm_start = time.time()

        llm = ChatGroq(
            model="llama-3.1-8b-instant",
            api_key=os.getenv("GROQ_API_KEY")
        )

        response = llm.invoke(f"""
Context:
{context}

Retry: {event["retry_count"]}
Delay: {event["delay_minutes"]}
System: {event["system"]}
""")

        print(f"🤖 GROQ time: {time.time() - llm_start:.2f}s")

        return response.content

    except Exception as e:
        print("❌ GROQ FAILED:", e)
        return "Fallback: AI unavailable"