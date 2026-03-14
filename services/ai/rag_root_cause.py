from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq


def build_vectorstore():

    loader = TextLoader("ai_knowledge/incidents.txt")
    docs = loader.load()

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    vectorstore = FAISS.from_documents(docs, embeddings)

    return vectorstore


def analyze_with_llm(event):

    vectorstore = build_vectorstore()

    retriever = vectorstore.as_retriever()

    docs = retriever.invoke(
        f"retry count {event['retry_count']} delay {event['delay_minutes']}"
    )

    context = "\n".join([d.page_content for d in docs])

    llm = ChatGroq(
        model="llama-3.3-70b-versatile"
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