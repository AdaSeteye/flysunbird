"""One-off: print text positions from ticket_template.pdf for overlay mapping."""
import fitz
import os
base = os.path.join(os.path.dirname(__file__), "..", "app", "assets", "ticket_template.pdf")
doc = fitz.open(base)
page = doc[0]
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
