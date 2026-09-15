ALTER TABLE public.mensagens ADD COLUMN IF NOT EXISTS media_type TEXT;
ALTER TABLE public.mensagens ADD COLUMN IF NOT EXISTS media_filename TEXT;
ALTER TABLE public.mensagens ADD COLUMN IF NOT EXISTS media_content_type TEXT;
ALTER TABLE public.mensagens ADD COLUMN IF NOT EXISTS media_storage_path TEXT;
ALTER TABLE public.mensagens ADD COLUMN IF NOT EXISTS media_byte_size INTEGER;

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'conversation-media', 'conversation-media', false, 16777216,
  ARRAY[
    'image/jpeg', 'image/png', 'image/webp',
    'audio/aac', 'audio/mp4', 'audio/mpeg', 'audio/ogg', 'audio/amr',
    'application/pdf', 'text/plain',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  ]
)
ON CONFLICT (id) DO NOTHING;
