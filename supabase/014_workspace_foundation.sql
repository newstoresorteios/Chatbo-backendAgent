-- Etapa 14: fundacao de workspaces, settings empresariais e onboarding
-- Execute no Supabase SQL Editor

ALTER TABLE public.usuarios
  ADD COLUMN IF NOT EXISTS account_type TEXT NOT NULL DEFAULT 'workspace_user';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'usuarios_account_type_check'
  ) THEN
    ALTER TABLE public.usuarios
      ADD CONSTRAINT usuarios_account_type_check
      CHECK (account_type IN ('workspace_user', 'system_admin'));
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.workspaces (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  brand_name TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT workspaces_status_check CHECK (status IN ('active', 'inactive'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_workspaces_name_lower
  ON public.workspaces (lower(name));

CREATE TABLE IF NOT EXISTS public.workspace_members (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'member',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT workspace_members_role_check CHECK (role IN ('owner', 'admin', 'supervisor', 'seller', 'member')),
  CONSTRAINT workspace_members_status_check CHECK (status IN ('active', 'inactive')),
  CONSTRAINT workspace_members_workspace_user_unique UNIQUE (workspace_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_members_workspace_id
  ON public.workspace_members(workspace_id);

CREATE INDEX IF NOT EXISTS idx_workspace_members_user_id
  ON public.workspace_members(user_id);

CREATE TABLE IF NOT EXISTS public.workspace_settings (
  workspace_id UUID PRIMARY KEY REFERENCES public.workspaces(id) ON DELETE CASCADE,
  segment TEXT,
  website TEXT,
  country TEXT,
  currency TEXT DEFAULT 'BRL',
  sales_model TEXT,
  sales_channels JSONB NOT NULL DEFAULT '[]'::jsonb,
  business_hours TEXT,
  primary_contact TEXT,
  agent_display_name TEXT,
  agent_role TEXT,
  agent_language TEXT,
  agent_primary_channel TEXT,
  cnpj TEXT,
  phone TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT workspace_settings_sales_model_check CHECK (
    sales_model IS NULL OR sales_model IN ('b2b', 'b2c', 'mixed')
  )
);

CREATE TABLE IF NOT EXISTS public.workspace_onboarding (
  workspace_id UUID PRIMARY KEY REFERENCES public.workspaces(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending',
  current_step TEXT,
  completed_steps JSONB NOT NULL DEFAULT '[]'::jsonb,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT workspace_onboarding_status_check CHECK (status IN ('pending', 'in_progress', 'complete'))
);

WITH legacy_companies AS (
  SELECT DISTINCT
    COALESCE(
      NULLIF(trim(u.empresa), ''),
      NULLIF((SELECT trim(nome) FROM public.empresa_config WHERE id = 'default' LIMIT 1), ''),
      'PulseDesk'
    ) AS company_name
  FROM public.usuarios u
),
legacy_workspaces AS (
  SELECT
    (
      substr(md5('legacy-workspace:' || company_name), 1, 8) || '-' ||
      substr(md5('legacy-workspace:' || company_name), 9, 4) || '-' ||
      substr(md5('legacy-workspace:' || company_name), 13, 4) || '-' ||
      substr(md5('legacy-workspace:' || company_name), 17, 4) || '-' ||
      substr(md5('legacy-workspace:' || company_name), 21, 12)
    )::uuid AS workspace_id,
    company_name
  FROM legacy_companies
)
INSERT INTO public.workspaces (id, name, status)
SELECT workspace_id, company_name, 'active'
FROM legacy_workspaces
ON CONFLICT (id) DO NOTHING;

WITH user_company AS (
  SELECT
    u.id AS user_id,
    u.perfil,
    COALESCE(
      NULLIF(trim(u.empresa), ''),
      NULLIF((SELECT trim(nome) FROM public.empresa_config WHERE id = 'default' LIMIT 1), ''),
      'PulseDesk'
    ) AS company_name,
    ROW_NUMBER() OVER (
      PARTITION BY COALESCE(
        NULLIF(trim(u.empresa), ''),
        NULLIF((SELECT trim(nome) FROM public.empresa_config WHERE id = 'default' LIMIT 1), ''),
        'PulseDesk'
      ), u.perfil
      ORDER BY u.created_at NULLS LAST, u.id
    ) AS role_order
  FROM public.usuarios u
),
member_rows AS (
  SELECT
    (
      substr(md5('legacy-workspace:' || company_name), 1, 8) || '-' ||
      substr(md5('legacy-workspace:' || company_name), 9, 4) || '-' ||
      substr(md5('legacy-workspace:' || company_name), 13, 4) || '-' ||
      substr(md5('legacy-workspace:' || company_name), 17, 4) || '-' ||
      substr(md5('legacy-workspace:' || company_name), 21, 12)
    )::uuid AS workspace_id,
    user_id,
    CASE
      WHEN perfil = 'admin' AND role_order = 1 THEN 'owner'
      WHEN perfil = 'admin' THEN 'admin'
      WHEN perfil = 'supervisor' THEN 'supervisor'
      WHEN perfil = 'vendedor' THEN 'seller'
      ELSE 'member'
    END AS workspace_role
  FROM user_company
)
INSERT INTO public.workspace_members (workspace_id, user_id, role, status)
SELECT workspace_id, user_id, workspace_role, 'active'
FROM member_rows
ON CONFLICT (workspace_id, user_id) DO NOTHING;

INSERT INTO public.workspace_settings (workspace_id, cnpj, primary_contact, phone, currency)
SELECT w.id, ec.cnpj, ec.email, ec.telefone, 'BRL'
FROM public.workspaces w
CROSS JOIN LATERAL (
  SELECT cnpj, email, telefone FROM public.empresa_config WHERE id = 'default' LIMIT 1
) ec
WHERE NOT EXISTS (
  SELECT 1 FROM public.workspace_settings ws WHERE ws.workspace_id = w.id
);

INSERT INTO public.workspace_onboarding (workspace_id, status, current_step, completed_steps, completed_at)
SELECT w.id, 'complete', 'activation', '["business","operation","catalog","channels","persona","test","activation"]'::jsonb, NOW()
FROM public.workspaces w
WHERE NOT EXISTS (
  SELECT 1 FROM public.workspace_onboarding wo WHERE wo.workspace_id = w.id
);
