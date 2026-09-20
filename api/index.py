import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List

# Import the orchestrator instance from the original application.
from app import orchestrator

app = FastAPI(title="ChargeMate API")

# Enable CORS for cross-origin local testing if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    latitude: Optional[float] = None
    lat: Optional[float] = None
    longitude: Optional[float] = None
    lon: Optional[float] = None
    remaining_range_km: float = 40.0
    search_radius_km: Optional[float] = None
    show_debug: bool = False

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """Process a user message via the existing orchestrator.

    Returns a JSON payload containing:
      - ``reply``: the textual answer shown to the user
      - ``rows``: list of station result objects (name, distance_km, eta_min,
        power_kw, price, score)
      - ``intent``: the parsed intent dictionary (useful for debugging)
    """
    actual_lat = req.latitude if req.latitude is not None else req.lat
    actual_lon = req.longitude if req.longitude is not None else req.lon

    if actual_lat is None:
        actual_lat = 21.1263
    if actual_lon is None:
        actual_lon = 79.1600

    reply, rows, intent = orchestrator.handle_request(
        user_text=req.message,
        lat=float(actual_lat),
        lon=float(actual_lon),
        remaining_range_km=req.remaining_range_km,
        search_radius_km=req.search_radius_km,
    )

    # Convert the row list (list of lists) into structured dicts.
    result_rows: List[dict] = []
    for row in rows:
        if len(row) >= 6:
            name, dist, eta, power, price, score = row[:6]
            result_rows.append({
                "name": name,
                "distance_km": dist,
                "eta_min": eta,
                "power_kw": power,
                "price": price,
                "score": score,
            })

    return {
        "reply": reply,
        "rows": result_rows,
        "intent": intent,
    }

# Mount static files if the public directory exists (for local testing)
public_path = Path(__file__).resolve().parent.parent / "public"
if public_path.exists():
    app.mount("/", StaticFiles(directory=str(public_path), html=True), name="public")

# Export the FastAPI app as ``handler`` for Vercel.
handler = app

