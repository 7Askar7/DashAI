import argparse
from pathlib import Path

import uvicorn

from .app import ROOT, create_app

parser = argparse.ArgumentParser(description="Локальный Agentboard dashboard")
parser.add_argument("--port", type=int, default=4242)
parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
parser.add_argument("--demo", action="store_true", help="Создать явно обозначенный демонстрационный проект в пустой БД")
args = parser.parse_args()
if not 1 <= args.port <= 65535:
    parser.error("Порт должен находиться в диапазоне 1..65535")
uvicorn.run(create_app(args.data_dir, seed_demo=args.demo, base_url=f"http://127.0.0.1:{args.port}"), host="127.0.0.1", port=args.port)
