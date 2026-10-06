import ast
import subprocess
import sys
from pathlib import Path


def test_producer_script_imports_project_modules_when_run_by_path(tmp_path):
    producer_path = Path(__file__).parents[1] / "producer" / "producer.py"
    result = subprocess.run(
        [sys.executable, str(producer_path), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--max-transactions" in result.stdout


def test_producer_counter_does_not_shadow_metrics_callable():
    producer_path = Path(__file__).parents[1] / "producer" / "producer.py"
    tree = ast.parse(producer_path.read_text(encoding="utf-8"))

    # Catch assignments, loop targets, imports, and any other bindings named count.
    bound_count_names = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and node.id == "count"
        and isinstance(node.ctx, (ast.Store, ast.Param))
    ]
    assert not bound_count_names

    metric_imports = [
        alias
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "rag.metrics"
        for alias in node.names
        if alias.name == "count"
    ]
    assert len(metric_imports) == 1
    assert metric_imports[0].asname == "metric_count"

    metric_statuses = {
        node.args[2].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "metric_count"
        and len(node.args) >= 3
        and isinstance(node.args[2], ast.Constant)
    }
    assert metric_statuses == {"success", "failure"}


def test_producer_records_actual_per_transaction_generation_duration():
    from types import SimpleNamespace

    from producer.producer import produce_batch
    from rag.metrics import DURATION

    class Future:
        def get(self, timeout):
            return SimpleNamespace(partition=0, offset=1)

    class Producer:
        def send(self, *args, **kwargs):
            return Future()

        def flush(self):
            pass

        def close(self):
            pass

    duration = DURATION.labels("producer", "transaction_generation")
    before = duration._sum.get()
    result = produce_batch(
        1,
        delay=0,
        transactions=[{
            "step": 1,
            "type": "PAYMENT",
            "amount": 10,
            "nameOrig": "source",
            "oldbalanceOrg": 10,
            "newbalanceOrig": 0,
            "nameDest": "destination",
            "oldbalanceDest": 0,
            "newbalanceDest": 10,
        }],
        producer_factory=lambda **kwargs: Producer(),
        serve_metrics=False,
        output=lambda _: None,
    )

    assert result.generated_count == 1
    assert result.sent_count == 1
    assert duration._sum.get() > before
