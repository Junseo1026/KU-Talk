"""Repair OCR for existing attachments where OCR text is missing.

This script scans `backend/data/parsed/*.json` and for any attachment entry
with empty `ocr_text` (or missing), it re-runs OCR on the stored file and
updates the JSON.

Run: `python3 backend/repair_ocr.py`
"""
import os
import sys
import json

# Ensure we can import crawler from the backend folder
HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
from crawler import KKUCrawler


def main():
    c = KKUCrawler()
    parsed_dir = os.path.join(HERE, "data", "parsed")
    files = [f for f in os.listdir(parsed_dir) if f.endswith('.json')]
    updated = 0
    for fname in files:
        path = os.path.join(parsed_dir, fname)
        with open(path, 'r', encoding='utf-8') as f:
            parsed = json.load(f)
        attachments = parsed.get('attachments') or []
        changed = False
        for a in attachments:
            if not a.get('path'):
                continue
            if a.get('ocr_text'):
                continue
            p = a.get('path')
            if not os.path.exists(p):
                print('attachment file missing:', p)
                continue
            print('Re-OCR:', fname, p)
            ocr = c._ocr_image(p)
            a['ocr_text'] = ocr
            changed = True
        if changed:
            # update aggregated ocr_text
            parsed['ocr_text'] = '\n'.join(a.get('ocr_text','') for a in parsed.get('attachments',[]))
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(parsed, f, ensure_ascii=False, indent=2)
            updated += 1
    print('Done. Updated', updated, 'files')


if __name__ == '__main__':
    main()

