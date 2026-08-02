from abc import ABC, abstractmethod
from typing import Any


class BillingProvider(ABC):
    @abstractmethod
    def create_customer(self, payload: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def create_checkout(self, payload: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def get_subscription(self, provider_subscription_id: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def cancel_subscription(self, provider_subscription_id: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def reactivate_subscription(self, provider_subscription_id: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def handle_webhook(self, payload: dict) -> dict:
        raise NotImplementedError


class NoopBillingProvider(BillingProvider):
    def _not_configured(self) -> None:
        raise RuntimeError("Nenhum provedor de cobrança está configurado.")

    def create_customer(self, payload: dict) -> dict:
        self._not_configured()

    def create_checkout(self, payload: dict) -> dict:
        self._not_configured()

    def get_subscription(self, provider_subscription_id: str) -> dict:
        self._not_configured()

    def cancel_subscription(self, provider_subscription_id: str) -> dict:
        self._not_configured()

    def reactivate_subscription(self, provider_subscription_id: str) -> dict:
        self._not_configured()

    def handle_webhook(self, payload: dict) -> dict:
        self._not_configured()
