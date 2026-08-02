from pydantic import BaseModel


class CatalogProduct(BaseModel):
    productId: str
    name: str
    description: str | None = None
    price: float | None = None
    currency: str = "BRL"
    availability: str | None = None
    stockStatus: str = "unknown"
    category: str | None = None
    source: str = "catalog"
    updatedAt: str | None = None


class CatalogPage(BaseModel):
    items: list[CatalogProduct]
    page: int
    limit: int
    hasNext: bool
