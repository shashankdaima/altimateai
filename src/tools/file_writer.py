import json
import csv
from pathlib import Path


def write_text(path: str, content: str, encoding: str = "utf-8") -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding=encoding)
    return str(p.resolve())


def write_json(path: str, data: dict | list, indent: int = 2) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=indent, ensure_ascii=False), encoding="utf-8")
    return str(p.resolve())


def write_csv(path: str, rows: list[dict], fieldnames: list[str] | None = None) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        p.write_text("")
        return str(p.resolve())
    fields = fieldnames or list(rows[0].keys())
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return str(p.resolve())


def write_bytes(path: str, data: bytes) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return str(p.resolve())


def append_text(path: str, content: str, encoding: str = "utf-8") -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding=encoding) as f:
        f.write(content)
    return str(p.resolve())
