from backend.app.storage import Store


def test_batch_counts_distinguish_successful_partial_and_failed_investigations(tmp_path):
    store = Store(tmp_path / "control.sqlite3")
    batch_id = "demo-batch"
    store.create_batch(
        batch_id=batch_id,
        requested_count=3,
        delay=0.1,
        source="frontend_simulator",
        idempotency_key=None,
        request_hash="test",
    )
    transaction_ids = ("TX-COMPLETE", "TX-PARTIAL", "TX-FAILED")
    for sequence, transaction_id in enumerate(transaction_ids, start=1):
        store.generated(batch_id, sequence, {
            "transaction_id": transaction_id,
            "event_time": "2026-01-01T00:00:00+00:00",
            "type": "TRANSFER",
            "amount": 100,
        })
        store.record_decision({
            "transaction_id": transaction_id,
            "alert_id": f"alert-{sequence}",
        }, "fraud")

    store.update_investigation(transaction_ids[0], {"investigation_status": "completed"})
    store.update_investigation(transaction_ids[1], {"investigation_status": "partial"})
    store.update_investigation(transaction_ids[2], {"investigation_status": "failed"})

    batch = store.batch(batch_id)

    assert batch["investigations_succeeded"] == 1
    assert batch["investigations_partial"] == 1
    assert batch["investigations_failed"] == 1
    assert batch["investigations_completed"] == 2
