-- Etapa 17: fundação de planos e assinaturas SaaS do NITRUS
-- Execute no Supabase SQL Editor depois da etapa 16.

CREATE TABLE IF NOT EXISTS public.saas_plans (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  billing_interval TEXT NOT NULL DEFAULT 'monthly',
  price_cents INTEGER NOT NULL DEFAULT 0,
  pricing_mode TEXT NOT NULL DEFAULT 'contact_sales',
  currency TEXT NOT NULL DEFAULT 'BRL',
  trial_days INTEGER NOT NULL DEFAULT 0,
  limits JSONB NOT NULL DEFAULT '{}'::jsonb,
  features JSONB NOT NULL DEFAULT '{}'::jsonb,
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_public BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT saas_plans_status_check CHECK (status IN ('active', 'inactive', 'archived')),
  CONSTRAINT saas_plans_interval_check CHECK (billing_interval IN ('monthly', 'yearly')),
  CONSTRAINT saas_plans_pricing_mode_check CHECK (pricing_mode IN ('fixed', 'contact_sales')),
  CONSTRAINT saas_plans_price_check CHECK (price_cents >= 0),
  CONSTRAINT saas_plans_trial_check CHECK (trial_days >= 0)
);

CREATE TABLE IF NOT EXISTS public.workspace_subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  plan_id UUID NOT NULL REFERENCES public.saas_plans(id),
  status TEXT NOT NULL,
  billing_interval TEXT NOT NULL,
  currency TEXT NOT NULL,
  unit_amount_cents INTEGER NOT NULL DEFAULT 0,
  trial_started_at TIMESTAMPTZ,
  trial_ends_at TIMESTAMPTZ,
  current_period_started_at TIMESTAMPTZ,
  current_period_ends_at TIMESTAMPTZ,
  cancel_at_period_end BOOLEAN NOT NULL DEFAULT false,
  canceled_at TIMESTAMPTZ,
  suspended_at TIMESTAMPTZ,
  provider TEXT,
  provider_customer_id TEXT,
  provider_subscription_id TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT workspace_subscriptions_status_check CHECK (status IN ('trialing', 'active', 'past_due', 'suspended', 'canceled', 'expired')),
  CONSTRAINT workspace_subscriptions_interval_check CHECK (billing_interval IN ('monthly', 'yearly')),
  CONSTRAINT workspace_subscriptions_amount_check CHECK (unit_amount_cents >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_workspace_subscriptions_current
  ON public.workspace_subscriptions(workspace_id)
  WHERE status IN ('trialing', 'active', 'past_due', 'suspended');

CREATE INDEX IF NOT EXISTS idx_workspace_subscriptions_workspace_id
  ON public.workspace_subscriptions(workspace_id);

CREATE TABLE IF NOT EXISTS public.workspace_subscription_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  subscription_id UUID REFERENCES public.workspace_subscriptions(id) ON DELETE SET NULL,
  event_type TEXT NOT NULL,
  previous_status TEXT,
  new_status TEXT,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workspace_subscription_events_workspace
  ON public.workspace_subscription_events(workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.workspace_usage_counters (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  metric TEXT NOT NULL,
  period_key TEXT NOT NULL,
  used_value BIGINT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT workspace_usage_counters_value_check CHECK (used_value >= 0),
  CONSTRAINT workspace_usage_counters_unique UNIQUE (workspace_id, metric, period_key)
);

CREATE INDEX IF NOT EXISTS idx_workspace_usage_counters_workspace_period
  ON public.workspace_usage_counters(workspace_id, period_key);

INSERT INTO public.saas_plans (
  code, name, description, status, billing_interval, price_cents, pricing_mode,
  currency, trial_days, limits, features, sort_order, is_public
)
VALUES
(
  'starter', 'Starter', 'Plano inicial com preço a configurar.', 'active', 'monthly', 0, 'contact_sales',
  'BRL', 14,
  '{"users": 3, "conversationsPerMonth": 500, "aiMessagesPerMonth": 1000, "activePersonas": 1, "channels": 1, "products": 500}'::jsonb,
  '{"webchat": true, "whatsapp": false, "mercos": false, "advancedReports": false, "automation": true, "prioritySupport": false}'::jsonb,
  1, true
),
(
  'professional', 'Professional', 'Plano profissional com preço a configurar.', 'active', 'monthly', 0, 'contact_sales',
  'BRL', 14,
  '{"users": 10, "conversationsPerMonth": 5000, "aiMessagesPerMonth": 10000, "activePersonas": 3, "channels": 3, "products": 5000}'::jsonb,
  '{"webchat": true, "whatsapp": true, "mercos": true, "advancedReports": true, "automation": true, "prioritySupport": false}'::jsonb,
  2, true
),
(
  'enterprise', 'Enterprise', 'Plano sob consulta comercial.', 'active', 'monthly', 0, 'contact_sales',
  'BRL', 0,
  '{"users": null, "conversationsPerMonth": null, "aiMessagesPerMonth": null, "activePersonas": null, "channels": null, "products": null}'::jsonb,
  '{"webchat": true, "whatsapp": true, "mercos": true, "advancedReports": true, "automation": true, "prioritySupport": true}'::jsonb,
  3, false
)
ON CONFLICT (code) DO NOTHING;

NOTIFY pgrst, 'reload schema';
