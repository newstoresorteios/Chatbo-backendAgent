from typing import Any, TypeAlias

from pydantic import BaseModel, Field


RuntimeRule: TypeAlias = str | dict[str, Any]


class PersonaRuntimeExample(BaseModel):
    customerMessage: str
    expectedResponse: str


class ActivePersonaRuntime(BaseModel):
    personaId: str
    workspaceId: str
    version: int
    name: str | None = None
    role: str | None = None
    language: str | None = None
    tone: str | None = None
    greeting: str | None = None
    introduction: str | None = None
    customerAddressStyle: str | None = None
    closingMessage: str | None = None
    targetAudience: str | None = None
    customerProfile: str | None = None
    salesGoals: list[RuntimeRule] = Field(default_factory=list)
    qualificationRules: list[RuntimeRule] = Field(default_factory=list)
    opportunityCriteria: list[RuntimeRule] = Field(default_factory=list)
    objectionHandling: dict[str, Any] = Field(default_factory=dict)
    upsellRules: list[RuntimeRule] = Field(default_factory=list)
    recommendationRules: list[RuntimeRule] = Field(default_factory=list)
    humanHandoffCriteria: list[RuntimeRule] = Field(default_factory=list)
    escalationRules: list[RuntimeRule] = Field(default_factory=list)
    restrictions: list[RuntimeRule] = Field(default_factory=list)
    examples: list[PersonaRuntimeExample] = Field(default_factory=list)
    activatedAt: str | None = None
    updatedAt: str | None = None
