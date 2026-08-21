"""
Ground Truth Evaluation Dataset Builder
========================================
Generates ground_truth.csv, the labelled evaluation set for the
three-configuration experiment (RQ1, RQ2, RQ3).

Design notes
------------
- 50 labelled ERP integration cases across 6 failure categories plus a
  small set of NORMAL near-miss cases. The NORMAL cases are deliberately
  included so that false positive rate (RQ3) can be measured: a good
  detector must NOT flag them.
- Each case carries three independent ground-truth labels:
    expected_detection  -> ANOMALY | NORMAL          (drives RQ3 detection metrics)
    expected_root_cause -> failure category           (drives RQ2 diagnosis accuracy)
    expected_routing    -> AUTO_REMEDIATE | INVESTIGATE | ESCALATE | NONE  (drives RQ1)
- Values are hand-authored from domain knowledge of real ERP/EDI failure
  patterns (SPS Commerce EDI, NetSuite governance limits, OAuth token
  expiry, queue saturation) so the set is defensible under examination,
  not random noise.

Routing rationale
-----------------
AUTO_REMEDIATE : known pattern, low business risk, safe to auto-fix
                 (e.g. transient timeout retry, rate-limit back-off,
                 standard EDI revalidation).
INVESTIGATE    : pattern recognised but carries financial/data risk or
                 ambiguity an analyst should confirm (e.g. duplicate
                 financial postings, queue backlog of unclear origin).
ESCALATE       : high severity, novel, or repeated failure where
                 autonomous action is unsafe (e.g. credential revoked,
                 partner endpoint down repeatedly, critical SLA breach).
NONE           : NORMAL cases, within acceptable thresholds, no action.
"""

import csv

# Rule thresholds (mirror configs/rules.yaml): retry_count >= 3 OR
# delay_minutes >= 30 trips a rule. NORMAL cases sit below both.

