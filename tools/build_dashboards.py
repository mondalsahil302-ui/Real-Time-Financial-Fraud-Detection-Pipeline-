"""Generate polished, production-ready Grafana dashboards for the Fraud Pipeline."""
from __future__ import annotations
import json
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "monitoring" / "grafana" / "dashboards"
PROMETHEUS_DS = {"type": "prometheus", "uid": "prometheus"}


def stat_panel(panel_id: int, title: str, expr: str, x: int, y: int, w: int, h: int, unit: str = "short", color: str = "green", thresholds=None) -> dict:
    if thresholds is None:
        thresholds = {"mode": "absolute", "steps": [{"color": color, "value": None}]}
    return {
        "id": panel_id,
        "title": title,
        "type": "stat",
        "datasource": PROMETHEUS_DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "color": {"mode": "thresholds"},
                "thresholds": thresholds,
                "mappings": []
            },
            "overrides": []
        },
        "options": {
            "reduceOptions": {
                "values": False,
                "calcs": ["lastNotNull"],
                "fields": ""
            },
            "orientation": "auto",
            "textMode": "auto",
            "colorMode": "value",
            "graphMode": "area",
            "justifyMode": "auto"
        },
        "targets": [
            {
                "refId": "A",
                "datasource": PROMETHEUS_DS,
                "expr": expr,
                "instant": True,
                "editorMode": "code"
            }
        ]
    }


def timeseries_panel(panel_id: int, title: str, targets: list[dict], x: int, y: int, w: int, h: int, unit: str = "short") -> dict:
    formatted_targets = []
    for i, t in enumerate(targets):
        formatted_targets.append({
            "refId": chr(65 + i),
            "datasource": PROMETHEUS_DS,
            "expr": t["expr"],
            "legendFormat": t.get("legendFormat", ""),
            "range": True,
            "editorMode": "code"
        })
    return {
        "id": panel_id,
        "title": title,
        "type": "timeseries",
        "datasource": PROMETHEUS_DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "color": {"mode": "palette-classic"},
                "custom": {
                    "axisBorderShow": False,
                    "axisCenteredZero": False,
                    "axisColorMode": "text",
                    "axisPlacement": "auto",
                    "fillOpacity": 15,
                    "gradientMode": "none",
                    "lineWidth": 2,
                    "pointSize": 5,
                    "showPoints": "auto",
                    "spanNulls": True
                },
                "thresholds": {
                    "mode": "absolute",
                    "steps": [{"color": "green", "value": None}]
                }
            },
            "overrides": []
        },
        "options": {
            "legend": {
                "calcs": ["lastNotNull", "max"],
                "displayMode": "table",
                "placement": "bottom",
                "showLegend": True
            },
            "tooltip": {
                "mode": "single",
                "sort": "none"
            }
        },
        "targets": formatted_targets
    }


def make_dashboard(uid: str, title: str, tags: list[str], panels: list[dict]) -> dict:
    return {
        "uid": uid,
        "title": title,
        "tags": tags,
        "timezone": "browser",
        "schemaVersion": 39,
        "version": 2,
        "refresh": "10s",
        "time": {"from": "now-1h", "to": "now"},
        "panels": panels
    }


