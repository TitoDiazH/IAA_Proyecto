from app.database import _connection_error_is_non_retryable


def test_authentication_errors_are_not_retried():
    assert _connection_error_is_non_retryable(
        RuntimeError("FATAL: password authentication failed for user postgres")
    )
    assert _connection_error_is_non_retryable(
        RuntimeError("(ECIRCUITBREAKER) too many authentication failures")
    )


def test_transient_connection_errors_can_be_retried():
    assert not _connection_error_is_non_retryable(RuntimeError("connection timed out"))
