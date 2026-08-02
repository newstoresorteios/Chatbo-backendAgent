import ssl

import httpx
from supabase import Client, ClientOptions, create_client

from app.config.settings import SUPABASE_KEY, SUPABASE_URL

_client: Client | None = None


def _ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if hasattr(ssl, "enum_certificates"):
        for store_name in ("ROOT", "CA"):
            try:
                for cert, encoding, _trust in ssl.enum_certificates(store_name):
                    if encoding != "x509_asn":
                        continue
                    try:
                        context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(cert))
                    except Exception:
                        pass
            except Exception:
                pass
    return context


def _http_client() -> httpx.Client:
    return httpx.Client(
        verify=_ssl_context(),
        trust_env=False,
        timeout=120.0,
    )


def get_supabase() -> Client:
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError(
                "SUPABASE_URL e SUPABASE_KEY devem estar configurados (Render -> Environment)."
            )
        _client = create_client(SUPABASE_URL, SUPABASE_KEY, ClientOptions(httpx_client=_http_client()))
    return _client


class _SupabaseProxy:
    def __getattr__(self, name: str):
        return getattr(get_supabase(), name)


supabase = _SupabaseProxy()
