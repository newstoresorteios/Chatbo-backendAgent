from typing import Any

from pydantic import BaseModel, Field


class PersonaExample(BaseModel):
    customerMessage: str = Field(min_length=1, max_length=2000)
    expectedResponse: str = Field(min_length=1, max_length=4000)


class AgentPersonaEditable(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, max_length=160)
    segment: str | None = Field(default=None, max_length=160)
    language: str | None = Field(default="pt-BR", max_length=20)
    tone: str | None = Field(default=None, max_length=80)
    toneDetails: str | None = Field(default=None, max_length=2000)
    greeting: str | None = Field(default=None, max_length=2000)
    introduction: str | None = Field(default=None, max_length=4000)
    customerAddressStyle: str | None = Field(default=None, max_length=120)
    closingMessage: str | None = Field(default=None, max_length=2000)
    targetAudience: str | None = Field(default=None, max_length=2000)
    customerProfile: str | None = Field(default=None, max_length=2000)
    salesGoals: list[str] = Field(default_factory=list, max_length=20)
    qualificationRules: list[str] = Field(default_factory=list, max_length=30)
    opportunityCriteria: list[str] = Field(default_factory=list, max_length=30)
    humanHandoffCriteria: list[str] = Field(default_factory=list, max_length=30)
    objectionHandling: dict[str, Any] = Field(default_factory=dict)
    upsellRules: list[str] = Field(default_factory=list, max_length=30)
    recommendationRules: list[str] = Field(default_factory=list, max_length=30)
    escalationRules: list[str] = Field(default_factory=list, max_length=30)
    restrictions: list[str] = Field(default_factory=list, max_length=30)
    examples: list[PersonaExample] = Field(default_factory=list, max_length=20)


class AgentPersonaCreate(AgentPersonaEditable):
    pass


class AgentPersonaUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, max_length=160)
    segment: str | None = Field(default=None, max_length=160)
    language: str | None = Field(default=None, max_length=20)
    tone: str | None = Field(default=None, max_length=80)
    toneDetails: str | None = Field(default=None, max_length=2000)
    greeting: str | None = Field(default=None, max_length=2000)
    introduction: str | None = Field(default=None, max_length=4000)
    customerAddressStyle: str | None = Field(default=None, max_length=120)
    closingMessage: str | None = Field(default=None, max_length=2000)
    targetAudience: str | None = Field(default=None, max_length=2000)
    customerProfile: str | None = Field(default=None, max_length=2000)
    salesGoals: list[str] | None = Field(default=None, max_length=20)
    qualificationRules: list[str] | None = Field(default=None, max_length=30)
    opportunityCriteria: list[str] | None = Field(default=None, max_length=30)
    humanHandoffCriteria: list[str] | None = Field(default=None, max_length=30)
    objectionHandling: dict[str, Any] | None = None
    upsellRules: list[str] | None = Field(default=None, max_length=30)
    recommendationRules: list[str] | None = Field(default=None, max_length=30)
    escalationRules: list[str] | None = Field(default=None, max_length=30)
    restrictions: list[str] | None = Field(default=None, max_length=30)
    examples: list[PersonaExample] | None = Field(default=None, max_length=20)


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
