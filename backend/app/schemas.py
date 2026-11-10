import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class GoogleIn(BaseModel):
    credential: str = Field(min_length=20)


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    name: str
    avatar_url: str | None = None
    has_password: bool
    created_at: datetime


class DetectionOut(BaseModel):
    index: int
    class_id: int
    class_name: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float


class TileOut(BaseModel):
    index: int
    colony_count: int
    mean_confidence: float | None
    width: int | None
    height: int | None
    annotated_url: str
    original_url: str | None
    detections: list[DetectionOut]


class AnalysisOut(BaseModel):
    id: uuid.UUID
    title: str
    notes: str
    organism: str
    mode: str
    layout: str | None
    rows: int
    cols: int
    file_count: int
    confidence: float
    imgsz: int
    status: str
    progress: int
    progress_message: str
    colony_count: int | None
    mean_confidence: float | None
    error: str | None
    detector_label: str | None
    created_at: datetime
    completed_at: datetime | None
    duration_ms: int | None
    operator: str
    annotated_url: str | None
    original_url: str | None
    tiles: list[TileOut]


class AnalysisListItem(BaseModel):
    id: uuid.UUID
    title: str
    organism: str
    mode: str
    layout: str | None
    rows: int
    cols: int
    file_count: int
    status: str
    progress: int
    colony_count: int | None
    created_at: datetime
    thumb_url: str | None


class AnalysisList(BaseModel):
    items: list[AnalysisListItem]
    total: int


class CreatedOut(BaseModel):
    id: uuid.UUID
    status: str


class DashboardOut(BaseModel):
    analyses: int
    colonies: int
    mean_colonies: float | None
    processing: int
    recent: list[AnalysisListItem]
