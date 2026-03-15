import React, { useEffect, useState } from "react";
import axios from "axios";

function App() {
  const [metrics, setMetrics] = useState({
    total_violations: 0,
    high_retry: 0,
    sla_delay: 0
  });

  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios
      .get("https://shiny-spoon-7v674pxj9vq2r4pq-8000.app.github.dev/metrics")
      .then((res) => {
        setMetrics(res.data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("API error:", err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return <h2 style={{ padding: "40px" }}>Loading metrics...</h2>;
  }

  return (
    <div style={{ padding: "40px", fontFamily: "Arial" }}>
      <h1>ERP AI Monitoring Dashboard</h1>

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