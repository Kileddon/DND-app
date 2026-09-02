# Development rules

- Keep dependency direction explicit: `domain` imports no FastAPI, Pydantic, SQLAlchemy, filesystem, or network code; `application` depends on domain and narrow external-boundary protocols; `infrastructure` implements persistence and side effects; `api` only maps transport DTOs to application commands and responses.
- Build a modular monolith. Apply OOP and SOLID pragmatically: prefer readable composition, cohesive functions, explicit state, localized side effects, and typed errors.
- Do not introduce speculative abstractions. In particular, avoid generic repositories, universal CRUD services, `BaseManager`, `AbstractServiceFactory`, deep inheritance, empty future-facing interfaces, global mutable state, and framework models in the domain.
- Persist a state change and its domain event in one transaction. Keep network publication outside open database transactions. Commands that can be retried must be idempotent by command ID.
- Add behavior-focused tests with changes. Critical domain rules require DB/network-free unit tests; transaction, migration, API error, idempotency, and restart behavior require integration tests; preserve the end-to-end vertical-slice acceptance test.
- Before handoff run: `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src tests`, and `uv run pytest`.
- Do not commit secrets, local databases, user media, logs, caches, or temporary files. Do not create a Git commit unless the user explicitly asks.
