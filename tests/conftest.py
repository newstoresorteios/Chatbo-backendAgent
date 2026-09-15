"""Unit tests never load developer/production integration credentials."""
import os

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
for key in tuple(os.environ):
    if any(part in key for part in ("SUPABASE", "DATABASE_URL", "OPENAI_API_KEY", "BREVO_API_KEY")):
        os.environ.pop(key, None)
