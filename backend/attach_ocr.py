"""Process existing parsed posts: download images and run OCR, update parsed JSONs."""
from crawler import KKUCrawler
import json
import os


def main():
    c = KKUCrawler()
    base = os.path.join(os.path.dirname(__file__), "data", "parsed")
    files = [f for f in os.listdir(base) if f.endswith('.json')]
    for fname in files:
        pid = os.path.splitext(fname)[0]
        path = os.path.join(base, fname)
        with open(path, 'r', encoding='utf-8') as f:
            parsed = json.load(f)
        if parsed.get('attachments'):
            continue
        content = parsed.get('content')
        source = parsed.get('_source_url')
        attachments = c.process_attachments_from_content(pid, content, base_url=source)
        if attachments:
            parsed.setdefault('attachments', []).extend(attachments)
            parsed['ocr_text'] = '\n'.join(a.get('ocr_text','') for a in parsed['attachments'])
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(parsed, f, ensure_ascii=False, indent=2)
            print('Updated', pid, 'attachments=', len(attachments))


if __name__ == '__main__':
    main()

