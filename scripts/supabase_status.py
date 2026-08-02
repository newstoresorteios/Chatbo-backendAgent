import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()
from app.services.supabase_service import supabase

tables = ['usuarios','clientes','produtos','pedidos','conversas','mensagens','campanhas','canais','chatbot_fluxos','integracoes','funil_negocios']
print('=== Supabase agora ===')
for t in tables:
    r = supabase.table(t).select('*', count='exact').limit(1).execute()
    n = r.count if r.count is not None else len(r.data or [])
    print(t + ':', n)
