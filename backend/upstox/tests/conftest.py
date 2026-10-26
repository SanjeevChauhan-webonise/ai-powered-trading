"""Reuse the app-level fixtures (test client, knowledge base) for the endpoint tests."""

from tests.conftest import client, kb

__all__ = ["client", "kb"]
