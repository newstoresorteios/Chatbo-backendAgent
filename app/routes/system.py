from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.auth import requer_admin, verificar_token
from app.core.billing_permissions import requer_system_admin
from app.repositories.workspace_repository import WorkspaceRepository
from app.services.billing_service import billing_service
from app.services.demo_cleanup_service import limpar_demo
from app.services.system_companies_service import system_companies_service
from app.services.system_status_service import system_status_service

router = APIRouter()
workspace_repository = WorkspaceRepository()


class LimparDemoRequest(BaseModel):
    incluirMercos: bool = False


class CreateCompanyRequest(BaseModel):
    name: str = Field(min_length=2)
    brandName: str | None = None


class UpdateCompanyRequest(BaseModel):
    name: str | None = None
    brandName: str | None = None
    status: str | None = None


class CreateCompanyAdminRequest(BaseModel):
    name: str = Field(min_length=2)
    email: str
    password: str = Field(min_length=6)
    role: str = "admin"


@router.get("/sistema/status")
def get_system_status(autorizado=Depends(verificar_token)):
    return system_status_service.get_status()


@router.post("/sistema/limpar-demo")
def limpar_dados_demo(body: LimparDemoRequest | None = None, _: dict = Depends(requer_admin)):
    return limpar_demo(incluir_mercos=bool(body and body.incluirMercos))


@router.get("/system/workspaces")
def listar_workspaces_globais(_: dict = Depends(requer_system_admin)):
    return {"items": system_companies_service.listar_empresas()}


@router.get("/system/companies")
def listar_empresas(_: dict = Depends(requer_system_admin)):
    return {"items": system_companies_service.listar_empresas()}


@router.post("/system/companies")
def criar_empresa(body: CreateCompanyRequest, _: dict = Depends(requer_system_admin)):
    return system_companies_service.criar_empresa(name=body.name, brand_name=body.brandName)


@router.get("/system/companies/{company_id}")
def obter_empresa(company_id: str, _: dict = Depends(requer_system_admin)):
    return system_companies_service.obter_empresa(company_id)


@router.patch("/system/companies/{company_id}")
def atualizar_empresa(
    company_id: str,
    body: UpdateCompanyRequest,
    _: dict = Depends(requer_system_admin),
):
    return system_companies_service.atualizar_empresa(
        company_id,
        name=body.name,
        brand_name=body.brandName,
        status=body.status,
    )


@router.get("/system/companies/{company_id}/members")
def listar_membros_empresa(company_id: str, _: dict = Depends(requer_system_admin)):
    return {"items": system_companies_service.listar_membros(company_id)}


@router.post("/system/companies/{company_id}/admins")
def criar_admin_empresa(
    company_id: str,
    body: CreateCompanyAdminRequest,
    _: dict = Depends(requer_system_admin),
):
    return system_companies_service.criar_admin_empresa(
        company_id,
        name=body.name,
        email=body.email,
        password=body.password,
        role=body.role,
    )


@router.get("/system/uso")
def listar_uso_global(_: dict = Depends(requer_system_admin)):
    return {"items": billing_service.repo.listar_uso()}
