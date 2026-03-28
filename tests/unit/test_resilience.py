"""Unit tests for Circuit Breaker and OutboxWorker."""
import time
import pytest
from unittest.mock import MagicMock, patch

from app.resilience.circuit_breaker import CircuitBreaker, CircuitState, CircuitOpenError
from app.resilience.outbox_worker import OutboxWorker, OutboxEntry


class TestCircuitBreaker:
    def test_initial_state_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.fail_count == 0

    def test_successful_calls_stay_closed(self):
        cb = CircuitBreaker(failure_threshold=3)
        result = cb.call(lambda: "ok")
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

        def failing_func():
            raise RuntimeError("fail!")

        for _ in range(3):
            with pytest.raises(RuntimeError):
                cb.call(failing_func)

        assert cb.state == CircuitState.OPEN
        assert cb.fail_count == 3

    def test_open_circuit_raises_circuit_open_error(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60)

        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        assert cb.state == CircuitState.OPEN

        with pytest.raises(CircuitOpenError):
            cb.call(lambda: "should not reach")

    def test_half_open_recovers_on_success(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0)

        with pytest.raises(RuntimeError):
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        assert cb.state == CircuitState.OPEN

        # With recovery_timeout=0, it should immediately try HALF_OPEN
        time.sleep(0.1)
        result = cb.call(lambda: "recovered")
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED

    def test_success_resets_fail_count(self):
        cb = CircuitBreaker(failure_threshold=5)

        def fail():
            raise RuntimeError("fail")

        # Fail twice
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call(fail)
        assert cb.fail_count == 2

        # Succeed once
        cb.call(lambda: "ok")
        assert cb.fail_count == 0


class TestOutboxWorker:
    def test_enqueue_and_process(self):
        mock_sm = MagicMock()
        mock_sm.add.return_value = {"id": "mem_1"}
        cb = CircuitBreaker(failure_threshold=5)

        worker = OutboxWorker(mock_sm, cb)
        worker.start()

        entry = OutboxEntry(
            action="add",
            graph_id="test_graph",
            text="test content",
            metadata={"episode_id": "ep_1"},
        )
        worker.enqueue(entry)

        # Give the worker thread time to process
        time.sleep(1.0)
        worker.stop()

        mock_sm.add.assert_called_once()

    def test_dead_letter_after_max_retries(self):
        mock_sm = MagicMock()
        mock_sm.add.side_effect = RuntimeError("SM down")
        cb = CircuitBreaker(failure_threshold=100, recovery_timeout=0)  # Don't trip CB

        worker = OutboxWorker(mock_sm, cb)
        worker.start()

        entry = OutboxEntry(
            action="add",
            graph_id="test_graph",
            text="will fail",
            metadata={},
            max_retries=1,  # Fail fast
        )
        worker.enqueue(entry)

        # Wait for retries + dead letter
        time.sleep(5.0)
        worker.stop()

        assert len(worker.get_dead_letters()) >= 1
