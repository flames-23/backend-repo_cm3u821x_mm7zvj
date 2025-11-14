"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict

# Example schemas (replace with your own):

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# Road Safety Intervention schemas

class Reference(BaseModel):
    source: str = Field(..., description="Origin of guidance, e.g., WHO, FHWA, PIARC, IRC")
    title: str = Field(..., description="Document or report title")
    url: Optional[str] = Field(None, description="Link to the source")
    excerpt: Optional[str] = Field(None, description="Short relevant quote or note")

class Intervention(BaseModel):
    name: str = Field(..., description="Intervention name, e.g., Raised Pedestrian Crossing")
    description: str = Field(..., description="What it is and why it works")
    road_types: List[str] = Field(..., description="Applicable road types, e.g., urban arterial, rural highway, local street")
    issues: List[str] = Field(..., description="Safety problems addressed, e.g., speeding, pedestrian crashes, rear-end crashes")
    environments: List[str] = Field(..., description="Context like school zone, market area, curve, intersection, work zone")
    cost_level: str = Field(..., description="low | medium | high")
    complexity: str = Field(..., description="implementation complexity: low | medium | high")
    effectiveness: Optional[Dict[str, float]] = Field(
        default=None,
        description="Optional effect sizes by crash type, e.g., {'pedestrian': 0.35} meaning 35% reduction"
    )
    constraints: Optional[List[str]] = Field(default=None, description="Design constraints or prerequisites")
    suitable_speed_range: Optional[List[int]] = Field(default=None, description="Typical operating speed range in km/h [min, max]")
    urban_rural: Optional[List[str]] = Field(default=None, description="urban, rural")
    co_benefits: Optional[List[str]] = Field(default=None, description="Additional benefits like traffic calming, accessibility")
    references: List[Reference] = Field(default_factory=list, description="Evidence sources and citations")
    tags: List[str] = Field(default_factory=list, description="Keywords for matching")

# Add your own schemas here:
# --------------------------------------------------

# Note: The Flames database viewer will automatically:
# 1. Read these schemas from GET /schema endpoint
# 2. Use them for document validation when creating/editing
# 3. Handle all database operations (CRUD) directly
# 4. You don't need to create any database endpoints!
