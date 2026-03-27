import fitz  # pymupdf
from pathlib import Path


def extract_text(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    return "\n".join(page.get_text() for page in doc)


def extract_pages(pdf_path: str, start: int = 0, end: int | None = None) -> str:
    doc = fitz.open(pdf_path)
    pages = list(doc)[start:end]
    return "\n".join(page.get_text() for page in pages)


def extract_metadata(pdf_path: str) -> dict:
    doc = fitz.open(pdf_path)
    return {
        "page_count": doc.page_count,
        "metadata": doc.metadata,
        "file": str(Path(pdf_path).resolve()),
    }


def extract_images(pdf_path: str, output_dir: str) -> list[str]:
    doc = fitz.open(pdf_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved = []
    for page_num, page in enumerate(doc):
        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            base_image = doc.extract_image(xref)
            ext = base_image["ext"]
            path = out / f"page{page_num}_img{img_index}.{ext}"
            path.write_bytes(base_image["image"])
            saved.append(str(path))
    return saved
