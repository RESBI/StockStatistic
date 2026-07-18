"""Thread-safe state for admin plugin.

Isolated from the main backend to avoid polluting its namespace.
"""
from __future__ import annotations

import threading

# Serializes all ingest/delete operations (SQLite write safety)
_ingest_lock = threading.Lock()

# Batch task tracking: batch_id -> {total, completed, current, status, results}
_batch_tasks: dict[str, dict] = {}

# Flag to ensure log table is created only once
_log_table_created = False
