-- Keep conversation attachments private and retain the existing size limit.
-- Only extend the accepted formats; do not change policies or existing objects.
UPDATE storage.buckets
SET allowed_mime_types = ARRAY(
    SELECT DISTINCT mime
    FROM unnest(allowed_mime_types || ARRAY[
        'image/gif', 'video/mp4', 'video/quicktime', 'video/webm'
    ]) AS formats(mime)
    ORDER BY mime
)
WHERE id = 'conversation-media'
  AND public = false
  AND allowed_mime_types IS NOT NULL;
