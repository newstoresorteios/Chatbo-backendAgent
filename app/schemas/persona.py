from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PersonaExample(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    customerMessage: str = Field(default="", max_length=4000, alias="customer_message")
    expectedResponse: str = Field(default="", max_length=8000, alias="expected_response")


class AgentPersonaEditable(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(default=None, max_length=200)
    role: str | None = Field(default=None, max_length=200)
    segment: str | None = Field(default=None, max_length=200)
    language: str | None = Field(default="pt-BR", max_length=40)
    tone: str | None = Field(default=None, max_length=80)
    toneDetails: str | None = Field(default=None, max_length=8000)
    greeting: str | None = Field(default=None, max_length=8000)
    introduction: str | None = Field(default=None, max_length=12000)
    customerAddressStyle: str | None = Field(default=None, max_length=4000)
    closingMessage: str | None = Field(default=None, max_length=8000)
    targetAudience: str | None = Field(default=None, max_length=8000)
    customerProfile: str | None = Field(default=None, max_length=8000)
    salesGoals: list[str] = Field(default_factory=list, max_length=100)
    qualificationRules: list[str] = Field(default_factory=list, max_length=100)
    opportunityCriteria: list[str] = Field(default_factory=list, max_length=100)
    humanHandoffCriteria: list[str] = Field(default_factory=list, max_length=100)
    objectionHandling: dict[str, Any] = Field(default_factory=dict)
    upsellRules: list[str] = Field(default_factory=list, max_length=100)
    recommendationRules: list[str] = Field(default_factory=list, max_length=100)
    escalationRules: list[str] = Field(default_factory=list, max_length=100)
    restrictions: list[str] = Field(default_factory=list, max_length=100)
    examples: list[PersonaExample] = Field(default_factory=list, max_length=40)


class AgentPersonaCreate(AgentPersonaEditable):
    pass


class AgentPersonaUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(default=None, max_length=200)
    role: str | None = Field(default=None, max_length=200)
    segment: str | None = Field(default=None, max_length=200)
    language: str | None = Field(default=None, max_length=40)
    tone: str | None = Field(default=None, max_length=80)
    toneDetails: str | None = Field(default=None, max_length=8000)
    greeting: str | None = Field(default=None, max_length=8000)
    introduction: str | None = Field(default=None, max_length=12000)
    customerAddressStyle: str | None = Field(default=None, max_length=4000)
    closingMessage: str | None = Field(default=None, max_length=8000)
    targetAudience: str | None = Field(default=None, max_length=8000)
    customerProfile: str | None = Field(default=None, max_length=8000)
    salesGoals: list[str] | None = Field(default=None, max_length=100)
    qualificationRules: list[str] | None = Field(default=None, max_length=100)
    opportunityCriteria: list[str] | None = Field(default=None, max_length=100)
    humanHandoffCriteria: list[str] | None = Field(default=None, max_length=100)
    objectionHandling: dict[str, Any] | None = None
    upsellRules: list[str] | None = Field(default=None, max_length=100)
    recommendationRules: list[str] | None = Field(default=None, max_length=100)
    escalationRules: list[str] | None = Field(default=None, max_length=100)
    restrictions: list[str] | None = Field(default=None, max_length=100)
    examples: list[PersonaExample] | None = Field(default=None, max_length=40)


class AgentPersonaResponse(AgentPersonaEditable):
    id: str
    workspaceId: str
    status: str
    version: int
    createdAt: str | None = None
    updatedAt: str | None = None
    activatedAt: str | None = None
    deactivatedAt: str | None = None


class AgentPersonaListResponse(BaseModel):
    items: list[AgentPersonaResponse]
    total: int
    activePersonaId: str | None = None


class PersonaVersionResponse(BaseModel):
    id: str
    personaId: str
    version: int
    snapshot: dict[str, Any]
    changeType: str
    createdBy: str | None = None
    createdAt: str | None = None


class PersonaTestRequest(BaseModel):
    persona: AgentPersonaEditable
    customerMessage: str = Field(min_length=1, max_length=4000)
    optionalContext: dict[str, Any] | None = None


class PersonaTestResponse(BaseModel):
    response: str
    warnings: list[str] = Field(default_factory=list)
    generatedAt: str
    persisted: bool = False
    activated: bool = False
