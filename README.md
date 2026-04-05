# ERP AI Monitoring System

An end-to-end AI-powered monitoring platform for ERP transactions that detects anomalies, performs root cause analysis using LLMs, and presents insights in a real-time dashboard.

## 🚀 Live Demo
- Frontend: https://erp-ai-monitor.vercel.app  
- Backend: https://erp-ai-monitor.onrender.com

> If backend is sleeping: click **Start Backend** → wait ~10–20s → click **Simulate Traffic**

---

## 🧠 What it does

- Monitors ERP events (SAP / NetSuite / EDI)
- Detects issues via:
  - Rule Engine (threshold-based)
  - ML Model (anomaly detection)
- Uses LLM (RAG) to generate:
  - Root Cause
  - Business Impact
  - Recommended Fix
- Displays results in a real-time dashboard

---

## 🏗️ Architecture

Frontend (React - Vercel)
        ↓
FastAPI Backend (Render)
        ↓
PostgreSQL (Events + Results)
        ↓
AI Layer
  - Rule Engine
  - ML Model (Isolation Forest)
  - LLM (Groq + RAG)

---

## ⚙️ Key Features

- Real-time monitoring dashboard
- Async AI processing (background threads)
- Retry worker for failed AI jobs
- RAG-based contextual reasoning
- Auto wake-up + simulate traffic controls
- WebSocket-based UI refresh (with polling fallback)

---

## 🧪 Example Output

```json
{
  "root_cause": "Partner API timeout due to high retry count",
  "impact": "Potential SLA breach and delayed transactions",
  "recommendation": "Check partner API logs and adjust retry policy"
}