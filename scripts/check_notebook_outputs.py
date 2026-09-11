import json
import sys
from pathlib import Path


def main(paths: list[str]) -> int:
    unsafe: list[str] = []
    for value in paths:
        path = Path(value)
        notebook = json.loads(path.read_text(encoding="utf-8"))
        if any(
            cell.get("outputs") or cell.get("execution_count") is not None
            for cell in notebook.get("cells", [])
            if cell.get("cell_type") == "code"
        ):
            unsafe.append(str(path))
    if unsafe:
        print(
            "Notebook outputs or execution counts must be cleared: " + ", ".join(unsafe)
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
