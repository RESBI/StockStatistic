# Legacy V3 Archive

This directory contains the pre-V3.1 runtime and its migration fixtures. It is retained for read-only comparison and rollback investigation.

- `frontend/`: legacy public `stockstat` package and finance runtime.
- `backend/`: legacy Storage/API implementation.
- `worker/`: legacy distributed compute Worker.

No V3.1 package may import code from this directory. The repository root, default documentation, test configuration, installation scripts, and Docker Compose describe V3.1 only.
