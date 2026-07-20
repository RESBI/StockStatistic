# StockStat V3.1 Architecture Decisions

| ID | Decision |
|---|---|
| ADR-01 | V3.1 code lives under `packages/`, `services/`, and `tests_v31/`; published distributions use the names in the V3.1 design. |
| ADR-02 | Supported Python versions are 3.11 and 3.12. The local implementation environment uses Python 3.12. |
| ADR-03 | Public schemas use Pydantic v2 with unknown fields rejected. Protocol, capability, and Artifact schemas version independently. |
| ADR-04 | Runtime identifiers are UUIDv7-compatible strings; protocol datetimes are timezone-aware UTC; query intervals are `[start, end)`. |
| ADR-05 | Digests use sorted, whitespace-free UTF-8 canonical JSON. NaN and Infinity are rejected. |
| ADR-06 | Artifact identity uses immutable SHA-256 content plus an independent metadata ID. Control messages contain references, never base64 table data. |
| ADR-07 | Finance capabilities use `finance.<domain>.<operation>@major.minor`. Worker roles are limited to `execute` and `reduce`. |
| ADR-08 | V3.0 code is a black-box oracle only. V3.1 packages must not import `frontend`, `backend`, `worker`, or their Python packages. |
| ADR-09 | PostgreSQL is the source of truth for Jobs and leases. Redis is optional, rebuildable acceleration only and is not required for correctness or the initial release profile. |
| ADR-10 | Client bearer tokens and Worker internal tokens are separate. Persisted ownership uses a SHA-256-derived principal ID, never the raw token. |
| ADR-11 | P9 repository cutover may complete while production release remains No-Go if required external deployment drills are unavailable; reports must distinguish code verification from infrastructure certification. |
