import pdfplumber
import pandas as pd
import json
import argparse
import sys
import base64
import io
from PIL import Image

# Function for automatically renaming duplicate columns
def make_unique_columns(columns):
    seen = {}
    unique_columns = []
    for col in columns:
        if col in seen:
            seen[col] += 1
            unique_columns.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 0
            unique_columns.append(col)
    return unique_columns

# Command-line argument parser setup
parser = argparse.ArgumentParser(description="Extract tables and text from a PDF file.")
parser.add_argument("pdf_path", type=str, help="Path to the PDF file")
args = parser.parse_args()
pdf_path = args.pdf_path

# List to store data from all tables and texts
data = {"tables": [], "text": "", "texttables": []}

# Open the PDF file and extract tables and text
with pdfplumber.open(pdf_path) as pdf:
    extracted_text = []
    text_tables = []
    images_info = []  # [(page_index, image_dict), ...]

    for i, page in enumerate(pdf.pages):
        extracted_text.append(page.extract_text() or "")

        # Tables
        tables = page.extract_tables()
        for table in tables:
            if not table:
                continue
            columns = make_unique_columns(table[0])
            df = pd.DataFrame(table[1:], columns=columns)
            data["tables"].append(df.to_dict(orient="records"))

            # Text version of the table
            text_table = "\n".join(
                [
                    " | ".join("" if (cell is None) else str(cell) for cell in row)
                    for row in table
                    if row and any(x is not None and str(x).strip() != "" for x in row)
                ]
            )
            if text_table.strip():
                text_tables.append(text_table)

        # Page images (raster XObjects)
        try:
            page_images = page.images or []
        except Exception:
            page_images = []
        for im in page_images:
            images_info.append((i, im))

    data["text"] = "\n".join(extracted_text)
    data["texttables"] = text_tables

    # If the file contains no text and exactly one image, extract it as a PNG (black and white) in base64
    has_no_text = len(("".join(extracted_text)).strip()) == 0
    if has_no_text and len(images_info) == 1:
        page_idx, im = images_info[0]
        page = pdf.pages[page_idx]

        # Render the page and crop the image area by bbox
        dpi = 300
        scale = dpi / 72.0  # PDF units -> pixels
        page_image = page.to_image(resolution=dpi).original  # PIL.Image
        W, H = page_image.size

        # Get bbox from PDF coordinates (origin at bottom-left)
        x0 = float(im.get("x0", 0))
        y0 = float(im.get("y0", 0))
        x1 = float(im.get("x1", page.width))
        y1 = float(im.get("y1", page.height))

        # Convert to PIL coordinates (origin at top-left)
        left = max(0, int(round(x0 * scale)))
        upper = max(0, int(round(H - y1 * scale)))
        right = min(W, int(round(x1 * scale)))
        lower = min(H, int(round(H - y0 * scale)))

        # Safeguard against incorrect bbox
        if right <= left or lower <= upper:
            crop_img = page_image
        else:
            crop_img = page_image.crop((left, upper, right, lower))

        # Convert to strictly black-and-white (1-bit) with a threshold of 128 and save as PNG
        bw = crop_img.convert("L").point(lambda x: 0 if x < 128 else 255, mode="1")
        buf = io.BytesIO()
        bw.save(buf, format="PNG", optimize=True)
        data["image"] = base64.b64encode(buf.getvalue()).decode("ascii")

# Output JSON to stdout
sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=4) + "\n")
