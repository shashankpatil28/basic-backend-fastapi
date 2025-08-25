from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import uvicorn

# ==============================================================================
# 1. Pydantic Models
# ==============================================================================
class Artisan(BaseModel):
    id: str
    name: str
    country: str

class Product(BaseModel):
    id: str
    title: str
    category: str

class CompleteArtisanData(BaseModel):
    artisan: List[Artisan]
    product: List[Product]
    metadata: dict = {}

# ==============================================================================
# 2. FastAPI Application
# ==============================================================================
app = FastAPI(title="Artisan IP Verification Backend")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
def root():
    return {"message": "Backend is working!"}

# Define a POST endpoint at /create
@app.post("/create")
async def create_ip_record(complete_data: CompleteArtisanData):
    """
    Receives the JSON data from the IP agent, prints it for verification,
    and returns a dummy JSON response.
    """
    # --------------------------------------------------------------------------
    # For developer verification: print the received data to the console
    # --------------------------------------------------------------------------
    print("\n=========================================================")
    print("Received JSON data from IP agent:")
    # Use .dict() or .json() to convert the Pydantic model to a dictionary/JSON string
    # We use .model_dump_json(indent=2) for a pretty-printed output
    print(complete_data.model_dump_json(indent=2))
    print("=========================================================\n")

    # --------------------------------------------------------------------------
    # 3. Dummy Response
    #    This is a dummy response simulating a successful backend process.
    #    It contains 10+ lines as requested.
    # --------------------------------------------------------------------------
    response_data = {
        "status": "success",
        "message": "Data submitted successfully. IP verification process has been initiated.",
        "transaction_id": "tx_20250825_123456789",
        "timestamp": "2025-08-25T11:10:00Z",
        "details": {
            "product_id": complete_data.product[0].id,
            "artisan_id": complete_data.artisan[0].id,
            "verification_eta": "48 hours",
            "next_steps": [
                "A dedicated IP specialist will review your submission.",
                "You will receive a notification via email once the initial review is complete."
            ]
        },
        "links": {
            "view_status": "http://localhost:8001/status/tx_20250825_123456789"
        }
    }
    return response_data

# ==============================================================================
# 4. Entry point for running the application
# ==============================================================================
if __name__ == "__main__":
    # To run, execute this script and navigate to http://localhost:8001
    # You can access the FastAPI documentation at http://localhost:8001/docs
    uvicorn.run(app, host="0.0.0.0", port=8001)
