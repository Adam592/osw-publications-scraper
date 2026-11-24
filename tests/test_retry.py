import pytest

from osw_scraper.retry import TransientError, call_with_retry


class Flaky:
    """Fails the first `failures` calls, then returns "ok"."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise TransientError("boom")
        return "ok"


def test_succeeds_after_transient_failures():
    delays = []
    func = Flaky(failures=2)
    result = call_with_retry(func, attempts=3, retry_on=(TransientError,), base_delay=1, sleep=delays.append)
    assert result == "ok"
    assert func.calls == 3
    assert delays == [1, 2]


def test_gives_up_and_reraises():
    func = Flaky(failures=5)
    with pytest.raises(TransientError):
        call_with_retry(func, attempts=3, retry_on=(TransientError,), sleep=lambda _: None)
    assert func.calls == 3


def test_does_not_retry_unexpected_errors():
    def broken():
        raise KeyError("bug")

    with pytest.raises(KeyError):
        call_with_retry(broken, attempts=3, retry_on=(TransientError,), sleep=lambda _: None)