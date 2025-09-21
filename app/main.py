# app/main.py
import os
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

# serverless-friendly mongodb helpers (lazy init)
from app.mongodb import ensure_initialized

# try to import optional create_indexes if mongodb.py provides it
try:
    from app.mongodb import create_indexes  # type: ignore
except Exception:
    create_indexes = None

from app.routes.craftid import router as craftid_router

load_dotenv()

app = FastAPI(title="Master-IP Prototype Service", version="0.1.0")

# include your main API routes
app.include_router(craftid_router)


@app.get("/")
async def root():
    return {"message": "Prototype Master-IP backend is running!"}


@app.post("/init-db")
async def init_db():
    """
    Admin endpoint (call once after deploy) to:
     - ensure DB connectivity
     - optionally create indexes if create_indexes() is implemented
    Note: Protect or remove this endpoint in production!
    """
    try:
        await ensure_initialized()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"DB init failed: {e}")

    if create_indexes is not None:
        try:
            # create_indexes is likely an async function
            maybe_awaitable = create_indexes()
            if hasattr(maybe_awaitable, "__await__"):
                await maybe_awaitable
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"create_indexes failed: {e}")

    return {"status": "ok", "detail": "DB initialized (and indexes created if available)"}
