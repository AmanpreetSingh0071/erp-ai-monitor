import { useEffect, useState } from "react";
import axios from "axios";

const API = "https://erp-ai-monitor.onrender.com";

function App() {
  const [metrics, setMetrics] = useState(null);
  const [insights, setInsights] = useState([]);
  const [health, setHealth] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const m = await axios.get(`${API}/metrics`);
        const i = await axios.get(`${API}/insights`);
        const h = await axios.get(`${API}/system-health`);

        setMetrics(m.data);
        setInsights(i.data);
        setHealth(h.data);
      } catch (err) {
        console.error("API ERROR:", err);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  // ✅ WebSocket
  useEffect(() => {
    const ws = new WebSocket("wss://erp-ai-monitor.onrender.com/ws");

    ws.onmessage = () => {
      window.location.reload();
    };

    return () => ws.close();
  }, []);

  if (!metrics) return <h2>Loading...</h2>;

  return (
    <div style={{ padding: 30 }}>

      <h1>ERP AI Monitoring</h1>

      {/* SYSTEM HEALTH */}
      <h2>System Health</h2>
      <div style={row}>
        <Card title="DB" value={health?.db} />
        <Card title="AI" value={health?.ai} />
        <Card title="Latency" value={health?.latency + "s"} />
      </div>

      {/* METRICS */}
      <h2>Metrics</h2>
      <div style={row}>
        <Card title="Total" value={metrics.total_violations} />
        <Card title="Retry" value={metrics.high_retry} />
        <Card title="Delay" value={metrics.sla_delay} />
      </div>

      {/* INSIGHTS */}
      <h2>AI Insights</h2>

      {insights.map((item, i) => {
        let parsed;

        try {
          parsed = JSON.parse(item.root_cause);
        } catch {
          parsed = null;
        }

        return (
          <div key={i} style={card}>
            <b>{item.transaction_id}</b>

            {parsed ? (
              <>
                <p><b>Cause:</b> {parsed.root_cause}</p>
                <p><b>Impact:</b> {parsed.impact}</p>
                <p><b>Fix:</b> {parsed.recommendation}</p>
              </>
            ) : (
              <p>{item.root_cause}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Card({ title, value }) {
  return (
    <div style={card}>
      <h4>{title}</h4>
      <h2>{value}</h2>
    </div>
  );
}

const row = {
  display: "flex",
  gap: 20
};

const card = {
  background: "#f4f4f4",
  padding: 20,
  borderRadius: 10,
  marginTop: 10
};

export default App;