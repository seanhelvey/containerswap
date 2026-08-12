# fast-api

Minimal FastAPI app deployed on [FastAPI Cloud](https://fastapicloud.com).

## Local development

```bash
uv sync
uv run fastapi dev
```

Open http://127.0.0.1:8000 — docs at http://127.0.0.1:8000/docs

## Deploy

```bash
uv run fastapi login   # once
uv run fastapi deploy
```
