from pydantic import BaseModel, ConfigDict, Field, model_validator


class MercosClienteCreate(BaseModel):
    """Payload mínimo para POST/PUT de cliente no Mercos."""

    model_config = ConfigDict(extra="allow")

    nome: str | None = Field(default=None, min_length=1, max_length=200)
    razao_social: str | None = Field(default=None, min_length=1, max_length=200)
    cnpj: str | None = Field(default=None, max_length=18)
    inscricao_estadual: str | None = None
    email: str | None = None
    telefone: str | None = None
    celular: str | None = None
    endereco: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    estado: str | None = Field(default=None, max_length=2)
    cep: str | None = None
    ativo: bool | None = None

    @model_validator(mode="after")
    def exigir_nome_ou_razao(self):
        if not (self.nome or self.razao_social):
            raise ValueError("Informe nome ou razao_social")
        return self


class MercosProdutoCreate(BaseModel):
    """Payload mínimo para POST de produto no Mercos."""

    model_config = ConfigDict(extra="allow")

    nome: str = Field(min_length=1, max_length=200)
    codigo: str | None = Field(default=None, max_length=100)
    unidade: str | None = None
    preco_tabela: float | None = Field(default=None, ge=0)
    preco_minimo: float | None = Field(default=None, ge=0)
    saldo_estoque: float | None = None
    ativo: bool | None = True
    observacoes: str | None = None


class MercosPedidoItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    produto_id: int
    quantidade: float = Field(gt=0)
    preco_tabela: float | None = Field(default=None, ge=0)
    id: int | None = None


class MercosPedidoCreate(BaseModel):
    """Payload mínimo para POST/PUT de pedido (API v2)."""

    model_config = ConfigDict(extra="allow")

    cliente_id: int
    itens: list[MercosPedidoItem] = Field(min_length=1)
    data_emissao: str | None = None
    condicao_pagamento: str | None = None
    observacoes: str | None = None
    transportadora_id: int | None = None
    tipo_pedido_id: int | None = None


class MercosTituloCreate(BaseModel):
    """Payload mínimo para POST/PUT de título no Mercos."""

    model_config = ConfigDict(extra="allow")

    cliente_id: int
    valor: float = Field(gt=0)
    data_vencimento: str | None = None
    data_emissao: str | None = None
    observacoes: str | None = None
    pedido_id: int | None = None
    forma_pagamento: str | None = None
