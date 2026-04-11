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

  // 🌙 THEME STATE
  const [darkMode, setDarkMode] = useState(
    localStorage.getItem("theme") === "dark"
  );

  useEffect(() => {
    localStorage.setItem("theme", darkMode ? "dark" : "light");
  }, [darkMode]);

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
  // AUTO WAKE
  // -------------------------
  useEffect(() => {
    const wakeUp = async () => {
      try {
        await fetch(`${API}/health`);
      } catch {}
    };

    wakeUp();
    const interval = setInterval(wakeUp, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  // -------------------------
  // WEBSOCKET
  // -------------------------
  useEffect(() => {
    const ws = new WebSocket("wss://erp-ai-monitor.onrender.com/ws");

    ws.onmessage = () => fetchData();
    ws.onerror = () => console.log("WS fallback");

    return () => ws.close();
  }, []);

  // -------------------------
  // ACTIONS
  // -------------------------
  const startBackend = async () => {
    await axios.get(`${API}/health`);
    alert("Backend triggered!");
  };

  const simulateTraffic = async () => {
    await axios.post(`${API}/simulate`);
    alert("🚀 Traffic simulated");
    fetchData();
  };

  // -------------------------
  // STATES
  // -------------------------
  if (loading) return <Centered>Loading dashboard...</Centered>;

  const theme = darkMode ? dark : light;

  return (
    <div style={{ ...container, ...theme.container }}>

      {/* 🌙 TOGGLE BUTTON */}
      <div style={toggleContainer}>
        <button
          onClick={() => setDarkMode(!darkMode)}
          style={toggleBtn}
        >
          {darkMode ? "🌙" : "☀️"}
        </button>
      </div>

      <h1 style={{ color: theme.text }}>ERP AI Monitoring</h1>

      {error && (
        <div style={errorBox}>
          ⚠️ {error}
        </div>
      )}

      <div style={{ marginTop: 15 }}>
        <button onClick={startBackend} style={button}>
          🚀 Start Backend
        </button>

        <button
          onClick={simulateTraffic}
          style={{ ...simulateBtn, marginLeft: 10 }}
        >
          ⚡ Simulate Traffic
        </button>
      </div>

      <div style={{ ...live, color: theme.green }}>
        ● Live Monitoring Active
      </div>

      <div style={{ ...subtitle, color: theme.subtext }}>
        Real-time anomaly detection with AI-driven root cause analysis
      </div>

      <div style={lastUpdate}>
        Last updated: {lastUpdated?.toLocaleTimeString()}
      </div>

      {/* SYSTEM HEALTH */}
      <Section title="System Health" theme={theme}>
        <div style={grid}>
          <Card title="Database" value={health?.db} theme={theme} />
          <Card title="AI Engine" value={health?.ai} theme={theme} />
          <Card title="Latency" value={`${health?.latency || 0}s`} theme={theme} />
        </div>
      </Section>

      {/* METRICS */}
      <Section title="Metrics" theme={theme}>
        <div style={grid}>
          <Card title="Total Violations" value={metrics?.total_violations || 0} theme={theme} />
          <Card title="High Retry" value={metrics?.high_retry || 0} theme={theme} />
          <Card title="SLA Delay" value={metrics?.sla_delay || 0} theme={theme} />
        </div>
      </Section>

      {/* INSIGHTS */}
      <Section title="AI Insights" theme={theme}>
        {insights.map((item, i) => {
          let parsed;
          try { parsed = JSON.parse(item.root_cause); } catch {}

          return (
            <div key={i} style={{ ...insightCard(item.rule_violation), background: theme.card }}>
              <div style={rowBetween}>
                <strong style={{ color: theme.text }}>{item.transaction_id}</strong>
                <StatusBadge status={item.ai_status} />
              </div>

              <span style={tag}>{item.rule_violation}</span>

              {parsed && (
                <>
                  <Block title="Root Cause" theme={theme}>{parsed.root_cause}</Block>
                  <Block title="Impact" theme={theme}>{parsed.impact}</Block>
                  <Block title="Fix" theme={theme}>{parsed.recommendation}</Block>
                </>
              )}

              <div style={time}>
                {new Date(item.created_at).toLocaleString()}
              </div>
            </div>
          );
        })}
      </Section>
    </div>
  );
}

// -------------------------
// COMPONENTS
// -------------------------
function Card({ title, value, theme }) {
  return (
    <div style={{ ...card, background: theme.card }}>
      <h4 style={{ color: theme.subtext }}>{title}</h4>
      <h2 style={{ color: theme.text }}>{value}</h2>
    </div>
  );
}

function Section({ title, children, theme }) {
  return (
    <div style={{ marginTop: 40 }}>
      <h2 style={{ color: theme.text }}>{title}</h2>
      {children}
    </div>
  );
}

function Block({ title, children, theme }) {
  return (
    <div style={{ ...block, background: theme.block }}>
      <b>{title}</b>
      <p>{children}</p>
    </div>
  );
}

function StatusBadge({ status }) {
  const color =
    status === "DONE" ? "#16a34a" :
    status === "FAILED" ? "#dc2626" : "#f59e0b";

  return <span style={{ background: color, color: "white", padding: "4px 10px", borderRadius: "20px" }}>{status}</span>;
}

function Centered({ children }) {
  return <div style={centered}>{children}</div>;
}

// -------------------------
// THEMES
// -------------------------
const light = {
  container: { background: "#f8fafc" },
  text: "#111",
  subtext: "#666",
  card: "#fff",
  block: "#eef2ff",
  green: "#16a34a"
};

const dark = {
  container: { background: "#0f172a" },
  text: "#f1f5f9",
  subtext: "#94a3b8",
  card: "#1e293b",
  block: "#1e3a8a",
  green: "#22c55e"
};

// -------------------------
const toggleContainer = {
  position: "absolute",
  top: 20,
  right: 20
};

const toggleBtn = {
  padding: "8px 12px",
  borderRadius: "20px",
  border: "none",
  cursor: "pointer"
};

const container = {
  maxWidth: "1100px",
  margin: "auto",
  padding: "40px",
  fontFamily: "Arial"
};

const button = {
  padding: "10px 20px",
  background: "#16a34a",
  color: "white",
  border: "none",
  borderRadius: "8px"
};

const simulateBtn = {
  padding: "10px 20px",
  background: "#2563eb",
  color: "white",
  border: "none",
  borderRadius: "8px"
};

const grid = { display: "flex", gap: "20px", flexWrap: "wrap" };

const card = {
  padding: "20px",
  borderRadius: "12px",
  minWidth: "180px"
};

const insightCard = () => ({
  padding: "16px",
  marginTop: "15px",
  borderRadius: "12px"
});

const rowBetween = { display: "flex", justifyContent: "space-between" };

const tag = {
  background: "#ef4444",
  color: "white",
  padding: "4px 10px",
  borderRadius: "6px"
};

const block = {
  padding: "10px",
  borderRadius: "8px",
  marginTop: "10px"
};

const time = { fontSize: "12px", marginTop: "10px" };

const centered = {
  display: "flex",
  justifyContent: "center",
  alignItems: "center",
  height: "100vh"
};

const live = { fontWeight: "bold" };
const subtitle = {};
const lastUpdate = { fontSize: "12px", marginBottom: 20 };

const errorBox = {
  background: "#fee2e2",
  padding: "10px",
  borderRadius: "8px",
  marginTop: "10px"
};

export default App;