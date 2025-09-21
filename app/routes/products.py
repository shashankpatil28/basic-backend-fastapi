# app/routes/products.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import os
import hashlib
import jwt
from datetime import datetime, timedelta
import asyncio

# reuse existing Pydantic models if present; fallback declarations otherwise
try:
    from app.models import OnboardingData, Artisan, Art
except Exception:
    # fallback (keeps file standalone if needed)
    from pydantic import EmailStr
    class Artisan(BaseModel):
        name: str
        location: str
        contact_number: str
        email: EmailStr
        aadhaar_number: str

    class Art(BaseModel):
        name: str
        description: str
        photo: str

    class OnboardingData(BaseModel):
        artisan: Artisan
        art: Art

from app.mongodb import ensure_initialized, collection, next_sequence

router = APIRouter()
SECRET_KEY = os.getenv("SECRET_KEY", "change_in_prod")
ALGORITHM = "HS256"

# Response shape for frontend compatibility
class VerificationData(BaseModel):
    public_id: str
    public_hash: str
    verification_url: str

class ArtisanInfo(BaseModel):
    name: str
    location: str

class ArtInfo(BaseModel):
    name: str
    description: str
    photo: str

class ProductOut(BaseModel):
    artisan_info: ArtisanInfo
    art_info: ArtInfo
    verification: VerificationData
    timestamp: str

# -----------------------
# POST /add-product
# Creates a CraftID entry (if not present) and returns the product payload
# -----------------------
@router.post("/add-product", response_model=ProductOut)
async def add_product(data: OnboardingData):
    # ensure DB initialized (serverless-friendly)
    try:
        await ensure_initialized()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"DB init error: {e}")

    craftids = collection("craftids")

    # normalize art name for uniqueness check
    art_name_norm = data.art.name.strip().lower()

    # quick uniqueness check (avoid duplicate product names)
    try:
        existing = await asyncio.wait_for(craftids.find_one({"art_name_norm": art_name_norm}), timeout=4)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="DB read timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB read error: {e}")

    if existing:
        # If product already exists, return its public fields (idempotent behavior)
        public_id = existing.get("public_id")
        public_hash = existing.get("public_hash")
        verification_url = f"/verify/{public_id}"
        return ProductOut(
            artisan_info=ArtisanInfo(
                name=existing["original_onboarding_data"]["artisan"]["name"],
                location=existing["original_onboarding_data"]["artisan"]["location"]
            ),
            art_info=ArtInfo(
                name=existing["original_onboarding_data"]["art"]["name"],
                description=existing["original_onboarding_data"]["art"]["description"],
                photo=existing["original_onboarding_data"]["art"].get("photo", "")
            ),
            verification=VerificationData(
                public_id=public_id,
                public_hash=public_hash,
                verification_url=verification_url
            ),
            timestamp=existing.get("timestamp")
        )

    # allocate atomic sequence for public_id
    try:
        seq = await asyncio.wait_for(next_sequence("craftid_seq"), timeout=4)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to allocate public id: {e}")

    public_id = f"CID-{seq:05d}"

    payload = {"public_id": public_id, "exp": datetime.utcnow() + timedelta(days=365)}
    private_key = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    public_hash = hashlib.sha256(
        (data.art.name + data.art.description + data.art.photo).encode()
    ).hexdigest()

    doc = {
        "public_id": public_id,
        "private_key": private_key,
        "public_hash": public_hash,
        "art_name_norm": art_name_norm,
        "original_onboarding_data": data.dict(),
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    try:
        await craftids.insert_one(doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB insert error: {e}")

    verification_url = f"/verify/{public_id}"

    return ProductOut(
        artisan_info=ArtisanInfo(name=data.artisan.name, location=data.artisan.location),
        art_info=ArtInfo(name=data.art.name, description=data.art.description, photo=data.art.photo),
        verification=VerificationData(public_id=public_id, public_hash=public_hash, verification_url=verification_url),
        timestamp=doc["timestamp"]
    )

# -----------------------
# GET /get-products
# Returns an array of products (maps craftids collection to frontend shape)
# -----------------------
@router.get("/get-products", response_model=List[ProductOut])
async def get_products():
    try:
        await ensure_initialized()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"DB init error: {e}")

    craftids = collection("craftids")

    try:
        cursor = craftids.find().sort("timestamp", -1)
        docs = await cursor.to_list(length=200)  # limit to 200 results by default
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB read error: {e}")

    out = []
    for d in docs:
        orig = d.get("original_onboarding_data", {})
        artisan = orig.get("artisan", {})
        art = orig.get("art", {})
        public_id = d.get("public_id")
        public_hash = d.get("public_hash")
        verification_url = f"/verify/{public_id}" if public_id else ""

        out.append(ProductOut(
            artisan_info=ArtisanInfo(
                name=artisan.get("name", ""),
                location=artisan.get("location", "")
            ),
            art_info=ArtInfo(
                name=art.get("name", ""),
                description=art.get("description", ""),
                photo=art.get("photo", "")
            ),
            verification=VerificationData(
                public_id=public_id or "",
                public_hash=public_hash or "",
                verification_url=verification_url
            ),
            timestamp=d.get("timestamp", "")
        ))

    return out
