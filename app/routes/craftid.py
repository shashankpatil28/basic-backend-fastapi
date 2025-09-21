# app/routes/craftid.py
import os
import hashlib
import jwt, asyncio
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from app.mongodb import ensure_initialized, collection, next_sequence
from app.models import OnboardingData
from pymongo import ReturnDocument  # for counters if needed

router = APIRouter()
SECRET_KEY = os.getenv("SECRET_KEY", "change_this_in_prod")
ALGORITHM = "HS256"

@router.post("/create")
async def create_craftid(data: OnboardingData):
    try:
        await ensure_initialized()
    except Exception as e:
        # 502 indicates upstream dependency (DB) failed
        raise HTTPException(status_code=502, detail=f"DB init error: {str(e)}")

    coll = collection("craftids")

    # Normalized art name for uniqueness (simple approach)
    art_name_norm = data.art.name.strip().lower()
    try:
        existing = await asyncio.wait_for(coll.find_one({"art_name_norm": art_name_norm}), timeout=4)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="DB read timed out")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB read error: {e}")

    if existing:
        raise HTTPException(status_code=409, detail="A similar product name already exists.")

    # get atomic sequence
    try:
        seq = await asyncio.wait_for(next_sequence("craftid_seq"), timeout=4)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to allocate public id: {e}")

    public_id = f"CID-{seq:05d}"
    payload = {"public_id": public_id, "exp": datetime.utcnow() + timedelta(days=365)}
    private_key = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    public_hash = hashlib.sha256((data.art.name + data.art.description + data.art.photo).encode()).hexdigest()

    doc = {
        "public_id": public_id,
        "private_key": private_key,
        "public_hash": public_hash,
        "art_name_norm": art_name_norm,
        "original_onboarding_data": data.dict(),
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    await coll.insert_one(doc)

    transaction_id = "tx_" + datetime.utcnow().strftime("%Y%m%d%H%M%S")

    response = {
        "status": "success",
        "message": f"Your CraftID for '{data.art.name}' has been created successfully.",
        "transaction_id": transaction_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "verification": {
            "public_id": public_id,
            "private_key": private_key,
            "public_hash": public_hash,
            "verification_url": f"http://localhost:8001/verify/{public_id}",
            "qr_code_link": f"http://localhost:8001/verify/qr/{public_id}"
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
            "track_status": f"http://localhost:8001/status/{transaction_id}",
            "shop_listing": f"http://localhost:8001/shop/{public_id}"
        }
    }
    return response
