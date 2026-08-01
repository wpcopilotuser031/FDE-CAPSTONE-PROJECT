from pydantic import BaseModel, Field


class RecommendationRequest(BaseModel):
    patient_id: str = Field(..., description="Unique patient identifier")
    diagnosis: str = Field(..., description="Clinical diagnosis or condition")
    location: str = Field(..., description="Patient preferred location, city/state")
    insurance_plan: str = Field(..., description="Insurance plan or payer network")
    max_results: int = Field(5, ge=1, le=10)
    urgency: str = Field("Routine", description="Clinical urgency level: Routine, Priority, or Urgent")
    preferred_window_days: int = Field(7, ge=1, le=90, description="Maximum acceptable days until first available appointment")


class SpecialistRecommendation(BaseModel):
    provider_id: str
    provider_name: str
    specialty: str
    location: str
    accepts_insurance: bool
    next_available_date: str
    score: float
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    rationale: str
    exceeded_wait_window: bool = False


class RecommendationDecisionTrace(BaseModel):
    capability: str
    caller_role: str
    mcp_enabled: bool
    tools_invoked: list[str]
    human_review_required: bool


class RecommendationResponse(BaseModel):
    request_id: str
    generated_at: str | None = None
    inferred_specialties: list[str]
    recommendations: list[SpecialistRecommendation]
    missing_information: list[str] = Field(default_factory=list)
    llm_used: bool = False
    decision_trace: RecommendationDecisionTrace | None = None
