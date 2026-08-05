from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import requer_admin, verificar_token
from app.core.billing_permissions import requer_system_admin
from app.core.workspace_scope import obter_company_context, workspace_id_from_context
from app.repositories.workspace_repository import WorkspaceRepository
from app.services.billing_service import billing_service
from app.services.commercial_bi_service import commercial_bi_service
from app.services.demo_cleanup_service import limpar_demo
from app.services.system_companies_service import system_companies_service
from app.services.system_status_service import system_status_service
from app.services.workspace_integration_service import workspace_integration_service

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


class DataSourceRequest(BaseModel):
    provider: str = "tray"
    adapterBaseUrl: str = Field(min_length=8)
    adapterToken: str | None = None
    enabled: bool = True


class DataSourceTestRequest(BaseModel):
    adapterBaseUrl: str | None = None
    adapterToken: str | None = None


@router.get("/sistema/status")
def get_system_status(
    autorizado=Depends(verificar_token),
    context: dict = Depends(obter_company_context),
):
    return system_status_service.get_status(
        workspace_id=workspace_id_from_context(context),
    )


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


@router.get("/system/companies/{company_id}/data-source")
def obter_data_source(company_id: str, _: dict = Depends(requer_system_admin)):
    system_companies_service.obter_empresa(company_id)
    row = workspace_integration_service.get(company_id, "tray")
    return workspace_integration_service.public_view(row)


@router.put("/system/companies/{company_id}/data-source")
def salvar_data_source(
    company_id: str,
    body: DataSourceRequest,
    _: dict = Depends(requer_system_admin),
):
    system_companies_service.obter_empresa(company_id)
    if body.provider != "tray":
        raise HTTPException(status_code=400, detail="Somente provider=tray é suportado no MVP.")
    row = workspace_integration_service.upsert_tray(
        company_id,
        adapter_base_url=body.adapterBaseUrl,
        adapter_token=body.adapterToken,
        enabled=body.enabled,
    )
    return workspace_integration_service.public_view(row)


@router.post("/system/companies/{company_id}/data-source/test")
def testar_data_source(
    company_id: str,
    body: DataSourceTestRequest | None = None,
    _: dict = Depends(requer_system_admin),
):
    system_companies_service.obter_empresa(company_id)
    try:
        if body and body.adapterBaseUrl and body.adapterToken:
            return workspace_integration_service.test_connection(
                base_url=body.adapterBaseUrl,
                token=body.adapterToken,
            )
        return workspace_integration_service.test_connection(company_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/system/companies/{company_id}/commercial-bi/analyze")
def analisar_bi_empresa(
    company_id: str,
    usuario: dict = Depends(requer_system_admin),
):
    system_companies_service.obter_empresa(company_id)
    try:
        return commercial_bi_service.analyze(
            company_id,
            user_id=str(usuario.get("id")) if usuario.get("id") else None,
            period_days=30,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/system/uso")
def listar_uso_global(_: dict = Depends(requer_system_admin)):
    return {"items": billing_service.repo.listar_uso()}
