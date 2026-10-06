import pytest

from rag.investigation.kafka_investigation_consumer import consume


class Consumer:
    def __init__(self, *args, **kwargs):
        self.calls = 0; self.commits = 0; self.seeks = []; self.closed = False
    def poll(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return {"partition-0": [type("Message", (), {"value": {"alert_id":"a1"}, "offset": 7})()]}
        raise RuntimeError("stop fake consumer")
    def commit(self): self.commits += 1
    def seek(self, partition, offset): self.seeks.append((partition, offset))
    def close(self): self.closed = True


def test_consumer_commits_only_after_handler_returns():
    holder = {}
    def factory(*args, **kwargs): holder["consumer"] = Consumer(); return holder["consumer"]
    with pytest.raises(RuntimeError, match="stop fake"):
        consume(topic="alerts", consumer_factory=factory, handler=lambda event: {"alert_id":"a1", "investigation_id":"i1", "investigation_status":"completed"})
    assert holder["consumer"].commits == 1 and holder["consumer"].closed


def test_consumer_continues_after_a_controlled_failed_investigation():
    class TwoMessageConsumer(Consumer):
        def poll(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                messages = [
                    type("Message", (), {"value": {"alert_id": "a1"}, "offset": 7})(),
                    type("Message", (), {"value": {"alert_id": "a2"}, "offset": 8})(),
                ]
                return {"partition-0": messages}
            raise RuntimeError("stop fake consumer")

    holder = {}
    results = iter((
        {"alert_id": "a1", "investigation_id": "i1", "investigation_status": "failed"},
        {"alert_id": "a2", "investigation_id": "i2", "investigation_status": "completed"},
    ))
    def factory(*args, **kwargs): holder["consumer"] = TwoMessageConsumer(); return holder["consumer"]
    with pytest.raises(RuntimeError, match="stop fake"):
        consume(topic="alerts", consumer_factory=factory, handler=lambda event: next(results))
    assert holder["consumer"].commits == 2 and holder["consumer"].closed


def test_consumer_stops_after_bounded_investigation_retries(monkeypatch):
    holder = {}
    def factory(*args, **kwargs): holder["consumer"] = Consumer(); return holder["consumer"]
    attempts = []
    monkeypatch.setattr("rag.investigation.kafka_investigation_consumer.time.sleep", lambda _: None)
    def fail(_event):
        attempts.append(1)
        raise ValueError("persist error")
    with pytest.raises(RuntimeError, match="source offset remains uncommitted"):
        consume(topic="alerts", consumer_factory=factory, handler=fail)
    assert len(attempts) == 3
    assert holder["consumer"].commits == 0
    assert holder["consumer"].seeks == [("partition-0", 7)]
    assert holder["consumer"].closed


def test_consumer_retries_transient_investigation_failure_then_commits(monkeypatch):
    holder = {}
    attempts = []
    def factory(*args, **kwargs): holder["consumer"] = Consumer(); return holder["consumer"]
    def handler(_event):
        attempts.append(1)
        if len(attempts) == 1:
            raise TimeoutError("temporary Cassandra timeout")
        return {"alert_id": "a1", "investigation_id": "i1", "investigation_status": "partial"}
    monkeypatch.setattr("rag.investigation.kafka_investigation_consumer.time.sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="stop fake"):
        consume(topic="alerts", consumer_factory=factory, handler=handler)
    assert len(attempts) == 2
    assert holder["consumer"].commits == 1
    assert holder["consumer"].seeks == []
    assert holder["consumer"].closed


def test_malformed_alert_is_dead_lettered_before_offset_commit(monkeypatch):
    holder, dlq = {}, []
    consumer = Consumer()
    consumer.sent = False
    def poll(**kwargs):
        if consumer.sent: raise RuntimeError("stop fake consumer")
        consumer.sent = True
        return {"partition-0": [type("Message", (), {"value": b"{bad json", "offset": 9, "topic": "alerts", "partition": 0})()]}
    consumer.poll = poll
    def factory(*args, **kwargs): holder["consumer"] = consumer; return consumer
    with pytest.raises(RuntimeError, match="stop fake"):
        consume(topic="alerts", consumer_factory=factory, dead_letter_handler=lambda *args: dlq.append(args[1:]))
    assert len(dlq) == 1 and dlq[0][0] == "fraud-investigation-dead-letter" and dlq[0][2] == "malformed_alert"
    assert consumer.commits == 1 and consumer.closed


def test_failed_dead_letter_write_stops_after_bounded_retries(monkeypatch):
    consumer = Consumer()
    consumer.sent = False
    def poll(**kwargs):
        if consumer.sent: raise RuntimeError("stop fake consumer")
        consumer.sent = True
        return {"partition-0": [type("Message", (), {"value": b"{bad json", "offset": 9, "topic": "alerts", "partition": 0})()]}
    consumer.poll = poll
    attempts = []
    monkeypatch.setattr("rag.investigation.kafka_investigation_consumer.time.sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="Dead-letter write failed"):
        consume(topic="alerts", consumer_factory=lambda *args, **kwargs: consumer,
                dead_letter_handler=lambda *args: attempts.append(1) or (_ for _ in ()).throw(OSError("broker unavailable")))
    assert len(attempts) == 3
    assert consumer.commits == 0 and consumer.seeks == [("partition-0", 9)] and consumer.closed
