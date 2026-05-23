# Python overlay

Applied when `pyproject.toml`, `requirements.txt`, or `setup.py` is
present, or any `.py` file appears in the diff. Covers FastAPI, Flask,
Django, generic library code, and scripts.

## Python-specific blockers

- **Bare `except:` or `except Exception:`** that swallows the error
  without re-raising or logging with context → blocking. Catch the
  specific exception or re-raise.
- **Mutable default arguments** (`def f(items=[])`) → blocking. Use
  `None` and assign inside the body.
- **SQL via string formatting** — `cur.execute(f"... {user_input} ...")`
  or `% / .format` interpolation → blocking. Use parameterized queries.
- **`subprocess` with `shell=True`** and any user-derived value in the
  command → blocking. Pass arguments as a list, no shell.
- **`pickle.loads` / `yaml.load` (without `SafeLoader`) / `eval` /
  `exec`** on untrusted input → blocking.
- **Missing type hints on public functions** in a typed codebase
  (one where `mypy` or `pyright` is configured) → blocking.
- **`requests` / `httpx` calls without a `timeout`** → blocking;
  hanging connections take down workers.
- **`assert` in production code paths** → blocking. `assert` is stripped
  with `-O`, so it cannot enforce safety invariants. Use `if … raise`.
- **`open(path)` without context manager or explicit `.close()`** →
  blocking when in a loop or long-running path.

## Async-specific blockers

- **Blocking I/O inside an async function** (`time.sleep`, `requests.get`,
  synchronous DB drivers in an `async def`) → blocking. Use `asyncio.sleep`,
  `httpx.AsyncClient`, or run blocking code in an executor.
- **`asyncio.create_task` without awaiting or storing** → task is
  garbage-collected and the warning is silent. Blocking.

## Style — request, do not block

- Prefer `pathlib.Path` over `os.path` string juggling.
- Prefer dataclasses or Pydantic models over loose `dict[str, Any]`
  for structured data.
- f-strings preferred over `%` and `.format`, except inside logging
  calls where lazy `%`-style formatting is correct
  (`logger.info("user %s did x", user.id)`).

## Tooling expectations

A PR should pass:

```bash
ruff check .
ruff format --check .
mypy . || pyright .
pytest
```

If any of these are not configured for the project, do not invent
findings; only enforce what the project itself enforces.
