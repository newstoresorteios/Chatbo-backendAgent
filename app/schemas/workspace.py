from pydantic import BaseModel, Field


class WorkspaceSettingsResponse(BaseModel):
    segment: str | None = None
    website: str | None = None
    country: str | None = None
    currency: str | None = None
    salesModel: str | None = None
    salesChannels: list[str] = Field(default_factory=list)
    businessHours: str | None = None
    primaryContact: str | None = None
    agentDisplayName: str | None = None
    agentRole: str | None = None
    agentLanguage: str | None = None
    agentPrimaryChannel: str | None = None


class WorkspaceSettingsUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2)
    brandName: str | None = None
    cnpj: str | None = None
    email: str | None = None
    phone: str | None = None
    segment: str | None = None
    website: str | None = None
    country: str | None = None
    currency: str | None = None
    salesModel: str | None = None
    salesChannels: list[str] | None = None
    businessHours: str | None = None
    primaryContact: str | None = None
    agentDisplayName: str | None = None
    agentRole: str | None = None
    agentLanguage: str | None = None
    agentPrimaryChannel: str | None = None


class WorkspaceContext(BaseModel):
    workspaceId: str
    workspaceName: str
    workspaceRole: str
    onboardingStatus: str
    accountType: str = "workspace_user"


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    brandName: str | None = None
    role: str
    status: str
    accountType: str
    onboardingStatus: str
    settings: WorkspaceSettingsResponse


class OnboardingResponse(BaseModel):
    status: str
    currentStep: str | None = None
    completedSteps: list[str] = Field(default_factory=list)
    startedAt: str | None = None
    completedAt: str | None = None


class OnboardingUpdate(BaseModel):
    currentStep: str | None = None
    completedSteps: list[str] | None = None
    status: str | None = None


class OnboardingTestRequest(BaseModel):
    inputText: str = Field(min_length=1, max_length=4000)


class WorkspaceChannelUpdate(BaseModel):
    channelType: str
    status: str = "configured"
    configuration: dict = Field(default_factory=dict)