CASES = [
    # ---------------- EDI_MAPPING_ERROR (8) ----------------
    dict(system="EDI_Gateway", partner="Walmart", failure_category="EDI_MAPPING_ERROR",
         retry_count=4, delay_minutes=45, severity="MEDIUM",
         error_signature="EDI 850 rejected: missing mandatory ISA envelope header",
         expected_detection="ANOMALY", expected_routing="AUTO_REMEDIATE",
         notes="Classic malformed envelope; standard revalidate+reprocess fix"),
    dict(system="SPS_Commerce", partner="Target", failure_category="EDI_MAPPING_ERROR",
         retry_count=3, delay_minutes=38, severity="MEDIUM",
         error_signature="GS segment control number mismatch on 810 invoice",
         expected_detection="ANOMALY", expected_routing="AUTO_REMEDIATE",
         notes="Well-understood control-number fix"),
    dict(system="EDI_Gateway", partner="Kroger", failure_category="EDI_MAPPING_ERROR",
         retry_count=5, delay_minutes=60, severity="MEDIUM",
         error_signature="Invalid qualifier in N1 segment, partner ID not recognised",
         expected_detection="ANOMALY", expected_routing="INVESTIGATE",
         notes="Partner config drift; analyst should confirm mapping table"),
    dict(system="SPS_Commerce", partner="Costco", failure_category="EDI_MAPPING_ERROR",
         retry_count=4, delay_minutes=42, severity="LOW",
         error_signature="Date format DTM segment CCYYMMDD expected, received YYMMDD",
         expected_detection="ANOMALY", expected_routing="AUTO_REMEDIATE",
         notes="Deterministic date reformat"),
    dict(system="EDI_Gateway", partner="HomeDepot", failure_category="EDI_MAPPING_ERROR",
         retry_count=6, delay_minutes=90, severity="HIGH",
         error_signature="Repeated 856 ASN structure failure across 40 transactions",
         expected_detection="ANOMALY", expected_routing="ESCALATE",
         notes="Systemic mapping break affecting many docs; needs engineer"),
    dict(system="SPS_Commerce", partner="Macys", failure_category="EDI_MAPPING_ERROR",
         retry_count=3, delay_minutes=33, severity="LOW",
         error_signature="Trailing whitespace in REF segment failing strict parser",
         expected_detection="ANOMALY", expected_routing="AUTO_REMEDIATE",
         notes="Trivial trim fix"),
    dict(system="EDI_Gateway", partner="Nordstrom", failure_category="EDI_MAPPING_ERROR",
         retry_count=4, delay_minutes=50, severity="MEDIUM",
         error_signature="Unexpected segment terminator in 850 line items",
         expected_detection="ANOMALY", expected_routing="INVESTIGATE",
         notes="Could indicate partner spec change"),
    dict(system="SPS_Commerce", partner="Tesco", failure_category="EDI_MAPPING_ERROR",
         retry_count=5, delay_minutes=55, severity="MEDIUM",
         error_signature="Missing GE segment, functional group not closed",
         expected_detection="ANOMALY", expected_routing="AUTO_REMEDIATE",
         notes="Standard envelope repair"),

    # ---------------- PARTNER_API_TIMEOUT (8) ----------------
    dict(system="NetSuite", partner="Amazon", failure_category="PARTNER_API_TIMEOUT",
         retry_count=3, delay_minutes=35, severity="LOW",
         error_signature="Partner REST endpoint 504 gateway timeout, single occurrence",
         expected_detection="ANOMALY", expected_routing="AUTO_REMEDIATE",
         notes="Transient; retry resolves"),
    dict(system="NetSuite", partner="Shopify", failure_category="PARTNER_API_TIMEOUT",
         retry_count=4, delay_minutes=40, severity="MEDIUM",
         error_signature="Connection timeout after 30s on order sync",
         expected_detection="ANOMALY", expected_routing="AUTO_REMEDIATE",
         notes="Standard back-off retry"),
    dict(system="Oracle_Fusion", partner="FedEx", failure_category="PARTNER_API_TIMEOUT",
         retry_count=7, delay_minutes=120, severity="HIGH",
         error_signature="Carrier API unreachable for 2 hours, all shipment calls failing",
         expected_detection="ANOMALY", expected_routing="ESCALATE",
         notes="Sustained outage; partner-side, needs escalation"),
    dict(system="NetSuite", partner="UPS", failure_category="PARTNER_API_TIMEOUT",
         retry_count=3, delay_minutes=32, severity="LOW",
         error_signature="Intermittent 503 on rate quote endpoint",
         expected_detection="ANOMALY", expected_routing="AUTO_REMEDIATE",
         notes="Transient throttle, retry"),
    dict(system="SAP_ERP", partner="DHL", failure_category="PARTNER_API_TIMEOUT",
         retry_count=6, delay_minutes=100, severity="HIGH",
         error_signature="Repeated SSL handshake timeout to partner gateway",
         expected_detection="ANOMALY", expected_routing="ESCALATE",
         notes="Possible cert issue partner-side; escalate"),
    dict(system="NetSuite", partner="Stripe", failure_category="PARTNER_API_TIMEOUT",
         retry_count=4, delay_minutes=46, severity="MEDIUM",
         error_signature="Payment webhook callback timed out, awaiting confirmation",
         expected_detection="ANOMALY", expected_routing="INVESTIGATE",
         notes="Financial callback; confirm before auto-action"),
    dict(system="Oracle_Fusion", partner="Avalara", failure_category="PARTNER_API_TIMEOUT",
         retry_count=3, delay_minutes=37, severity="MEDIUM",
         error_signature="Tax calculation service slow response, 35s latency",
         expected_detection="ANOMALY", expected_routing="AUTO_REMEDIATE",
         notes="Retry with back-off"),
    dict(system="NetSuite", partner="Amazon", failure_category="PARTNER_API_TIMEOUT",
         retry_count=8, delay_minutes=180, severity="CRITICAL",
         error_signature="Marketplace API down 3h during peak, 200+ orders queued",
         expected_detection="ANOMALY", expected_routing="ESCALATE",
         notes="Critical peak-window outage; immediate escalation"),

    # ---------------- NETSUITE_QUEUE_BACKLOG (7) ----------------
    dict(system="NetSuite", partner="Internal", failure_category="NETSUITE_QUEUE_BACKLOG",
         retry_count=3, delay_minutes=55, severity="MEDIUM",
         error_signature="Async job queue depth 1,200, processing lag rising",
         expected_detection="ANOMALY", expected_routing="INVESTIGATE",
         notes="Capacity question; analyst review"),
    dict(system="NetSuite", partner="Internal", failure_category="NETSUITE_QUEUE_BACKLOG",
         retry_count=4, delay_minutes=75, severity="HIGH",
         error_signature="Map/Reduce script queue stalled, no completions 40min",
         expected_detection="ANOMALY", expected_routing="ESCALATE",
         notes="Stalled processor; needs engineer"),
    dict(system="NetSuite", partner="Internal", failure_category="NETSUITE_QUEUE_BACKLOG",
         retry_count=3, delay_minutes=48, severity="MEDIUM",
         error_signature="Scheduled script deployment backlog after release",
         expected_detection="ANOMALY", expected_routing="INVESTIGATE",
         notes="Post-deploy backlog; confirm cause"),
    dict(system="NetSuite", partner="Internal", failure_category="NETSUITE_QUEUE_BACKLOG",
         retry_count=5, delay_minutes=85, severity="HIGH",
         error_signature="CSV import queue saturated, 8k records pending 1h",
         expected_detection="ANOMALY", expected_routing="ESCALATE",
         notes="Large saturation; escalate"),
    dict(system="NetSuite", partner="Internal", failure_category="NETSUITE_QUEUE_BACKLOG",
         retry_count=3, delay_minutes=41, severity="MEDIUM",
         error_signature="Inventory sync queue lag during nightly batch",
         expected_detection="ANOMALY", expected_routing="INVESTIGATE",
         notes="Batch-window lag; review schedule"),
    dict(system="NetSuite", partner="Internal", failure_category="NETSUITE_QUEUE_BACKLOG",
         retry_count=4, delay_minutes=68, severity="HIGH",
         error_signature="Workflow scheduler thread pool exhausted",
         expected_detection="ANOMALY", expected_routing="ESCALATE",
         notes="Resource exhaustion; engineer"),
    dict(system="NetSuite", partner="Internal", failure_category="NETSUITE_QUEUE_BACKLOG",
         retry_count=3, delay_minutes=52, severity="MEDIUM",
         error_signature="Webhook delivery queue retrying, downstream slow",
         expected_detection="ANOMALY", expected_routing="INVESTIGATE",
         notes="Downstream dependency; review"),

    # ---------------- DUPLICATE_TRANSACTION (7) ----------------
    dict(system="NetSuite", partner="Walmart", failure_category="DUPLICATE_TRANSACTION",
         retry_count=3, delay_minutes=30, severity="HIGH",
         error_signature="Duplicate PO# detected, sales order would double-post",
         expected_detection="ANOMALY", expected_routing="INVESTIGATE",
         notes="Financial risk; never auto-post, confirm first"),
    dict(system="SAP_ERP", partner="Target", failure_category="DUPLICATE_TRANSACTION",
         retry_count=4, delay_minutes=34, severity="HIGH",
         error_signature="Invoice 810 reprocessed, duplicate GL entry risk",
         expected_detection="ANOMALY", expected_routing="ESCALATE",
         notes="GL integrity risk; escalate to finance ops"),
    dict(system="NetSuite", partner="Costco", failure_category="DUPLICATE_TRANSACTION",
         retry_count=3, delay_minutes=31, severity="MEDIUM",
         error_signature="Retry created duplicate item fulfilment record",
         expected_detection="ANOMALY", expected_routing="INVESTIGATE",
         notes="Confirm idempotency before reversing"),
    dict(system="Oracle_Fusion", partner="Kroger", failure_category="DUPLICATE_TRANSACTION",
         retry_count=5, delay_minutes=44, severity="HIGH",
         error_signature="Payment applied twice after webhook replay",
         expected_detection="ANOMALY", expected_routing="ESCALATE",
         notes="Double payment; immediate escalation"),
    dict(system="NetSuite", partner="HomeDepot", failure_category="DUPLICATE_TRANSACTION",
         retry_count=3, delay_minutes=33, severity="MEDIUM",
         error_signature="Duplicate customer record created on import",
         expected_detection="ANOMALY", expected_routing="INVESTIGATE",
         notes="Data hygiene; merge after review"),
    dict(system="SAP_ERP", partner="Tesco", failure_category="DUPLICATE_TRANSACTION",
         retry_count=4, delay_minutes=36, severity="HIGH",
         error_signature="ASN 856 sent twice, partner flagged duplicate shipment",
         expected_detection="ANOMALY", expected_routing="INVESTIGATE",
         notes="Partner-facing; confirm before resend"),
    dict(system="NetSuite", partner="Sainsburys", failure_category="DUPLICATE_TRANSACTION",
         retry_count=3, delay_minutes=30, severity="MEDIUM",
         error_signature="Idempotency key collision on order create",
         expected_detection="ANOMALY", expected_routing="INVESTIGATE",
         notes="Key collision; verify dedup logic"),

    # ---------------- AUTH_FAILURE (7) ----------------
    dict(system="NetSuite", partner="Amazon", failure_category="AUTH_FAILURE",
         retry_count=3, delay_minutes=30, severity="MEDIUM",
         error_signature="OAuth token expired, 401 on token-based auth",
         expected_detection="ANOMALY", expected_routing="AUTO_REMEDIATE",
         notes="Token refresh is automatable"),
    dict(system="SAP_ERP", partner="Stripe", failure_category="AUTH_FAILURE",
         retry_count=4, delay_minutes=35, severity="MEDIUM",
         error_signature="Access token refresh failed, refresh token still valid",
         expected_detection="ANOMALY", expected_routing="AUTO_REMEDIATE",
         notes="Re-mint access token"),
    dict(system="NetSuite", partner="Coupa", failure_category="AUTH_FAILURE",
         retry_count=6, delay_minutes=70, severity="HIGH",
         error_signature="Credentials revoked, 403 forbidden persistent",
         expected_detection="ANOMALY", expected_routing="ESCALATE",
         notes="Revoked creds need human re-provisioning"),
    dict(system="Oracle_Fusion", partner="Avalara", failure_category="AUTH_FAILURE",
         retry_count=3, delay_minutes=32, severity="MEDIUM",
         error_signature="TBA signature mismatch on integration record",
         expected_detection="ANOMALY", expected_routing="INVESTIGATE",
         notes="Signature config; analyst verifies keys"),
    dict(system="NetSuite", partner="Shopify", failure_category="AUTH_FAILURE",
         retry_count=4, delay_minutes=38, severity="MEDIUM",
         error_signature="Expired client secret on connected app",
         expected_detection="ANOMALY", expected_routing="ESCALATE",
         notes="Secret rotation needs admin"),
    dict(system="SAP_ERP", partner="DHL", failure_category="AUTH_FAILURE",
         retry_count=3, delay_minutes=31, severity="LOW",
         error_signature="Clock skew caused JWT nbf validation failure",
         expected_detection="ANOMALY", expected_routing="AUTO_REMEDIATE",
         notes="NTP resync + retry"),
    dict(system="NetSuite", partner="Amazon", failure_category="AUTH_FAILURE",
         retry_count=7, delay_minutes=95, severity="HIGH",
         error_signature="Repeated 401 after rotation, integration locked out",
         expected_detection="ANOMALY", expected_routing="ESCALATE",
         notes="Lockout; needs admin intervention"),

    # ---------------- RATE_LIMIT_EXCEEDED (7) ----------------
    dict(system="NetSuite", partner="Amazon", failure_category="RATE_LIMIT_EXCEEDED",
         retry_count=3, delay_minutes=30, severity="LOW",
         error_signature="SuiteTalk concurrency governance limit hit",
         expected_detection="ANOMALY", expected_routing="AUTO_REMEDIATE",
         notes="Back-off and stagger; automatable"),
    dict(system="NetSuite", partner="Shopify", failure_category="RATE_LIMIT_EXCEEDED",
         retry_count=4, delay_minutes=33, severity="LOW",
         error_signature="REST API 429 too many requests during bulk sync",
         expected_detection="ANOMALY", expected_routing="AUTO_REMEDIATE",
         notes="Exponential back-off"),
    dict(system="Oracle_Fusion", partner="Avalara", failure_category="RATE_LIMIT_EXCEEDED",
         retry_count=3, delay_minutes=31, severity="LOW",
         error_signature="Tax API throttled, monthly quota near limit",
         expected_detection="ANOMALY", expected_routing="INVESTIGATE",
         notes="Quota planning; review usage"),
    dict(system="NetSuite", partner="Stripe", failure_category="RATE_LIMIT_EXCEEDED",
         retry_count=5, delay_minutes=50, severity="MEDIUM",
         error_signature="Webhook burst exceeded partner rate cap",
         expected_detection="ANOMALY", expected_routing="AUTO_REMEDIATE",
         notes="Queue and throttle outbound"),
    dict(system="SAP_ERP", partner="Coupa", failure_category="RATE_LIMIT_EXCEEDED",
         retry_count=4, delay_minutes=40, severity="MEDIUM",
         error_signature="Procurement API daily call ceiling reached",
         expected_detection="ANOMALY", expected_routing="INVESTIGATE",
         notes="Ceiling planning; review batch size"),
    dict(system="NetSuite", partner="Internal", failure_category="RATE_LIMIT_EXCEEDED",
         retry_count=3, delay_minutes=30, severity="LOW",
         error_signature="SuiteScript governance units exhausted mid-execution",
         expected_detection="ANOMALY", expected_routing="AUTO_REMEDIATE",
         notes="Yield/reschedule; standard pattern"),
    dict(system="NetSuite", partner="Amazon", failure_category="RATE_LIMIT_EXCEEDED",
         retry_count=6, delay_minutes=80, severity="HIGH",
         error_signature="Sustained 429 throttling blocking peak order intake",
         expected_detection="ANOMALY", expected_routing="ESCALATE",
         notes="Peak throttle blocking revenue; escalate"),

    # ---------------- NORMAL cases (6): 3 quiet + 3 noisy FP-traps ----------------
    # Quiet normals sit below rule thresholds (retry<3 AND delay<30) -> clear negatives.
    # Noisy normals TRIP a rule threshold but are genuinely benign. Rules-only will
    # false-positive on these; the Isolation Forest (trained on an L-shaped normal
    # region) and the semantic agent layer should rescue them. This is the crux of RQ3.
    dict(system="Oracle_Fusion", partner="Stripe", failure_category="NORMAL",
         retry_count=0, delay_minutes=5, severity="LOW",
         error_signature="Clean transaction, no retries, fast completion",
         expected_detection="NORMAL", expected_routing="NONE",
         notes="Clear normal baseline (quiet)"),
    dict(system="EDI_Gateway", partner="Target", failure_category="NORMAL",
         retry_count=1, delay_minutes=12, severity="LOW",
         error_signature="Single retry, succeeded second attempt, within SLA",
         expected_detection="NORMAL", expected_routing="NONE",
         notes="Healthy transient retry (quiet)"),
    dict(system="NetSuite", partner="Amazon", failure_category="NORMAL",
         retry_count=2, delay_minutes=15, severity="LOW",
         error_signature="Two retries within tolerance, no SLA breach",
         expected_detection="NORMAL", expected_routing="NONE",
         notes="Borderline but sub-threshold (quiet)"),
    dict(system="NetSuite", partner="Internal", failure_category="NORMAL",
         retry_count=1, delay_minutes=40, severity="LOW",
         error_signature="Planned nightly batch window, elevated delay expected and benign",
         expected_detection="NORMAL", expected_routing="NONE",
         notes="NOISY FP-trap: delay trips rule (>=30) but benign maintenance window"),
    dict(system="SAP_ERP", partner="DHL", failure_category="NORMAL",
         retry_count=4, delay_minutes=18, severity="LOW",
         error_signature="Known flaky partner heartbeat, self-heals, no business impact",
         expected_detection="NORMAL", expected_routing="NONE",
         notes="NOISY FP-trap: retry trips rule (>=3) but benign self-healing pattern"),
    dict(system="NetSuite", partner="Costco", failure_category="NORMAL",
         retry_count=2, delay_minutes=50, severity="LOW",
         error_signature="Scheduled data warehouse export, high delay by design",
         expected_detection="NORMAL", expected_routing="NONE",
         notes="NOISY FP-trap: delay trips rule (>=30) but planned export, benign"),
]


