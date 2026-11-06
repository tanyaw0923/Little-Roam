from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Literal
from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator

Province = Literal['AB','BC','ON','QC','MB','SK','NS','NB','NL','PE','YT','NT','NU']
ActivityType = Literal['any','indoor','outdoor']
Budget = Literal['any','free','paid']

class RecommendationRequest(BaseModel):
    city: str = Field(min_length=2, max_length=80)
    children_ages: list[int] = Field(min_length=1, max_length=8)
    interests: list[str] = Field(default_factory=list, max_length=12)
    activity_type: ActivityType = 'any'
    budget: Budget = 'any'
    search_scope: Literal['city', 'regional'] = 'city'
    postal_code: str | None = Field(default=None, max_length=8)
    visit_date: date | None = Field(default=None, description='Outing date (YYYY-MM-DD); defaults to today in Alberta. Forecast available up to 15 days ahead.')
    _resolved_origin: tuple[float,float] | None = PrivateAttr(default=None)
    max_drive_minutes: Literal[30, 60, 120] = 60
    max_results: int = Field(default=10, ge=1, le=10)

    @property
    def province(self) -> Province:
        """Internal province for the Alberta-only MVP; not a user input field."""
        return 'AB'

    @model_validator(mode='after')
    def ensure_regional_origin(self):
        today = datetime.now(ZoneInfo('America/Edmonton')).date()
        if self.visit_date is not None and not today <= self.visit_date <= today + timedelta(days=15):
            raise ValueError('visit_date must be today or within the next 15 days (Alberta local date)')
        if self.postal_code is not None:
            from .postal import normalize_postal_code
            self.postal_code = normalize_postal_code(self.postal_code)
            if self.search_scope != 'regional':
                raise ValueError('postal_code requires search_scope=regional')
            if self.province != 'AB' or not self.postal_code.startswith('T'):
                raise ValueError('Postal-code regional search currently supports Alberta postal codes')
        if self.search_scope == 'regional' and self.postal_code is None:
            from .geo import origin_for
            if origin_for(self.province, self.city) is None:
                raise ValueError('Regional search currently supports Calgary, Canmore, and Banff, AB as origins')
        return self

    @field_validator('children_ages')
    @classmethod
    def ages_valid(cls, ages):
        if any(age < 0 or age > 17 for age in ages):
            raise ValueError('Children ages must be between 0 and 17')
        return ages

class Candidate(BaseModel):
    place_id: str
    name: str
    address: str
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float | None = None
    drive_minutes: float | None = None
    weather_summary: str | None = None
    weather_source: str | None = None
    hours_status: Literal['open_now','closed_now','permanently_closed','unknown'] = 'unknown'
    hours_source_url: str | None = None
    hours_checked_at: str | None = None
    published_weekly_hours: list[str] = Field(default_factory=list)
    hours_for_visit_date: Literal['unknown'] = 'unknown'
    weather_score_adjustment: float = Field(default=0.0, exclude=True)
    google_maps_url: str | None = None
    website_url: str | None = None
    website_source: Literal['curated','google_places','unknown'] = 'unknown'
    official_source_url: str | None = None
    activity_type: ActivityType = 'any'
    categories: list[str] = Field(default_factory=list)
    price_category: Budget = 'any'
    min_age: int | None = None
    max_age: int | None = None
    google_place_id: str | None = None
    source: Literal['mock','google_places','curated']

class Recommendation(BaseModel):
    place_id: str
    name: str
    address: str
    google_maps_url: str | None
    website_url: str | None
    website_source: Literal['curated','google_places','unknown'] = 'unknown'
    official_source_url: str | None = None
    activity_type: ActivityType
    distance_km: float | None = None
    drive_minutes: float | None = None
    weather_summary: str | None = None
    weather_source: str | None = None
    hours_status: Literal['open_now','closed_now','permanently_closed','unknown'] = 'unknown'
    hours_source_url: str | None = None
    hours_checked_at: str | None = None
    hours_for_visit_date: Literal['unknown'] = 'unknown'
    admission_price_cad: float | None = None
    hours_verified: bool = False
    reason: str
    parent_tip: str
    source: str
    score: float

class RecommendationResponse(BaseModel):
    visit_date: date | None = None
    city: str
    province: Province
    mode: str
    count: int
    recommendations: list[Recommendation]
    warnings: list[str] = Field(default_factory=list)
