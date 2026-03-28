import { useEffect, useState } from "react";
import axios from "axios";

const API = "https://erp-ai-monitor.onrender.com";

function App() {
  const [metrics, setMetrics] = useState(null);
  const [insights, setInsights] = useState([]);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // -------------------------
  // FETCH DATA
  // -------------------------
  const fetchData = async () => {
    try {
      const [m, i, h] = await Promise.all([
        axios.get(`${API}/metrics`),
        axios.get(`${API}/insights`),
        axios.get(`${API}/system-health`)
      ]);

      setMetrics(m.data);
      setInsights(i.data);
      setHealth(h.data);
      setError(null);
    } catch (err) {
      console.error(err);
      setError("API not responding...");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 8000);
    return () => clearInterval(interval);
  }, []);

  // -------------------------
  // WEBSOCKET (NO RELOAD)
  // -------------------------
  useEffect(() => {
    const ws = new WebSocket("wss://erp-ai-monitor.onrender.com/ws");

    ws.onmessage = () => {
      fetchData(); // ✅ only refresh data, not whole page
    };

    ws.onerror = () => {
      console.log("WebSocket failed, fallback to polling");
    };

    return () => ws.close();
  }, []);

  // -------------------------
  // STATES
  // -------------------------
  if (loading) return <Centered>Loading dashboard...</Centered>;
  if (error) return <Centered>{error}</Centered>;

  return (
    <div style={container}>
      <h1 style={title}>ERP AI Monitoring</h1>
      <p style={subtitle}>
        Real-time anomaly detection with AI-driven root cause analysis
      </p>

      {/* SYSTEM HEALTH */}
      <Section title="System Health">
        <div style={grid}>
          <Card title="Database" value={health?.db} status />
          <Card title="AI Engine" value={health?.ai} status />
          <Card title="Latency" value={`${health?.latency || 0}s`} />
        </div>
      </Section>

      {/* METRICS */}
      <Section title="Metrics">
        <div style={grid}>
          <Card title="Total Violations" value={metrics.total_violations} />
          <Card title="High Retry" value={metrics.high_retry} />
          <Card title="SLA Delay" value={metrics.sla_delay} />
        </div>
      </Section>

      {/* INSIGHTS */}
      <Section title="AI Insights">
        {insights.length === 0 ? (
          <p style={{ color: "#666" }}>No insights yet...</p>
        ) : (
          insights.map((item, i) => {
            let parsed;

            try {
              parsed = JSON.parse(item.root_cause);
            } catch {
              parsed = null;
            }

            return (
              <div key={i} style={insightCard}>
                {/* HEADER */}
                <div style={rowBetween}>
                  <strong>{item.transaction_id}</strong>
                  <StatusBadge status={item.ai_status} />
                </div>

                {/* TAG */}
                <div style={{ marginTop: 8 }}>
                  <span style={tag}>{item.rule_violation}</span>
                </div>

                {/* CONTENT */}
                {parsed ? (
                  <>
                    <Block title="Root Cause" style={blue}>
                      {parsed.root_cause}
                    </Block>

                    <Block title="Impact" style={orange}>
                      {parsed.impact}
                    </Block>

                    <Block title="Recommended Fix" style={green}>
                      {parsed.recommendation}
                    </Block>
                  </>
                ) : (
                  <p>{item.root_cause}</p>
                )}

                {/* TIME */}
                <div style={time}>
                  {new Date(item.created_at).toLocaleString()}
                </div>
              </div>
            );
          })
        )}
      </Section>
    </div>
  );
}

// -------------------------
// COMPONENTS
// -------------------------
function Card({ title, value, status }) {
  const color =
    value === "OK" ? "#16a34a" :
    value === "FAIL" ? "#dc2626" : "#111";

  return (
    <div style={card}>
      <h4 style={{ color: "#666" }}>{title}</h4>
      <h2 style={{ color }}>{value}</h2>
    </div>
  );
}

function StatusBadge({ status }) {
  const color =
    status === "DONE" ? "#16a34a" :
    status === "FAILED" ? "#dc2626" : "#f59e0b";

  return (
    <span style={{
      background: color,
      color: "white",
      padding: "4px 10px",
      borderRadius: "20px",
      fontSize: "12px"
    }}>
      {status}
    </span>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ marginTop: 40 }}>
      <h2>{title}</h2>
      {children}
    </div>
  );
}

function Block({ title, children, style }) {
  return (
    <div style={{ ...block, ...style }}>
      <b>{title}</b>
      <p style={{ marginTop: 5 }}>{children}</p>
    </div>
  );
}

function Centered({ children }) {
  return (
    <div style={{
      display: "flex",
      justifyContent: "center",
      alignItems: "center",
      height: "100vh",
      fontSize: 20
    }}>
      {children}
    </div>
  );
}

// -------------------------
// STYLES
// -------------------------
const container = {
  maxWidth: "1100px",
  margin: "auto",
  padding: "40px",
  fontFamily: "Arial",
  background: "#f8fafc"
};

const title = {
  marginBottom: 5
};

const subtitle = {
  color: "#666",
  marginBottom: 30
};

const grid = {
  display: "flex",
  gap: "20px",
  flexWrap: "wrap"
};

const card = {
  background: "white",
  padding: "20px",
  borderRadius: "12px",
  minWidth: "180px",
  boxShadow: "0 4px 10px rgba(0,0,0,0.08)"
};

const insightCard = {
  background: "white",
  padding: "16px",
  marginTop: "15px",
  borderRadius: "12px",
  boxShadow: "0 4px 10px rgba(0,0,0,0.08)"
};

const rowBetween = {
  display: "flex",
  justifyContent: "space-between"
};

const tag = {
  background: "#ef4444",
  color: "white",
  padding: "4px 10px",
  borderRadius: "6px",
  fontSize: "12px"
};

const block = {
  padding: "10px",
  borderRadius: "8px",
  marginTop: "10px"
};

const blue = { background: "#eef2ff" };
const orange = { background: "#fff7ed" };
const green = { background: "#ecfdf5" };

const time = {
  fontSize: "12px",
  color: "#666",
  marginTop: "10px"
};

export default App;