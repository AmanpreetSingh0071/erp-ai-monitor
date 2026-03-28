import { useEffect, useState } from "react";
import axios from "axios";

const API = "https://erp-ai-monitor.onrender.com";

function App() {
  const [metrics, setMetrics] = useState(null);
  const [insights, setInsights] = useState([]);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

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

      const sorted = i.data
        .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
        .slice(0, 10);

      setInsights(sorted);
      setHealth(h.data);
      setLastUpdated(new Date());
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
  // WEBSOCKET
  // -------------------------
  useEffect(() => {
    const ws = new WebSocket("wss://erp-ai-monitor.onrender.com/ws");

    ws.onmessage = () => {
      fetchData();
    };

    ws.onerror = () => {
      console.log("WebSocket fallback to polling");
    };

    return () => ws.close();
  }, []);

  // -------------------------
  // 🔥 SIMULATE TRAFFIC
  // -------------------------
  const simulateTraffic = async () => {
    try {
      await axios.post(`${API}/simulate`);
      alert("🚀 Traffic simulated");
      fetchData();
    } catch (err) {
      console.error(err);
      alert("Simulation failed");
    }
  };

  // -------------------------
  // STATES
  // -------------------------
  if (loading) return <Centered>Loading dashboard...</Centered>;
  if (error) return <Centered>{error}</Centered>;

  return (
    <div style={container}>
      <h1>ERP AI Monitoring</h1>

      {/* 🔥 BUTTON */}
      <button onClick={simulateTraffic} style={simulateBtn}>
        ⚡ Simulate Traffic
      </button>

      <div style={live}>
        ● Live Monitoring Active
      </div>

      <div style={subtitle}>
        Real-time anomaly detection with AI-driven root cause analysis
      </div>

      <div style={lastUpdate}>
        Last updated: {lastUpdated?.toLocaleTimeString()}
      </div>

      {/* SYSTEM HEALTH */}
      <Section title="System Health">
        <div style={grid}>
          <Card title="Database" value={health?.db} />
          <Card title="AI Engine" value={health?.ai} />
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
              <div key={i} style={insightCard(item.rule_violation)}>
                <div style={rowBetween}>
                  <strong>{item.transaction_id}</strong>
                  <StatusBadge status={item.ai_status} />
                </div>

                <div style={{ marginTop: 8 }}>
                  <span style={tag}>{item.rule_violation}</span>
                </div>

                {item.ai_status === "PENDING" && (
                  <div style={pending}>
                    AI is analyzing this event...
                  </div>
                )}

                {parsed && item.ai_status === "DONE" ? (
                  <>
                    <Block title="🔍 Root Cause" style={blue}>
                      {parsed.root_cause}
                    </Block>

                    <Block title="⚠️ Impact" style={orange}>
                      {parsed.impact}
                    </Block>

                    <Block title="🛠 Recommended Fix" style={green}>
                      {parsed.recommendation}
                    </Block>
                  </>
                ) : !parsed && item.ai_status === "DONE" ? (
                  <p>{item.root_cause}</p>
                ) : null}

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
function Card({ title, value }) {
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
    <div style={centered}>
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

const simulateBtn = {
  marginTop: "15px",
  padding: "10px 20px",
  background: "#2563eb",
  color: "white",
  border: "none",
  borderRadius: "8px",
  cursor: "pointer",
  fontWeight: "bold"
};

const live = {
  color: "#16a34a",
  fontWeight: "bold",
  marginBottom: 5
};

const subtitle = {
  color: "#666",
  marginBottom: 5
};

const lastUpdate = {
  fontSize: "12px",
  color: "#888",
  marginBottom: 20
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

const insightCard = (violation) => ({
  background: "white",
  padding: "16px",
  marginTop: "15px",
  borderRadius: "12px",
  boxShadow: "0 4px 10px rgba(0,0,0,0.08)",
  borderLeft: `6px solid ${
    violation === "SLA_DELAY" ? "#ef4444" :
    violation === "HIGH_RETRY" ? "#f59e0b" :
    "#3b82f6"
  }`
});

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

const pending = {
  marginTop: 10,
  fontStyle: "italic",
  color: "#999"
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

const centered = {
  display: "flex",
  justifyContent: "center",
  alignItems: "center",
  height: "100vh",
  fontSize: "20px"
};

export default App;