def generate_all():
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Main Pipeline Dashboard
    p1 = [
        stat_panel(1, "Total Processed", "sum(fraud_pipeline_events_total{component=\"spark\",event=\"transactions_processed\"}) or vector(0)", 0, 0, 6, 4, unit="short", color="blue"),
        stat_panel(2, "Fraud Alerts Flagged", "sum(fraud_pipeline_events_total{component=\"spark\",event=\"fraud_alerts_produced\"}) or vector(0)", 6, 0, 6, 4, unit="short", color="red"),
        stat_panel(3, "Investigations Completed", "sum(fraud_pipeline_events_total{component=\"investigation\",event=\"completed\"}) or vector(0)", 12, 0, 6, 4, unit="short", color="orange"),
        stat_panel(4, "Active Scrape Targets", "sum(up)", 18, 0, 6, 4, unit="short", thresholds={"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 6}]}),

        timeseries_panel(5, "Pipeline Event Throughput (/sec)", [
            {"expr": "fraud_pipeline:events_per_second:5m", "legendFormat": "{{component}} - {{event}} ({{status}})"}
        ], 0, 4, 12, 8, unit="reqps"),

        timeseries_panel(6, "Processing Latency p95 (seconds)", [
            {"expr": "histogram_quantile(0.95, sum by (le) (rate(fraud_pipeline_duration_seconds_bucket[5m])))", "legendFormat": "Global p95 Latency"},
            {"expr": "histogram_quantile(0.95, sum by (le) (rate(fraud_pipeline_duration_seconds_bucket{component=\"investigation\"}[5m])))", "legendFormat": "LLM Investigation p95"},
            {"expr": "histogram_quantile(0.95, sum by (le) (rate(fraud_pipeline_duration_seconds_bucket{component=\"spark\"}[5m])))", "legendFormat": "Spark Streaming p95"}
        ], 12, 4, 12, 8, unit="s"),

        timeseries_panel(7, "Service Target Health Status", [
            {"expr": "up", "legendFormat": "{{job}} ({{instance}})"}
        ], 0, 12, 12, 8, unit="short"),

        timeseries_panel(8, "Container CPU Usage", [
            {"expr": "sum by (id) (rate(container_cpu_usage_seconds_total{id!=\"/\"}[5m]))", "legendFormat": "{{id}}"}
        ], 12, 12, 12, 8, unit="percentunit"),

        timeseries_panel(9, "Container Memory Usage", [
            {"expr": "container_memory_usage_bytes{id!=\"/\"}", "legendFormat": "{{id}}"}
        ], 0, 20, 24, 7, unit="bytes")
    ]
    dash1 = make_dashboard("fraud-pipeline", "Fraud Detection Pipeline", ["fraud", "pipeline"], p1)
    (DASHBOARD_DIR / "fraud-pipeline.json").write_text(json.dumps(dash1, indent=2), encoding="utf-8")

    # 2. Fraud Detection (Spark & ML)
    p2 = [
        stat_panel(1, "Spark Processed Transactions", "sum(fraud_pipeline_events_total{component=\"spark\",event=\"transactions_processed\"}) or vector(0)", 0, 0, 6, 4, unit="short", color="blue"),
        stat_panel(2, "Flagged High Risk (L3-L5)", "sum(fraud_pipeline_events_total{component=\"spark\",event=\"fraud_alerts_produced\"}) or vector(0)", 6, 0, 6, 4, unit="short", color="red"),
        stat_panel(3, "Filtered Low Risk (L1-L2)", "sum(fraud_pipeline_events_total{component=\"spark\",event=\"low_risk_produced\"}) or vector(0)", 12, 0, 6, 4, unit="short", color="green"),
        stat_panel(4, "Alert Ratio (%)", "100 * sum(fraud_pipeline_events_total{component=\"spark\",event=\"fraud_alerts_produced\"}) / clamp_min(sum(fraud_pipeline_events_total{component=\"spark\",event=\"transactions_processed\"}), 1) or vector(0)", 18, 0, 6, 4, unit="percent", color="orange"),

        timeseries_panel(5, "Spark Transactions Processed / sec", [
            {"expr": "sum(rate(fraud_pipeline_events_total{component=\"spark\",event=\"transactions_processed\"}[5m]))", "legendFormat": "Processed tx/s"},
            {"expr": "sum(rate(fraud_pipeline_events_total{component=\"spark\",event=\"fraud_alerts_produced\"}[5m]))", "legendFormat": "Fraud alerts/s"},
            {"expr": "sum(rate(fraud_pipeline_events_total{component=\"spark\",event=\"low_risk_produced\"}[5m]))", "legendFormat": "Low risk/s"}
        ], 0, 4, 14, 8, unit="reqps"),

        timeseries_panel(6, "Spark Batch Processing Duration p95", [
            {"expr": "histogram_quantile(0.95, sum by (le) (rate(fraud_pipeline_duration_seconds_bucket{component=\"spark\"}[5m])))", "legendFormat": "Batch p95 (s)"}
        ], 14, 4, 10, 8, unit="s")
    ]
    dash2 = make_dashboard("fraud-detection", "Fraud Detection", ["fraud", "detection", "spark"], p2)
    (DASHBOARD_DIR / "fraud-detection.json").write_text(json.dumps(dash2, indent=2), encoding="utf-8")

    # 3. RAG and LLM Investigation
    p3 = [
        stat_panel(1, "Total Investigations", "sum(fraud_pipeline_events_total{component=\"investigation\",event=\"completed\"}) or vector(0)", 0, 0, 6, 4, unit="short", color="orange"),
        stat_panel(2, "LLM Generations", "sum(fraud_pipeline_events_total{component=\"llm\",event=\"generation\"}) or vector(0)", 6, 0, 6, 4, unit="short", color="blue"),
        stat_panel(3, "RAG Vector Retrievals", "sum(fraud_pipeline_events_total{component=\"rag\",event=\"retrieval\"}) or vector(0)", 12, 0, 6, 4, unit="short", color="purple"),
        stat_panel(4, "LLM Success Ratio", "fraud_pipeline:llm_success_ratio:5m or vector(1)", 18, 0, 6, 4, unit="percentunit", thresholds={"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 0.8}]}),

        timeseries_panel(5, "Investigation Latency p95 (seconds)", [
            {"expr": "histogram_quantile(0.95, sum by (le) (rate(fraud_pipeline_duration_seconds_bucket{component=\"investigation\"}[5m])))", "legendFormat": "p95 Latency"}
        ], 0, 4, 12, 8, unit="s"),

        timeseries_panel(6, "LLM Generations & RAG Retrievals / sec", [
            {"expr": "sum by (status) (rate(fraud_pipeline_events_total{component=\"llm\",event=\"generation\"}[5m]))", "legendFormat": "LLM: {{status}}"},
            {"expr": "sum by (status) (rate(fraud_pipeline_events_total{component=\"rag\",event=\"retrieval\"}[5m]))", "legendFormat": "RAG: {{status}}"}
        ], 12, 4, 12, 8, unit="reqps"),

        timeseries_panel(7, "Investigation Outcomes / sec", [
            {"expr": "sum by (status) (rate(fraud_pipeline_events_total{component=\"investigation\",event=\"completed\"}[5m]))", "legendFormat": "{{status}}"}
        ], 0, 12, 24, 7, unit="reqps")
    ]
    dash3 = make_dashboard("fraud-rag-llm", "RAG and LLM Investigation", ["fraud", "rag", "llm"], p3)
    (DASHBOARD_DIR / "rag-llm.json").write_text(json.dumps(dash3, indent=2), encoding="utf-8")

    # 4. Kafka
    p4 = [
        stat_panel(1, "Total Produced Transactions", "sum(fraud_pipeline_events_total{component=\"kafka\",event=\"transaction_produced\",status=\"success\"}) or vector(0)", 0, 0, 8, 4, unit="short", color="blue"),
        stat_panel(2, "Dead Letter Messages", "sum(fraud_pipeline_events_total{component=\"kafka\",event=\"dead_letter\"}) or vector(0)", 8, 0, 8, 4, unit="short", color="red"),
        stat_panel(3, "Producer Status", "up{job=\"transaction-producer\"}", 16, 0, 8, 4, unit="short", color="green"),

        timeseries_panel(4, "Kafka Events / sec", [
            {"expr": "sum by (event,status) (rate(fraud_pipeline_events_total{component=\"kafka\"}[5m]))", "legendFormat": "{{event}} ({{status}})"}
        ], 0, 4, 12, 8, unit="reqps"),

        timeseries_panel(5, "Kafka Failures / sec", [
            {"expr": "sum by (event) (rate(fraud_pipeline_events_total{component=\"kafka\",status=\"failure\"}[5m]))", "legendFormat": "{{event}} failure"}
        ], 12, 4, 12, 8, unit="reqps")
    ]
    dash4 = make_dashboard("fraud-kafka", "Kafka", ["fraud", "kafka"], p4)
    (DASHBOARD_DIR / "kafka.json").write_text(json.dumps(dash4, indent=2), encoding="utf-8")

    # 5. Cassandra
    p5 = [
        stat_panel(1, "Total Cassandra Writes", "sum(fraud_pipeline_events_total{component=\"cassandra\",event=\"write\",status=\"success\"}) or vector(0)", 0, 0, 8, 4, unit="short", color="green"),
        stat_panel(2, "Total Cassandra Failures", "sum(fraud_pipeline_events_total{component=\"cassandra\",status=\"failure\"}) or vector(0)", 8, 0, 8, 4, unit="short", color="red"),
        stat_panel(3, "Cassandra Scrape Target", "up{job=\"control-center-api\"}", 16, 0, 8, 4, unit="short", color="blue"),

        timeseries_panel(4, "Cassandra Operations / sec", [
            {"expr": "sum by (event,status) (rate(fraud_pipeline_events_total{component=\"cassandra\"}[5m]))", "legendFormat": "{{event}} ({{status}})"}
        ], 0, 4, 12, 8, unit="reqps"),

        timeseries_panel(5, "Cassandra Failures / sec", [
            {"expr": "sum by (event) (rate(fraud_pipeline_events_total{component=\"cassandra\",status=\"failure\"}[5m]))", "legendFormat": "{{event}} failures"}
        ], 12, 4, 12, 8, unit="reqps")
    ]
    dash5 = make_dashboard("fraud-cassandra", "Cassandra", ["fraud", "cassandra"], p5)
    (DASHBOARD_DIR / "cassandra.json").write_text(json.dumps(dash5, indent=2), encoding="utf-8")

    # 6. Infrastructure Health
    p6 = [
        stat_panel(1, "Active Targets Count", "sum(up)", 0, 0, 6, 4, unit="short", color="green"),
        stat_panel(2, "Prometheus Target Health", "min(up)", 6, 0, 6, 4, unit="short", thresholds={"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}),
        stat_panel(3, "Alertmanager Healthy", "up{job=\"prometheus\"}", 12, 0, 6, 4, unit="short", color="blue"),
        stat_panel(4, "cAdvisor Telemetry Active", "up{job=\"cadvisor\"}", 18, 0, 6, 4, unit="short", color="purple"),

        timeseries_panel(5, "Scrape Target Availability Matrix", [
            {"expr": "up", "legendFormat": "{{job}} - {{instance}}"}
        ], 0, 4, 24, 7, unit="short"),

        timeseries_panel(6, "Container CPU Usage (cAdvisor)", [
            {"expr": "sum by (id) (rate(container_cpu_usage_seconds_total{id!=\"/\"}[5m]))", "legendFormat": "{{id}}"}
        ], 0, 11, 12, 8, unit="percentunit"),

        timeseries_panel(7, "Container Memory Usage (cAdvisor)", [
            {"expr": "container_memory_usage_bytes{id!=\"/\"}", "legendFormat": "{{id}}"}
        ], 12, 11, 12, 8, unit="bytes")
    ]
    dash6 = make_dashboard("fraud-infrastructure-health", "Infrastructure and Application Health", ["fraud", "infrastructure", "health"], p6)
    (DASHBOARD_DIR / "infrastructure-health.json").write_text(json.dumps(dash6, indent=2), encoding="utf-8")

    print(f"Generated 6 Grafana dashboards in {DASHBOARD_DIR}")


if __name__ == "__main__":
    generate_all()
