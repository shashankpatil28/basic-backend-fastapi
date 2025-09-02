# app/main.py
import os
import json
import hashlib
from datetime import datetime, timedelta
import ssl

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr

import jwt  # from PyJWT
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from sqlalchemy.dialects.postgresql import JSONB  # (used for types in notes)

from dotenv import load_dotenv

load_dotenv()
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False  # Neon already verifies certs
ssl_context.verify_mode = ssl.CERT_REQUIRED

# ==============================================================================
# 1. Pydantic Models (unchanged)
# ==============================================================================
class Artisan(BaseModel):
    name: str
    location: str
    contact_number: str
    email: EmailStr
    aadhaar_number: str

class Art(BaseModel):
    name: str
    description: str
    photo: str  # Base64 encoded image string

class OnboardingData(BaseModel):
    artisan: Artisan
    art: Art

# ==============================================================================
# 2. Config
# ==============================================================================
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-prod")
ALGORITHM = "HS256"

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Serverless-friendly: do not hold connections between invocations
engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    connect_args={"ssl": ssl_context},  # Neon requires SSL
    pool_pre_ping=True,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# ==============================================================================
# 3. FastAPI app
# ==============================================================================
app = FastAPI(title="Master-IP Prototype Service", version="0.1.0")

# Run once per cold start: create table/sequence/indexes if missing
DDL_INIT = """
CREATE TABLE IF NOT EXISTS craftids (
    id BIGSERIAL PRIMARY KEY,
    public_id TEXT UNIQUE NOT NULL,
    private_key TEXT NOT NULL,
    public_hash TEXT NOT NULL,
    original_onboarding_data JSONB NOT NULL,
    artisan_name TEXT NOT NULL,
    artisan_location TEXT NOT NULL,
    artisan_contact_number TEXT NOT NULL,
    artisan_email TEXT NOT NULL,
    artisan_aadhaar_number TEXT NOT NULL,
    art_name TEXT NOT NULL,
    art_description TEXT NOT NULL,
    art_photo TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Sequence for human-friendly public_id numbers (separate from internal id)
CREATE SEQUENCE IF NOT EXISTS craftid_public_seq START WITH 1 INCREMENT BY 1;

-- Case-insensitive uniqueness on art_name
CREATE UNIQUE INDEX IF NOT EXISTS idx_craftids_art_name_lower
    ON craftids ((lower(art_name)));

-- Helpful index for verification by hash
CREATE INDEX IF NOT EXISTS idx_craftids_public_hash
    ON craftids (public_hash);
"""

@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.exec_driver_sql(DDL_INIT)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"message": "Prototype Master-IP backend is running!"}

# ==============================================================================
# 4. POST /create  (now async + Postgres)
# ==============================================================================
@app.post("/create")
async def create_craftid(data: OnboardingData):
    async with SessionLocal() as session:
        async with session.begin():
            # Uniqueness: case-insensitive art name
            check = await session.execute(
                text("SELECT 1 FROM craftids WHERE lower(art_name) = lower(:nm) LIMIT 1"),
                {"nm": data.art.name},
            )
            if check.scalar() is not None:
                raise HTTPException(
                    status_code=409,
                    detail="A similar product name already exists. Please provide a more unique name."
                )

            # Public ID via sequence
            nextval = await session.execute(text("SELECT nextval('craftid_public_seq')"))
            n = int(nextval.scalar_one())
            public_id = f"CID-{n:05d}"

            # JWT as private key
            payload = {"public_id": public_id, "exp": datetime.utcnow() + timedelta(days=365)}
            private_key = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
            if isinstance(private_key, bytes):
                private_key = private_key.decode()

            # Public hash
            public_hash = hashlib.sha256(
                (data.art.name + data.art.description + data.art.photo).encode()
            ).hexdigest()

            # Insert row
            await session.execute(
                text("""
                    INSERT INTO craftids (
                        public_id, private_key, public_hash, original_onboarding_data,
                        artisan_name, artisan_location, artisan_contact_number, artisan_email, artisan_aadhaar_number,
                        art_name, art_description, art_photo
                    )
                    VALUES (
                        :public_id, :private_key, :public_hash, :onboarding::jsonb,
                        :artisan_name, :artisan_location, :artisan_contact_number, :artisan_email, :artisan_aadhaar_number,
                        :art_name, :art_description, :art_photo
                    )
                """),
                {
                    "public_id": public_id,
                    "private_key": private_key,
                    "public_hash": public_hash,
                    # Cast to JSONB in SQL; we pass serialized JSON string
                    "onboarding": json.dumps(data.dict()),
                    "artisan_name": data.artisan.name,
                    "artisan_location": data.artisan.location,
                    "artisan_contact_number": data.artisan.contact_number,
                    "artisan_email": str(data.artisan.email),
                    "artisan_aadhaar_number": data.artisan.aadhaar_number,
                    "art_name": data.art.name,
                    "art_description": data.art.description,
                    "art_photo": data.art.photo,
                }
            )

    # Build response
    transaction_id = "tx_" + datetime.utcnow().strftime("%Y%m%d%H%M%S")
    response_data = {
        "status": "success",
        "message": f"Your CraftID for '{data.art.name}' has been created successfully.",
        "transaction_id": transaction_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "verification": {
            "public_id": public_id,
            "private_key": private_key,
            "public_hash": public_hash,
            "verification_url": f"{API_BASE_URL}/verify/{public_id}",
            "qr_code_link": f"{API_BASE_URL}/verify/qr/{public_id}"
        },
        "artisan_info": {
            "name": data.artisan.name,
            "location": data.artisan.location
        },
        "art_info": {
            "name": data.art.name,
            "description": data.art.description
        },
        "original_onboarding_data": data.dict(),
        "links": {
            "track_status": f"{API_BASE_URL}/status/{transaction_id}",
            "shop_listing": f"{API_BASE_URL}/shop/{public_id}"
        }
    }
    return response_data

# Local dev entrypoint only
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
