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


class AgentConfigurationPublish(BaseModel):
    expectedVersion: int = Field(ge=0)
    values: dict[str, str | int | float | bool]