def build():
    fieldnames = [
        "case_id", "system", "partner", "failure_category",
        "retry_count", "delay_minutes", "severity", "error_signature",
        "expected_detection", "expected_root_cause", "expected_routing", "notes",
    ]

    rows = []
    for i, c in enumerate(CASES, start=1):
        rows.append({
            "case_id": f"EVAL-{i:03d}",
            "system": c["system"],
            "partner": c["partner"],
            "failure_category": c["failure_category"],
            "retry_count": c["retry_count"],
            "delay_minutes": c["delay_minutes"],
            "severity": c["severity"],
            "error_signature": c["error_signature"],
            "expected_detection": c["expected_detection"],
            # expected_root_cause == the category for anomalies, "NONE" for normal
            "expected_root_cause": c["failure_category"] if c["failure_category"] != "NORMAL" else "NONE",
            "expected_routing": c["expected_routing"],
            "notes": c["notes"],
        })

    with open("ground_truth.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    from collections import Counter
    cats = Counter(r["failure_category"] for r in rows)
    routes = Counter(r["expected_routing"] for r in rows)
    det = Counter(r["expected_detection"] for r in rows)

    print(f"OK: Wrote ground_truth.csv with {len(rows)} cases\n")
    print("By failure category:")
    for k, v in sorted(cats.items()):
        print(f"  {k:<24} {v}")
    print("\nBy expected detection label:")
    for k, v in sorted(det.items()):
        print(f"  {k:<24} {v}")
    print("\nBy expected routing decision:")
    for k, v in sorted(routes.items()):
        print(f"  {k:<24} {v}")


if __name__ == "__main__":
    build()
