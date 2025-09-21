# app/main.py
import os
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

from app.routes.craftid import router as craftid_router
from app.routes.products import router as products_router

# Import helper from your mongodb.py
from app.mongodb import ensure_initialized, close as mongo_close

load_dotenv()

app = FastAPI(title="Master-IP Prototype Service", version="0.1.0")

# include routers
app.include_router(craftid_router)
app.include_router(products_router)


@app.get("/")
async def root():
    return {"message": "Prototype Master-IP backend is running!"}


@app.post("/init-db")
async def init_db():
    """
    Admin: Initialize DB (call once after deploy).
    If ensure_initialized fails due to old loop issues, attempt to reset client and retry.
    """
    try:
        await ensure_initialized()
    except Exception as e:
        # try reset and retry
        try:
            mongo_close()
            await ensure_initialized()
        except Exception as e2:
            raise HTTPException(status_code=502, detail=f"DB init failed: {e}; retry failed: {e2}")
    return {"status": "ok", "detail": "DB initialized or already ready."}
