"""Errors raised by the adapters. None holds a prompt, a reply or a response body, because
those carry personal data."""


class AdapterError(Exception):
    """A model call failed. `status` is the HTTP or Lambda status code and nothing else."""

    def __init__(self, status: int | None):
        super().__init__(f"model call failed with status {status}")
        self.status = status


class RefusedTarget(AdapterError):
    """The adapter was pointed at something other than a mock (ADR 0023, decision 8)."""

    def __init__(self, reason: str):
        Exception.__init__(self, f"refused target: {reason}")
        self.status = None
