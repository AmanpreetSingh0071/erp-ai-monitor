import { useEffect, useState } from "react";
import axios from "axios";

function App() {
  const [metrics, setMetrics] = useState({
    total_violations: 0,
    high_retry: 0,
    sla_delay: 0
  });

  const [insights, setInsights] = useState([]);   // ✅ NEW

  const [loading, setLoading] = useState(true);

  // -------------------------
  // Fetch Metrics
  // -------------------------
  useEffect(() => {
    axios
      .get("https://erp-ai-monitor.onrender.com/metrics")
      .then((res) => {
        setMetrics(res.data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("API error:", err);
        setLoading(false);
      });
  }, []);

  // -------------------------
  // Fetch AI Insights
  // -------------------------
  useEffect(() => {
    axios
      .get("https://erp-ai-monitor.onrender.com/insights")
      .then((res) => {
        setInsights(res.data);
      })
      .catch((err) => {
        console.error("Insights error:", err);
      });
  }, []);

  if (loading) {
    return <h2 style={{ padding: "40px" }}>Loading metrics...</h2>;
  }

  return (
    <div style={{ padding: "40px", fontFamily: "Arial" }}>
      <h1>ERP AI Monitoring Dashboard</h1>

      {/* -------------------------
          Metrics Cards
      ------------------------- */}
      <div style={{ display: "flex", gap: "20px", marginTop: "30px" }}>
        <div style={cardStyle}>
          <h3>Total Violations</h3>
          <h2>{metrics.total_violations}</h2>
        </div>

        <div style={cardStyle}>
          <h3>High Retry</h3>
          <h2>{metrics.high_retry}</h2>
        </div>

        <div style={cardStyle}>
          <h3>SLA Delay</h3>
          <h2>{metrics.sla_delay}</h2>
        </div>
      </div>

      {/* -------------------------
          AI Insights Section
      ------------------------- */}
      <h2 style={{ marginTop: "50px" }}>AI Root Cause Insights</h2>

      {insights.length === 0 ? (
        <p>No AI insights yet...</p>
      ) : (
        insights.map((item, i) => (
          <div
            key={i}
            style={{
              border: "1px solid #ddd",
              padding: "15px",
              marginTop: "15px",
              borderRadius: "10px",
              background: "#f4f6ff"
            }}
          >
            <p><strong>Transaction:</strong> {item.transaction_id}</p>

            <p>
              <strong>Violation:</strong>{" "}
              <span style={{
                color: "white",
                background: "red",
                padding: "3px 8px",
                borderRadius: "5px"
              }}>
                {item.rule_violation}
              </span>
            </p>

            <p style={{
              background: "#eef",
              padding: "10px",
              borderRadius: "6px"
            }}>
              {item.root_cause}
            </p>
          </div>
        ))
      )}
    </div>
  );
}

const cardStyle = {
  background: "#f4f4f4",
  padding: "20px",
  borderRadius: "10px",
  width: "200px",
  textAlign: "center",
  boxShadow: "0 2px 6px rgba(0,0,0,0.2)"
};

export default App;