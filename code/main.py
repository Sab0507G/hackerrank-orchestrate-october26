"""Entry point: python3 code/main.py  -> writes output.csv at the repo root."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline import run  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "dataset"


def main():
    results = run(DATASET, DATASET / "deletion_requests.csv", ROOT / "output.csv")
    print(f"wrote {len(results)} rows to {ROOT / 'output.csv'}")


if __name__ == "__main__":
    main()
