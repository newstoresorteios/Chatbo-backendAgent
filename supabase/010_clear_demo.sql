-- PulseDesk: limpar dados de demonstração (seed) no Supabase
-- Execute no SQL Editor APÓS backup, se necessário.
-- NÃO remove usuarios, settings, funil_estagios nem tokens de auth.

-- 1) Conversas demo (mensagens somem em cascata)
DELETE FROM public.conversas;

-- 2) Campanhas fictícias (Black Friday, etc.)
DELETE FROM public.campanhas
WHERE id IN ('cp1', 'cp2', 'cp3', 'cp4');

-- 3) Canais demo (Instagram, SMS fake, etc.)
DELETE FROM public.canais
WHERE id IN ('ch1', 'ch2', 'ch3', 'ch4', 'ch5', 'ch6', 'ch7');

-- 4) Robôs com métricas inventadas
DELETE FROM public.chatbot_fluxos
WHERE id IN ('bot1', 'bot2', 'bot3', 'bot4');

-- 5) Integrações fake (mantém Mercos)
DELETE FROM public.integracoes
WHERE id IN ('i1', 'i2', 'i3', 'i4', 'i5', 'i6', 'i7', 'i8');

-- 6) Negócios do funil (estágios s1–s5 permanecem)
DELETE FROM public.funil_negocios;

-- 7) OPCIONAL: zerar dados Mercos antigos antes de sync nova conta
-- DELETE FROM public.pedidos;
-- DELETE FROM public.clientes;
-- DELETE FROM public.produtos;

-- 8) Garantir entrada Mercos
INSERT INTO public.integracoes (id, name, category, connected)
VALUES ('mercos', 'Mercos', 'erp', false)
ON CONFLICT (id) DO UPDATE SET connected = false;
