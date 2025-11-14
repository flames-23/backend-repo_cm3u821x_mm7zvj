import os
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database import create_document, get_documents, db

# Import schemas for typing
from schemas import Intervention as InterventionSchema, Reference as ReferenceSchema

app = FastAPI(title="Road Safety Intervention GPT API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Road Safety Intervention API is running"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# ---------------------------
# Data Models (Requests)
# ---------------------------
class Reference(BaseModel):
    source: str
    title: str
    url: Optional[str] = None
    excerpt: Optional[str] = None

class InterventionIn(BaseModel):
    name: str
    description: str
    road_types: List[str]
    issues: List[str]
    environments: List[str]
    cost_level: str
    complexity: str
    effectiveness: Optional[Dict[str, float]] = None
    constraints: Optional[List[str]] = None
    suitable_speed_range: Optional[List[int]] = None
    urban_rural: Optional[List[str]] = None
    co_benefits: Optional[List[str]] = None
    references: List[Reference] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


# ---------------------------
# Utilities
# ---------------------------
INTERVENTION_COLLECTION = "intervention"

KNOWN_ROAD_TYPES = [
    "urban arterial", "urban collector", "local street", "rural highway", "rural arterial", "expressway",
    "village road", "residential street", "state highway", "national highway"
]
KNOWN_ISSUES = [
    "speeding", "pedestrian crashes", "rear-end crashes", "run-off-road", "head-on", "intersection conflicts",
    "nighttime visibility", "overtaking", "wrong-way", "work zone safety", "bicyclist safety", "school zone safety"
]
KNOWN_ENVIRONMENTS = [
    "school zone", "market area", "mixed land use", "curve", "intersection", "midblock", "work zone",
    "bridge", "tunnel", "bus stop", "railway crossing"
]

WEIGHTS = {
    "issues": 0.45,
    "road_types": 0.25,
    "environments": 0.2,
    "speed": 0.05,
    "urban_rural": 0.05,
}


def normalize(text: str) -> str:
    return text.strip().lower()


def list_overlap(a: List[str], b: List[str]) -> int:
    sa = {normalize(x) for x in a}
    sb = {normalize(x) for x in b}
    return len(sa.intersection(sb))


def speed_in_range(speed_kmh: Optional[int], rng: Optional[List[int]]) -> bool:
    if speed_kmh is None or not rng or len(rng) != 2:
        return False
    return rng[0] <= speed_kmh <= rng[1]


def rank_interventions(
    interventions: List[Dict[str, Any]],
    *,
    road_type: Optional[str],
    issues: List[str],
    environments: List[str],
    speed_kmh: Optional[int],
    urban_rural: Optional[str]
) -> List[Dict[str, Any]]:
    ranked = []
    for it in interventions:
        score = 0.0
        reasons = []
        # Issues matching
        if issues:
            overlap = list_overlap(issues, it.get("issues", []))
            if len(issues) > 0:
                s = WEIGHTS["issues"] * (overlap / len(set(map(normalize, issues))))
                score += s
                if overlap:
                    reasons.append(f"Matches issues: {overlap}/{len(set(map(normalize, issues)))}")
        # Road type
        if road_type:
            overlap = list_overlap([road_type], it.get("road_types", []))
            if overlap:
                score += WEIGHTS["road_types"]
                reasons.append("Applicable to specified road type")
        # Environment
        if environments:
            overlap = list_overlap(environments, it.get("environments", []))
            if len(environments) > 0:
                s = WEIGHTS["environments"] * (overlap / len(set(map(normalize, environments))))
                score += s
                if overlap:
                    reasons.append("Suitable for the described environment")
        # Speed
        if speed_kmh is not None and it.get("suitable_speed_range"):
            if speed_in_range(speed_kmh, it.get("suitable_speed_range")):
                score += WEIGHTS["speed"]
                reasons.append("Effective within given speed range")
        # Urban/rural
        if urban_rural and it.get("urban_rural"):
            if normalize(urban_rural) in [normalize(x) for x in it.get("urban_rural", [])]:
                score += WEIGHTS["urban_rural"]
                reasons.append("Designed for the specified context (urban/rural)")

        ranked.append({
            **it,
            "_score": round(score, 4),
            "_reasons": reasons
        })

    ranked.sort(key=lambda x: x["_score"], reverse=True)
    return ranked


def parse_free_text(prompt: str) -> Dict[str, Any]:
    """Very simple keyword-based parser to map free text into filters."""
    p = normalize(prompt)
    road_type = next((rt for rt in KNOWN_ROAD_TYPES if rt in p), None)
    urban_rural = None
    if "urban" in p:
        urban_rural = "urban"
    elif "rural" in p:
        urban_rural = "rural"

    issues = [kw for kw in KNOWN_ISSUES if kw in p]
    environments = [kw for kw in KNOWN_ENVIRONMENTS if kw in p]

    # crude speed extraction
    speed_kmh = None
    for token in p.replace("km/h", "kmh").split():
        if token.isdigit():
            n = int(token)
            if 10 <= n <= 130:
                speed_kmh = n
                break

    return {
        "road_type": road_type,
        "issues": issues,
        "environments": environments,
        "speed_kmh": speed_kmh,
        "urban_rural": urban_rural
    }


# ---------------------------
# Endpoints
# ---------------------------
@app.post("/interventions")
def create_intervention(payload: InterventionIn):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    data = payload.model_dump()
    inserted_id = create_document(INTERVENTION_COLLECTION, data)
    return {"id": inserted_id}


@app.get("/interventions")
def list_interventions(road_type: Optional[str] = None,
                      issue: Optional[str] = None,
                      environment: Optional[str] = None,
                      limit: int = 100):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    filt: Dict[str, Any] = {}
    if road_type:
        filt["road_types"] = {"$in": [road_type]}
    if issue:
        filt["issues"] = {"$in": [issue]}
    if environment:
        filt["environments"] = {"$in": [environment]}

    docs = get_documents(INTERVENTION_COLLECTION, filt, limit)
    # Convert ObjectId
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return {"items": docs}


class RecommendationRequest(BaseModel):
    prompt: Optional[str] = None
    road_type: Optional[str] = None
    issues: List[str] = Field(default_factory=list)
    environments: List[str] = Field(default_factory=list)
    speed_kmh: Optional[int] = None
    urban_rural: Optional[str] = None
    top_k: int = 10


@app.post("/recommendations")
def recommend(req: RecommendationRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    filters = {
        "road_type": req.road_type,
        "issues": req.issues,
        "environments": req.environments,
        "speed_kmh": req.speed_kmh,
        "urban_rural": req.urban_rural,
    }

    if req.prompt:
        parsed = parse_free_text(req.prompt)
        # Merge: explicit fields override parsed
        for k, v in parsed.items():
            if (k in ["issues", "environments"] and not filters[k]) or (k not in ["issues", "environments"] and filters[k] is None):
                filters[k] = v

    docs = get_documents(INTERVENTION_COLLECTION, {}, None)
    # Convert ObjectId
    items: List[Dict[str, Any]] = []
    for d in docs:
        d["id"] = str(d.pop("_id"))
        items.append(d)

    ranked = rank_interventions(
        items,
        road_type=filters["road_type"],
        issues=filters["issues"] or [],
        environments=filters["environments"] or [],
        speed_kmh=filters["speed_kmh"],
        urban_rural=filters["urban_rural"],
    )

    top = ranked[: max(1, min(req.top_k, 50))]

    # Build explanation text using references
    results = []
    for it in top:
        refs = it.get("references", []) or []
        ref_notes = []
        for r in refs[:3]:
            src = r.get("source") or ""
            title = r.get("title") or ""
            url = r.get("url") or None
            ref_notes.append({"source": src, "title": title, "url": url, "excerpt": r.get("excerpt")})

        results.append({
            "id": it.get("id"),
            "name": it.get("name"),
            "description": it.get("description"),
            "score": it.get("_score"),
            "reasons": it.get("_reasons"),
            "applicability": {
                "road_types": it.get("road_types", []),
                "issues": it.get("issues", []),
                "environments": it.get("environments", []),
                "suitable_speed_range": it.get("suitable_speed_range"),
                "urban_rural": it.get("urban_rural"),
            },
            "references": ref_notes,
            "constraints": it.get("constraints", []),
            "co_benefits": it.get("co_benefits", []),
        })

    return {
        "filters_used": filters,
        "count": len(results),
        "items": results,
    }


# ---------------------------
# Optional: Seed minimal dataset for demo purposes
# ---------------------------
SEED_DATA: List[InterventionIn] = [
    InterventionIn(
        name="Raised Pedestrian Crossing",
        description="A raised table at pedestrian crossing that slows vehicles and improves visibility.",
        road_types=["urban arterial", "urban collector", "local street"],
        issues=["speeding", "pedestrian crashes"],
        environments=["school zone", "market area", "midblock"],
        cost_level="medium",
        complexity="medium",
        suitable_speed_range=[20, 50],
        urban_rural=["urban"],
        co_benefits=["traffic calming", "accessibility"],
        references=[
            Reference(source="WHO", title="Pedestrian safety: a road safety manual", url="https://www.who.int/publications/i/item/pedestrian-safety-a-road-safety-manual"),
            Reference(source="FHWA", title="Safety Effects of Marked vs. Unmarked Crosswalks", url="https://safety.fhwa.dot.gov/"),
        ],
        tags=["pedestrian", "crossing", "traffic calming"],
    ),
    InterventionIn(
        name="Rumble Strips (Shoulder/Centerline)",
        description="Milled rumble strips alert drivers who drift from their lane, reducing run-off-road and head-on crashes.",
        road_types=["rural highway", "rural arterial", "state highway", "national highway"],
        issues=["run-off-road", "head-on"],
        environments=["curve", "midblock"],
        cost_level="low",
        complexity="low",
        suitable_speed_range=[50, 110],
        urban_rural=["rural"],
        co_benefits=["fatigue management"],
        references=[
            Reference(source="FHWA", title="Rumble Strips and Rumble Stripes", url="https://safety.fhwa.dot.gov/"),
            Reference(source="PIARC", title="Road Safety Manual"),
        ],
        tags=["run-off-road", "lane departure"],
    ),
    InterventionIn(
        name="Roundabout Conversion",
        description="Replace signalized or stop-controlled intersection with a roundabout to reduce severe angle crashes.",
        road_types=["urban arterial", "rural arterial", "local street"],
        issues=["intersection conflicts", "head-on"],
        environments=["intersection"],
        cost_level="high",
        complexity="high",
        suitable_speed_range=[20, 60],
        urban_rural=["urban", "rural"],
        co_benefits=["emissions reduction", "traffic calming"],
        references=[
            Reference(source="FHWA", title="Roundabouts: An Informational Guide"),
            Reference(source="IRC", title="Guidelines for Traffic Management in Urban Areas"),
        ],
        tags=["intersection", "conversion"],
    ),
]


def seed_if_empty() -> None:
    try:
        if db is None:
            return
        count = db[INTERVENTION_COLLECTION].count_documents({})
        if count == 0:
            for item in SEED_DATA:
                create_document(INTERVENTION_COLLECTION, item.model_dump())
    except Exception:
        # Ignore seeding errors to avoid crashing the app in environments without DB
        pass


seed_if_empty()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
