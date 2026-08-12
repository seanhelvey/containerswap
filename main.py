from fastapi import FastAPI

app = FastAPI(title="fast-api")


@app.get("/")
async def read_root():
    return {"message": "Hello from FastAPI Cloud"}


@app.get("/health")
async def health():
    return {"status": "ok"}
