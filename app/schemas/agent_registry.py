from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentRuntimeType(BaseModel):
    code: str
    name: str
    baseRuntime: str
    description: str | None = None


class WorkspaceAgentResponse(BaseModel):
    id: str
    companyId: str
    workspaceId: str
    agentType: str
    baseRuntime: str
    status: str
    displayName: str | None = None
    configuration: dict = Field(default_factory=dict)
    configurationVersion: int = 0


class WorkspaceAgentUpdate(BaseModel):
    agentType: str | None = None
    status: str | None = Field(default=None, pattern="^(active|inactive|provisioning|error)$")
    displayName: str | None = None
    configuration: dict | None = None


class AgentRuntimeConfiguration(BaseModel):
    """Operational controls that are safe to expose to workspace operators."""

    model_config = ConfigDict(extra="forbid")

    maxReplyChars: int = Field(default=900, ge=300, le=4000)
    historyTurns: int = Field(default=12, ge=4, le=40)
    catalogShortlistSize: int = Field(default=3, ge=1, le=5)
    catalogCandidatePool: int = Field(default=20, ge=5, le=80)
    catalogRerankLimit: int = Field(default=15, ge=5, le=20)
    observabilityLevel: Literal["standard", "detailed"] = "standard"


class AgentConfigurationPublish(BaseModel):
    expectedVersion: int = Field(ge=0)
    values: AgentRuntimeConfiguration
