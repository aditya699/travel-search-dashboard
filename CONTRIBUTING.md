# Contributing

Thanks for helping. A few things keep the project easy to work on:

- **Everything runs offline.** Tests use the demo sites and the fake LLM; please keep
  it that way, so CI and new contributors never need a key.
- **Config over code.** Sites, routes, carriers, airports and access rules are JSON in
  `server/app/config/`. A change that only adds one of those should not touch Python.
- **Checks before charts.** If you add a field to the cleaned schema, add a check for
  it in `app/clean/validate.py` and a case in `tests/test_clean.py`.

## Before you open a pull request

```bash
cd server
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

```bash
cd client
npm run lint
npm run build
```

CI runs the same commands.
