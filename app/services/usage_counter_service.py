from fastapi import HTTPException

from app.services.billing_service import BillingService


class UsageCounterService:
    """Ponto único para validar e registrar consumo sujeito a entitlement."""

    def __init__(self, billing: BillingService | None = None):
        self.billing = billing

    def consume(self, workspace_id: str, metric: str, amount: int = 1) -> dict:
        if amount < 1:
            raise HTTPException(status_code=422, detail="Quantidade de uso inválida.")
        billing = self.billing
        if billing is None:
            from app.services.billing_service import billing_service
            billing = billing_service
        return billing.consume_usage(workspace_id, metric, amount)
