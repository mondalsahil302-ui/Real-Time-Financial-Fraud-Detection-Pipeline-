import urllib.request

import rag.metrics as metrics
from rag.metrics import count, start_metrics_server


def test_metrics_and_health_endpoints_are_exposed(monkeypatch):
    monkeypatch.setattr(metrics, "_readiness_checks", lambda: {
        "kafka": True, "cassandra": True, "chroma": True,
    })
    server = start_metrics_server(host="127.0.0.1", port=0)
    count("test", "event", "success")
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(base + "/health", timeout=3) as response:
            assert response.status == 200 and b'"status": "ok"' in response.read()
        with urllib.request.urlopen(base + "/readiness", timeout=3) as response:
            assert response.status == 200
            assert b'"dependencies"' in response.read()
        monkeypatch.setattr(metrics, "_readiness_checks", lambda: {
            "kafka": False, "cassandra": True, "chroma": True,
        })
        try:
            urllib.request.urlopen(base + "/readiness", timeout=3)
        except urllib.error.HTTPError as response:
            assert response.code == 503
            assert b'"kafka": false' in response.read()
        else:
            raise AssertionError("Readiness should fail while a required dependency is unavailable")
        with urllib.request.urlopen(base + "/metrics", timeout=3) as response:
            body = response.read().decode()
            assert "fraud_pipeline_events_total" in body
            assert 'component="test"' in body
    finally:
        server.shutdown()
