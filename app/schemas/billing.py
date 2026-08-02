from typing import Any

from pydantic import BaseModel, Field


class PlanSummary(BaseModel):
    id: str
    code: str
    name: str
    description: str | None = None
    status: str
    billingInterval: str
    priceCents: int
    pricingMode: str
    currency: str
    trialDays: int
    sortOrder: int
    isPublic: bool


class PlanDetail(PlanSummary):
    limits: dict[str, Any] = Field(default_factory=dict)
    features: dict[str, Any] = Field(default_factory=dict)


class SubscriptionSummary(BaseModel):
    id: str
    workspaceId: str
    status: str
    effectiveStatus: str
    planCode: str
    planName: str
    billingInterval: str
    currency: str
    unitAmountCents: int
    trialStartedAt: str | None = None
    trialEndsAt: str | None = None
    currentPeriodStartedAt: str | None = None
    currentPeriodEndsAt: str | None = None
    cancelAtPeriodEnd: bool


class SubscriptionStatus(BaseModel):
    status: str
    effectiveStatus: str
    subscriptionState: str


class UsageSummary(BaseModel):
    values: dict[str, int] = Field(default_factory=dict)
    periodKey: str


class SubscriptionEntitlements(BaseModel):
    features: dict[str, Any] = Field(default_factory=dict)
    limits: dict[str, Any] = Field(default_factory=dict)
    usage: UsageSummary


class BillingOverview(BaseModel):
    subscription: SubscriptionSummary | None = None
    subscriptionState: str
    plan: PlanDetail | None = None
    entitlements: SubscriptionEntitlements


class SelectPlanRequest(BaseModel):
    planCode: str = Field(min_length=1, max_length=80)
    billingInterval: str = "monthly"


class PlanCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    status: str = "active"
    billingInterval: str = "monthly"
    priceCents: int = Field(default=0, ge=0)
    pricingMode: str = "contact_sales"
    currency: str = "BRL"
    trialDays: int = Field(default=0, ge=0)
    limits: dict[str, Any] = Field(default_factory=dict)
    features: dict[str, Any] = Field(default_factory=dict)
    sortOrder: int = 0
    isPublic: bool = True


class PlanUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    billingInterval: str | None = None
    priceCents: int | None = Field(default=None, ge=0)
    pricingMode: str | None = None
    currency: str | None = None
    trialDays: int | None = Field(default=None, ge=0)
    limits: dict[str, Any] | None = None
    features: dict[str, Any] | None = None
    sortOrder: int | None = None
    isPublic: bool | None = None
