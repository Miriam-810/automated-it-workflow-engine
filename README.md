# Automated IT Workflow Engine

A governance service for IT resource requests (laptops, licenses, privileged access…), built with **FastAPI**, **SQLAlchemy 2.0** and **Pydantic v2**. Each request goes through a declarative policy engine that auto-approves, auto-rejects or routes it to a manager. The request then moves through an explicit state machine, and every state change is written to an append-only audit log.

## Core features

- **Request lifecycle state machine**: illegal transitions are rejected with `409 Conflict` and never reach the database.
- **Declarative, explainable policy engine**: rules live in [`policy.yaml`](policy.yaml), not in code. The rule that decided a request (`decision_rule`, `decision_reason`) is stored on the request, and `POST /api/v1/policy/evaluate` previews a decision without creating anything.
- **Append-only audit trail**: every transition writes an `AuditEvent` (who, when, from → to, why) in the same transaction as the status change. ORM-level guards block updates and deletes on audit rows.
- **Governance controls**: segregation of duties (requesters can't approve their own requests), only the requester can cancel, and rejections and failures must include a reason.
- **Optimistic locking**: a `version` column detects concurrent updates. If two managers act on the same request at once, the second one gets `409` instead of silently overwriting the first.

## Lifecycle

```
pending ──► approved ──► provisioning ──► fulfilled
 │  │          │            ▲     │
 │  │          ▼            │     ▼
 │  │      cancelled        └─ failed   (retry)
 │  └──► cancelled
 └─────► rejected
```

Terminal states: `rejected`, `cancelled`, `fulfilled`. Every response includes `allowed_transitions` so clients know which actions are valid next.

## Policy rules

Rules are evaluated top to bottom, and the first match wins. Conditions inside a rule are AND-ed. If no rule matches, `default_outcome` applies.

| Rule | Condition | Outcome |
|---|---|---|
| `budget-cap` | cost ≥ 5000 | auto reject |
| `insufficient-justification` | justification < 10 chars | manager review |
| `privileged-access` | `prod-access`, `admin-rights`, `vpn-exception` | manager review |
| `low-cost` | cost < 50 | auto approve |
| `standard-software` | `software-license`, cost < 200 | auto approve |
| *(default)* | — | manager review |

Supported conditions: `resource_types`, `min_cost` (inclusive), `max_cost` (exclusive), `min_justification_length`, `max_justification_length`. The policy file is schema-validated at startup, so unknown keys or duplicate rule ids stop the app from booting.

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/requests` | Submit a request (policy runs immediately) |
| `GET` | `/api/v1/requests?status=&employee_id=&limit=&offset=` | List with filters and pagination |
| `GET` | `/api/v1/requests/{id}` | Get one request |
| `GET` | `/api/v1/requests/{id}/events` | Audit trail for a request |
| `POST` | `/api/v1/requests/{id}/approve` | Manager approves (`actor` ≠ requester) |
| `POST` | `/api/v1/requests/{id}/reject` | Manager rejects (`reason` required) |
| `POST` | `/api/v1/requests/{id}/cancel` | Requester withdraws |
| `POST` | `/api/v1/requests/{id}/provision` | Start (or retry) provisioning |
| `POST` | `/api/v1/requests/{id}/complete` | Mark fulfilled |
| `POST` | `/api/v1/requests/{id}/fail` | Mark failed (`reason` required) |
| `GET` | `/api/v1/policy` | Active policy |
| `POST` | `/api/v1/policy/evaluate` | Dry-run the policy for a payload |

Interactive docs are served at `/docs` while the app is running.

> Authentication is not implemented yet. For now, `actor` is supplied in the request body.

## Getting started

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn main:app --reload
pytest
```

Configuration (environment variables):

- `DATABASE_URL`: defaults to `sqlite:///./sql_app.db`
- `POLICY_PATH`: defaults to `./policy.yaml`

## Repository structure

- `main.py`: API routes and request/response wiring
- `workflow.py`: state machine (`ALLOWED_TRANSITIONS`, `transition()`)
- `rules.py`: policy schema, loader and evaluator
- `policy.yaml`: governance rules
- `models.py`: ORM models (`ApprovalRequest`, `AuditEvent`) and audit immutability guard
- `schemas.py`: Pydantic request/response models
- `database.py`: engine, session factory, `get_db` dependency
- `tests/`: unit tests for rules and the state machine, plus API tests against an in-memory DB

## Roadmap

- [ ] `app/` package layout, Alembic migrations, Docker, GitHub Actions CI
- [ ] Authentication and roles (employee / manager / admin)
- [ ] Background provisioning worker with retries and idempotency keys
- [ ] Request-ID middleware and structured logging
