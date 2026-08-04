from pydantic import BaseModel, Field


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


class WorkspaceAgentUpdate(BaseModel):
    agentType: str | None = None
    status: str | None = Field(default=None, pattern="^(active|inactive|provisioning|error)$")
    displayName: str | None = None
    configuration: dict | None = None
