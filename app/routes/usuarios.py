from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.auth import obter_token_payload, obter_usuario_atual
from app.services.usuario_service import usuario_service

router = APIRouter()


class CreateUsuarioRequest(BaseModel):
    name: str = Field(min_length=2)
    email: str
    password: str = Field(min_length=6)
    role: str = "user"
    company: str | None = None


class UpdateUsuarioRequest(BaseModel):
    name: str | None = None
    role: str | None = None
    active: bool | None = None
    company: str | None = None


@router.get("/usuarios")
def listar_usuarios(usuario: dict = Depends(obter_usuario_atual)):
    return usuario_service.listar(usuario)


@router.post("/usuarios")
def criar_usuario(
    body: CreateUsuarioRequest,
    usuario: dict = Depends(obter_usuario_atual),
):
    return usuario_service.criar(
        name=body.name,
        email=body.email,
        password=body.password,
        role=body.role,
        company=body.company,
        actor=usuario,
    )


@router.patch("/usuarios/{usuario_id}")
def atualizar_usuario(
    usuario_id: str,
    body: UpdateUsuarioRequest,
    usuario: dict = Depends(obter_usuario_atual),
):
    return usuario_service.atualizar(
        usuario_id,
        actor_id=str(usuario.get("id")),
        actor_role=usuario.get("perfil") or "user",
        actor=usuario,
        name=body.name,
        role=body.role,
        active=body.active,
        company=body.company,
    )
