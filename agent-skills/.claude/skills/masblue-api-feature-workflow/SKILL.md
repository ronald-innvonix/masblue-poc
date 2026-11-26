---
name: masblue-api-feature-workflow
description: Step-by-step workflow for adding or changing an API feature in the Masblue AI Chat Service (new endpoint, route, service, repository method, Pydantic schema, or SSE stream) in the correct layer order with auth, pagination, error handling, and tests. Use this skill whenever the task is to add, extend, or modify an endpoint or use case, expose existing data over HTTP, add a repository query, add request/response models, wire a dependency, or "build the X feature", even if the user does not mention layers or FastAPI.
---

# Adding an API feature

Read `masblue-project-standards` first if you have not (layering rules, conventions, definition of
done). This skill is the recipe; `references/worked-example.md` is a complete, tested feature
(`GET /api/v1/conversations`) that follows it. Mirror that example's shape.

## Build order (bottom-up)

Building bottom-up keeps every step type-checkable and testable on its own.

1. **Clarify the contract.** Method, path, auth (almost always required), request fields,
   response shape, error cases, pagination. If the architecture doc already specifies it
   (`docs/MASBLUE_AI_POC_ARCHITECTURE.md`), follow it and note any deviation.
2. **Model/migration only if a column or table is genuinely new.** Then use
   `masblue-database-migrations`. Prefer reusing existing tables.
3. **Schema** in `schemas/<domain>.py`: request models with `Field(...)` constraints, response models
   with `ConfigDict(from_attributes=True)` when built from ORM objects.
4. **Repository method** in `repositories/<entity>_repo.py`: SQL only, keyword-only paging args,
   deterministic ordering with a tiebreaker, user scoping in the `WHERE`. `flush()` on writes, never
   `commit()`.
5. **Service** in `services/<name>_service.py`: constructor takes repositories (and the session if
   it must commit). Implements the use case, enforces rules, raises `AppError` subclasses, commits
   once on success. No FastAPI imports.
6. **Dependency** in `api/deps.py`: `async def get_<name>_service(session: Annotated[AsyncSession,
   Depends(get_db)]) -> <Name>Service`. Wiring only.
7. **Route** in `api/v1/<area>.py`, registered in `api/v1/router.py` with a `prefix` and `tags`.
8. **Tests** (see `masblue-testing`): route test with a fake service, a 401 test, a service test with
   a fake repository. Add provider or repository tests when those layers have new logic.
9. **Docs/config**: README endpoint notes if the public API changed; new settings in all four places.
10. **Run the definition of done** from `masblue-project-standards`.

## Route rules

- Declare `user: Annotated[CurrentUser, Depends(get_current_user)]` **first** in the signature. This
  makes FastAPI authenticate before it builds any database-backed dependency, so unauthenticated calls
  fail with 401 without touching PostgreSQL (the existing chat routes get this wrong).
- Add `dependencies=[Depends(rate_limit_placeholder)]` on the router, as the existing routers do.
- One service call per route. The route maps results to a response model and nothing else.
- Always set `response_model=` and a return annotation. Convert ORM objects with
  `Schema.model_validate(obj)`; never return ORM instances.
- Pagination: `page: Annotated[int, Query(ge=1)] = 1`, `page_size: Annotated[int, Query(ge=1,
  le=100)] = 20`; the service turns `page` into `offset`. Return `page`, `page_size`, `total`, and the
  items.
- Ownership: never accept a user id from the client. Use `user.user_id` from the verified JWT.
  When a record is missing **or** belongs to someone else, raise the same
  `AppError("<THING>_NOT_FOUND", "<Thing> not found", 404)`.

## Service rules

- Raise typed errors with `UPPER_SNAKE` codes; never put user input or internals in messages.
- Wrap each use case's writes in one transaction: repositories `flush()`, the service `commit()`s
  once at the end (see `ChatService._prepare_turn`, which commits the user's turn before the slow
  provider call so no transaction stays open during the LLM request).
- Keep services independent of HTTP so they can be unit-tested with fake repositories.

## Streaming endpoints

Copy the structure of `stream_chat` in `api/v1/chat.py`:

- The service exposes an `AsyncIterator[dict[str, str]]`; the route encodes each item as
  `data: <json>\n\n`.
- Catch `AppError` and unexpected exceptions *inside* the generator, emit an `{"error": {...}}` frame,
  and always finish with `data: [DONE]` in `finally`. After headers are sent the status cannot change.
- Return `StreamingResponse(..., media_type="text/event-stream", headers={"Cache-Control": "no-cache",
  "X-Accel-Buffering": "no"})`.
- Do not change existing frame shapes (the React client depends on them) without asking.

## Before you finish, check

- [ ] Auth dependency is first in every new route signature.
- [ ] No DB, SDK, or business logic in the route; no FastAPI import in the service.
- [ ] Every query that returns user data is scoped by `user_id`.
- [ ] Every new function, class, and module has a one-line docstring and full type hints.
- [ ] Tests cover success, 401, validation failure, and not-found/ownership.
- [ ] `ruff check`, `ruff format --check`, `mypy`, `pytest` show no *new* failures
      (the repo has pre-existing ones listed in `masblue-project-standards/references/known-issues.md`).
