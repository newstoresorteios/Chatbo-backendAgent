"""Run a full customer import using the company's stored integration credentials."""
import argparse
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.tray_customer_sync import tray_customer_sync


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--checkpoint", type=Path)
    args = parser.parse_args()
    page = args.start_page
    if args.checkpoint and args.checkpoint.exists():
        checkpoint = json.loads(args.checkpoint.read_text())
        if checkpoint["workspace_id"] != args.workspace_id:
            parser.error("Checkpoint pertence a outra empresa")
        page = checkpoint["next_page"]
    total = 0
    while page is not None:
        try:
            result = tray_customer_sync.sync_page(args.workspace_id, page=page)
        except RuntimeError as exc:
            if "tray_adaptor_429" not in str(exc):
                raise RuntimeError(f"Importação interrompida na página {page}") from None
            if "day" in str(exc).lower() or "daily" in str(exc).lower():
                print(f"Limite diário atingido; retome pela página {page}.", flush=True)
                return
            print(f"Limite temporário na página {page}; nova tentativa em 60s.", flush=True)
            time.sleep(60)
            continue
        total += result["synced"]
        print(f"page={page} synced={result['synced']} total={total}", flush=True)
        page = result["nextPage"]
        if args.checkpoint:
            args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.checkpoint.with_suffix(".tmp")
            temporary.write_text(json.dumps({"workspace_id": args.workspace_id,
                                            "next_page": page}))
            temporary.replace(args.checkpoint)
        if page is not None:
            time.sleep(35)


if __name__ == "__main__":
    main()
