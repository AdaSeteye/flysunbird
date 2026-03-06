"""One-off: print text positions from ticket_template.pdf for overlay mapping."""
import fitz
import os
import sys
base = os.path.join(os.path.dirname(__file__), "..", "app", "assets", "ticket_template.pdf")
doc = fitz.open(base)
page = doc[0]
# Page size and rotation (must match standard; rotation != 0 can cause overlay to appear in wrong place)
sys.stderr.write("Page rect: %s  rotation: %s\n" % (page.rect, getattr(page, "rotation", 0)))
# Image bboxes (e.g. QR code) — use this to set _QR_RECT in ticket_service.py
try:
    for img in doc.get_page_images(0, full=True):
        bbox = page.get_image_bbox(img)
        if bbox:
            sys.stderr.write("Image bbox: %s\n" % (bbox,))
except Exception as e:
    sys.stderr.write("get_images/bbox: %s\n" % e)
blocks = page.get_text("dict")["blocks"]
for b in blocks:
    for l in b.get("lines", []):
        for s in l.get("spans", []):
            t = s["text"].strip().replace("\u2192", "->")
            if not t:
                continue
            bbox = s["bbox"]
            print(round(bbox[0], 1), round(bbox[1], 1), round(bbox[2], 1), round(bbox[3], 1), "|", t[:55])
doc.close()
