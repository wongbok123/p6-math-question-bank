"""
PDF to image conversion using PyMuPDF.
"""

import fitz  # PyMuPDF
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional, Generator
from PIL import Image
import io
import re

from config import PDF_DPI, PDF_DIR, IMAGES_DIR


class PDFLoader:
    """Handles PDF loading and conversion to images."""

    def __init__(self, dpi: int = PDF_DPI):
        self.dpi = dpi
        self.zoom = dpi / 72  # PDF standard is 72 DPI

    def load_pdf(self, pdf_path: Path) -> fitz.Document:
        """Load a PDF document."""
        return fitz.open(pdf_path)

    def get_page_count(self, doc: fitz.Document) -> int:
        """Get total number of pages."""
        return len(doc)

    def page_to_image(self, doc: fitz.Document, page_num: int) -> np.ndarray:
        """
        Convert a single PDF page to a numpy array (OpenCV format).
        """
        page = doc[page_num]
        mat = fitz.Matrix(self.zoom, self.zoom)
        pix = page.get_pixmap(matrix=mat)

        # Convert to numpy array
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )

        # Convert RGB to BGR for OpenCV
        if pix.n == 4:  # RGBA
            img = img[:, :, :3]  # Drop alpha
        if pix.n >= 3:
            img = img[:, :, ::-1]  # RGB to BGR

        return img

    def page_to_pil(self, doc: fitz.Document, page_num: int) -> Image.Image:
        """
        Convert a single PDF page to a PIL Image.
        """
        page = doc[page_num]
        mat = fitz.Matrix(self.zoom, self.zoom)
        pix = page.get_pixmap(matrix=mat)

        # Convert to PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return img

    def iterate_pages(
        self, doc: fitz.Document, start: int = 0, end: Optional[int] = None
    ) -> Generator[Tuple[int, np.ndarray], None, None]:
        """
        Generator that yields (page_num, image) tuples.
        """
        if end is None:
            end = len(doc)

        for page_num in range(start, end):
            yield page_num, self.page_to_image(doc, page_num)

    def extract_all_pages(
        self, pdf_path: Path, output_dir: Optional[Path] = None
    ) -> List[Path]:
        """
        Extract all pages as images and save to disk.
        Returns list of saved image paths.
        """
        doc = self.load_pdf(pdf_path)
        stem = pdf_path.stem

        if output_dir is None:
            output_dir = IMAGES_DIR / stem
        output_dir.mkdir(parents=True, exist_ok=True)

        saved_paths = []
        for page_num in range(len(doc)):
            img = self.page_to_image(doc, page_num)
            output_path = output_dir / f"page_{page_num:03d}.png"

            # Convert BGR to RGB for saving
            img_rgb = img[:, :, ::-1] if len(img.shape) == 3 else img
            Image.fromarray(img_rgb).save(output_path)

            saved_paths.append(output_path)

        doc.close()
        return saved_paths

    def get_text(self, doc: fitz.Document, page_num: int) -> str:
        """
        Extract text from a page using PyMuPDF's built-in OCR.
        Useful for quick text searches.
        """
        page = doc[page_num]
        return page.get_text()

    def search_text(
        self, doc: fitz.Document, text: str, page_range: Optional[Tuple[int, int]] = None
    ) -> List[Tuple[int, fitz.Rect]]:
        """
        Search for text across pages.
        Returns list of (page_num, rect) tuples.
        """
        results = []
        start, end = page_range if page_range else (0, len(doc))

        for page_num in range(start, end):
            page = doc[page_num]
            matches = page.search_for(text)
            for rect in matches:
                results.append((page_num, rect))

        return results


def parse_pdf_filename(filename: str) -> Tuple[int, str]:
    """
    Parse PDF filename to extract year and school name.
    Expected format: "YYYY-P6-Maths-Prelim Exam-School Name.pdf"
    """
    # Pattern: year at start, school name at end
    pattern = r"(\d{4})-P6-Maths-Prelim Exam-(.+)\.pdf"
    match = re.match(pattern, filename)

    if match:
        year = int(match.group(1))
        school = match.group(2).strip()
        return year, school

    # Fallback: try to find year anywhere
    year_match = re.search(r"(\d{4})", filename)
    year = int(year_match.group(1)) if year_match else 2025

    # Use filename without extension as school name
    school = Path(filename).stem
    return year, school


def list_pdfs(directory: Path = PDF_DIR) -> List[Path]:
    """List all PDF files in a directory."""
    return sorted(directory.glob("*.pdf"))


if __name__ == "__main__":
    # Test PDF loading
    pdfs = list_pdfs()
    print(f"Found {len(pdfs)} PDFs:")
    for pdf in pdfs:
        year, school = parse_pdf_filename(pdf.name)
        print(f"  {pdf.name} -> Year: {year}, School: {school}")

        loader = PDFLoader()
        doc = loader.load_pdf(pdf)
        print(f"    Pages: {loader.get_page_count(doc)}")
        doc.close()
