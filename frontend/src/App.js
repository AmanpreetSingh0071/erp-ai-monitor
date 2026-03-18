import { useEffect, useState } from "react";
import axios from "axios";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer
} from "recharts";

const API = "https://erp-ai-monitor.onrender.com";

function App() {
  const [metrics, setMetrics] = useState(null);
  const [insights, setInsights] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  // -------------------------
  // Fetch data (polling)
  // -------------------------
  useEffect(() => {
    const fetchData = async () => {
      try {
        const m = await axios.get(`${API}/metrics`);
        const i = await axios.get(`${API}/insights`);

        setMetrics(m.data);
        setInsights(i.data);

        setHistory(prev => [
          ...prev.slice(-10),
          {
            time: new Date().toLocaleTimeString(),
            total: m.data.total_violations
          }
        ]);

        setLoading(false);
      } catch (err) {
        console.error("API ERROR:", err);
        setLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  // -------------------------
  // Simulate transaction
  // -------------------------
  const triggerEvent = async () => {
    const txId = "TX" + Math.floor(Math.random() * 10000);

    try {
      await axios.post(`${API}/ingest`, {
        transaction_id: txId,
        system: "SAP",
        partner: "Vendor-X",
        retry_count: Math.floor(Math.random() * 15),
        delay_minutes: Math.floor(Math.random() * 100)
      });

      alert(`Triggered ${txId}`);
    } catch (err) {
      console.error("Trigger failed:", err);
    }
  };

  // -------------------------
  // SAFE ROOT CAUSE PARSER
  // -------------------------
  const parseRootCause = (rc) => {
    if (!rc) return "Processing...";

    try {
      const parsed = JSON.parse(rc);
      return parsed.root_cause || rc;
    } catch {
      return rc;
    }
  };

  // -------------------------
  // LOADING STATE
  // -------------------------
  if (loading) {
    return <h2 style={{ padding: "40px" }}>Loading dashboard...</h2>;
  }

  if (!metrics) {
    return <h2 style={{ padding: "40px" }}>API not responding...</h2>;
  }

  // -------------------------
  // UI
  // -------------------------
  return (
    <div style={container}>
      <h1>ERP AI Monitoring</h1>
      <p style={{ color: "#666" }}>
        Real-time anomaly detection & AI root cause analysis
      </p>

      {/* BUTTON */}
      <button onClick={triggerEvent} style={button}>
        + Simulate Transaction
      </button>

      {/* METRICS */}
      <div style={cardRow}>
        <Card title="Total Violations" value={metrics.total_violations} />
        <Card title="High Retry" value={metrics.high_retry} />
        <Card title="SLA Delay" value={metrics.sla_delay} />
      </div>

      {/* CHART (FIXED HEIGHT WRAPPER) */}
      <div style={chartContainer}>
        <h3>Violation Trend</h3>

        <div style={{ width: "100%", height: 300 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="total" stroke="#3b82f6" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* AI INSIGHTS */}
      <h2 style={{ marginTop: 40 }}>AI Root Cause Insights</h2>

      {insights.length === 0 ? (
        <p>No insights yet...</p>
      ) : (
        insights.map((item, i) => (
          <div key={i} style={insightCard}>
            <div style={row}>
              <span><b>{item.transaction_id}</b></span>
              <StatusBadge status={item.ai_status} />
            </div>

            <div style={{ marginTop: 8 }}>
              <span style={tag}>{item.rule_violation}</span>
            </div>

            <p style={rootCause}>
              {parseRootCause(item.root_cause)}
            </p>

            <p style={time}>
              {item.created_at
                ? new Date(item.created_at).toLocaleString()
                : ""}
            </p>
          </div>
        ))
      )}

      {/* GRAFANA (OPTIONAL) */}
      <h2 style={{ marginTop: 50 }}>System Monitoring</h2>

      <iframe
        title="grafana"
        src="https://your-grafana-url/d/your-dashboard"
        width="100%"
        height="500px"
        style={{ borderRadius: 10, border: "1px solid #ddd" }}
      />
    </div>
  );
}

// -------------------------
// Components
// -------------------------
function Card({ title, value }) {
  return (
    <div style={card}>
      <h4>{title}</h4>
      <h2>{value}</h2>
    </div>
  );
}

function StatusBadge({ status }) {
  const color =
    status === "DONE" ? "green" :
    status === "FAILED" ? "red" : "orange";

  return (
    <span style={{
      background: color,
      color: "white",
      padding: "3px 10px",
      borderRadius: "20px",
      fontSize: "12px"
    }}>
      {status}
    </span>
  );
}

// -------------------------
// Styles
// -------------------------
const container = {
  padding: "30px",
  fontFamily: "Arial",
  background: "#f8fafc"
};

const cardRow = {
  display: "flex",
  gap: "20px",
  marginTop: "20px"
};

const card = {
  background: "white",
  padding: "20px",
  borderRadius: "12px",
  width: "200px",
  boxShadow: "0 2px 8px rgba(0,0,0,0.1)"
};

const button = {
  marginTop: "20px",
  padding: "10px 20px",
  background: "#2563eb",
  color: "white",
  border: "none",
  borderRadius: "8px",
  cursor: "pointer"
};

const chartContainer = {
  marginTop: "40px",
  background: "white",
  padding: "20px",
  borderRadius: "12px",
  boxShadow: "0 2px 8px rgba(0,0,0,0.1)"
};

const insightCard = {
  background: "white",
  padding: "15px",
  marginTop: "15px",
  borderRadius: "10px",
  boxShadow: "0 2px 6px rgba(0,0,0,0.1)"
};

const row = {
  display: "flex",
  justifyContent: "space-between"
};

const tag = {
  background: "#ef4444",
  color: "white",
  padding: "4px 10px",
  borderRadius: "6px"
};

const rootCause = {
  marginTop: "10px",
  background: "#eef2ff",
  padding: "10px",
  borderRadius: "6px"
};

const time = {
  fontSize: "12px",
  color: "#666",
  marginTop: "5px"
};

export default App;