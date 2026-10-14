"""Load production router/model registrations for isolated per-file test runs."""

from app.main import app  # noqa: F401 -- register all cross-table ORM references
