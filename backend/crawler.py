"""
KKU CS notices crawler.

This module provides a small, configurable crawler that downloads list pages
and post pages, saves raw HTML and parsed JSON. It is intentionally simple and
config-driven so CSS selectors can be updated if the site structure changes.
"""
import hashlib
import json
import os
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

import config
from PIL import Image, ImageOps, ImageFilter, ImageEnhance
import pytesseract
from urllib.parse import urljoin
import mimetypes
import tempfile
import uuid


def ensure_dirs():
    os.makedirs(config.RAW_DIR, exist_ok=True)
    os.makedirs(config.PARSED_DIR, exist_ok=True)
    os.makedirs(config.DATA_DIR, exist_ok=True)


def safe_id_from_url(url: str) -> str:
    # prefer a short hash of the URL as an identifier
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    return h


class KKUCrawler:
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        # Allow requests to use environment proxy settings by default
        try:
            # requests.Session uses env by default, but ensure trust_env is True
            self.session.trust_env = True
        except Exception:
            pass
        # If proxy env vars are set, ensure session.proxies include them
        http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if http_proxy or https_proxy:
            proxies = {}
            if http_proxy:
                proxies["http"] = http_proxy
            if https_proxy:
                proxies["https"] = https_proxy
            try:
                self.session.proxies.update(proxies)
            except Exception:
                pass
        # optional: log proxy usage
        if http_proxy or https_proxy:
            print(f"Using proxies: http={http_proxy} https={https_proxy}")
        ensure_dirs()
        self.index = self._load_index()

    def _load_index(self):
        try:
            with open(config.INDEX_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_index(self):
        with open(config.INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)

    def fetch_list_page(self, page: int = 1) -> str:
        # some sites use anchors for paging (#page1). We'll append a fragment
        # if necessary. The exact mechanism may need to be adjusted.
        # If an AJAX list endpoint is configured, call it instead and return
        # the raw JSON text. Otherwise fall back to fetching the base page.
        if getattr(config, "AJAX_LIST_URL", None):
            params = dict(config.AJAX_LIST_PARAMS)
            params.update({"pageNo": str(page)})
            resp = self.session.post(config.AJAX_LIST_URL, data=params, timeout=15)
            resp.raise_for_status()
            return resp.text
        url = config.BASE_URL
        if page > 1:
            url = f"{config.BASE_URL}#page{page}"
        resp = self.session.get(url, timeout=15)
        resp.raise_for_status()
        return resp.text

    def parse_list_page(self, html: str):
        # If the content is JSON from the AJAX endpoint, parse and return
        # items using the JSON structure. Otherwise parse HTML for links.
        links = []
        try:
            data = json.loads(html)
            # structure expected: {"data": {"list": [ ... ] }}
            lst = data.get("data", {}).get("list", [])
            for item in lst:
                bbs_seq = item.get("BBS_SEQ") or item.get("bbsSeq")
                subject = item.get("SUBJECT") or item.get("subject") or ""
                contents = item.get("CONTENTS") or item.get("CONTENTS") or None
                # Build a canonical view URL if possible
                view_url = None
                if bbs_seq:
                    view_url = f"https://cs.kku.ac.kr/cms/FR_CON/BoardView.do?MENU_ID={config.AJAX_LIST_PARAMS.get('MENU_ID')}&SITE_NO={config.AJAX_LIST_PARAMS.get('SITE_NO')}&BOARD_SEQ={config.AJAX_LIST_PARAMS.get('BOARD_SEQ')}&BBS_SEQ={bbs_seq}"
                links.append({"title": subject, "url": view_url, "bbs_seq": bbs_seq, "contents": contents})
            return links
        except Exception:
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.select(config.LIST_LINK_SELECTOR):
                href = a.get("href")
                if not href:
                    continue
                # Build absolute URL if needed
                if href.startswith("/"):
                    base = "https://cs.kku.ac.kr"
                    href = base + href
                links.append({"title": (a.get_text(strip=True) or ""), "url": href})
            return links

    def fetch_post(self, url: str) -> str:
        resp = self.session.get(url, timeout=15)
        resp.raise_for_status()
        return resp.text

    def parse_post(self, html: str):
        soup = BeautifulSoup(html, "html.parser")
        data = {}
        for key, sel in config.POST_SELECTORS.items():
            el = None
            # allow comma-separated selectors
            for s in sel.split(","):
                s = s.strip()
                if not s:
                    continue
                found = soup.select_one(s)
                if found:
                    el = found
                    break
            if el is None:
                data[key] = None
            else:
                # For content we want inner HTML; for others text
                if key == "content":
                    data[key] = str(el)
                else:
                    data[key] = el.get_text(strip=True)
        return data

    def save_raw(self, post_id: str, html: str):
        path = os.path.join(config.RAW_DIR, f"{post_id}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

    def save_parsed(self, post_id: str, meta: dict):
        path = os.path.join(config.PARSED_DIR, f"{post_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def _ensure_image_dir(self, post_id: str):
        d = os.path.join(config.RAW_DIR, "images", post_id)
        os.makedirs(d, exist_ok=True)
        return d

    def _download_file(self, url: str, dest_path: str):
        try:
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            with open(dest_path, "wb") as f:
                f.write(resp.content)
            return True
        except Exception as e:
            print("Failed to download", url, e)
            return False

    def _ocr_image(self, path: str) -> str:
        def preprocess(img: Image.Image) -> Image.Image:
            # Convert to RGB, then to L (grayscale) for many OCR cases
            img = img.convert("RGB")
            # optionally resize if very large for faster processing
            max_dim = 2500
            if max(img.size) > max_dim:
                scale = max_dim / max(img.size)
                new_size = (int(img.size[0] * scale), int(img.size[1] * scale))
                img = img.resize(new_size, Image.LANCZOS)
            # convert to grayscale
            img = img.convert("L")
            # enhance contrast
            img = ImageOps.autocontrast(img)
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.5)
            # apply a slight median filter to reduce noise
            img = img.filter(ImageFilter.MedianFilter(size=3))
            return img

        try:
            img = Image.open(path)
            proc = preprocess(img)
            # use both Korean and English
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmpf:
                tmp_path = tmpf.name
            proc.save(tmp_path, format="PNG")
            text = pytesseract.image_to_string(Image.open(tmp_path), lang="kor+eng")
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            return text
        except Exception as e:
            # Try a fallback: convert image to RGB and save as PNG, then OCR
            try:
                print("OCR primary failed for, trying conversion:", path, e)
                img = Image.open(path).convert("RGB")
                tmp = path + ".convert.png"
                img.save(tmp, format="PNG")
                # apply preprocess to converted image
                try:
                    img2 = Image.open(tmp)
                    proc2 = preprocess(img2)
                    proc_tmp = tmp + ".proc.png"
                    proc2.save(proc_tmp, format="PNG")
                    text = pytesseract.image_to_string(Image.open(proc_tmp), lang="kor+eng")
                except Exception:
                    text = pytesseract.image_to_string(Image.open(tmp), lang="kor+eng")
                try:
                    os.remove(tmp)
                except Exception:
                    pass
                try:
                    os.remove(proc_tmp)
                except Exception:
                    pass
                return text
            except Exception as e2:
                print("OCR fallback failed for", path, e2)
                return ""

    def process_attachments_from_content(self, post_id: str, content_html: str, base_url: str = None):
        # find <img> tags and download+ocr them
        if not content_html:
            return []
        soup = BeautifulSoup(content_html, "html.parser")
        imgs = soup.find_all("img")
        if not imgs:
            return []
        image_dir = self._ensure_image_dir(post_id)
        attachments = []
        for i, img in enumerate(imgs, start=1):
            src = img.get("src")
            if not src:
                continue
            # resolve relative URLs
            if base_url and src.startswith("/"):
                src_url = urljoin(base_url, src)
            elif src.startswith("/"):
                src_url = urljoin("https://cs.kku.ac.kr", src)
            else:
                src_url = src
            ext = os.path.splitext(src_url.split("?")[0])[1]
            if not ext:
                # try to guess by content-type via HEAD
                try:
                    h = self.session.head(src_url, timeout=10)
                    ctype = h.headers.get("content-type", "")
                    ext = mimetypes.guess_extension(ctype.split(";")[0].strip() or "") or ".jpg"
                except Exception:
                    ext = ".jpg"
            fname = f"img_{i}{ext}"
            dest = os.path.join(image_dir, fname)
            ok = self._download_file(src_url, dest)
            ocr_text = ""
            if ok:
                ocr_text = self._ocr_image(dest)
            attachments.append({"name": fname, "url": src_url, "path": dest, "ocr_text": ocr_text})
        return attachments

    def run(self, max_pages: Optional[int] = 3):
        """
        Crawl list pages up to `max_pages`. If `max_pages` is None, crawl until
        an empty page is encountered (or until an internal safety limit).
        """
        new_count = 0
        page = 1
        safety_limit = 200
        pages_crawled = 0
        while True:
            if max_pages is not None and page > max_pages:
                break
            if pages_crawled >= safety_limit:
                print("Reached safety page limit, stopping")
                break
            print(f"Fetching list page {page}...")
            try:
                html = self.fetch_list_page(page=page)
            except Exception as e:
                print("Failed to fetch list page:", e)
                break
            links = self.parse_list_page(html)
            pages_crawled += 1
            if not links:
                print("No links found on page", page)
                break
            for item in links:
                # If the AJAX list provided CONTENTS and BBS_SEQ, use them
                url = item.get("url")
                bbs_seq = item.get("bbs_seq")
                if bbs_seq:
                    post_id = str(bbs_seq)
                elif url:
                    post_id = safe_id_from_url(url)
                else:
                    # fallback to hashing the title
                    post_id = safe_id_from_url(item.get("title", ""))

                if post_id in self.index:
                    continue

                if item.get("contents"):
                    # use provided CONTENTS from AJAX response
                    parsed = {"title": item.get("title"), "content": item.get("contents")}
                    post_html = item.get("contents")
                else:
                    if not url:
                        print("No URL or contents for item, skipping", item)
                        continue
                    try:
                        post_html = self.fetch_post(url)
                    except Exception as e:
                        print("Failed to fetch post:", url, e)
                        continue
                    parsed = self.parse_post(post_html)
                parsed.update({"_source_url": url, "_fetched_at": int(time.time())})
                # Save raw and parsed, then process images for OCR if present
                self.save_raw(post_id, post_html)
                # process images embedded in content
                attachments = self.process_attachments_from_content(post_id, parsed.get("content"), base_url=url)
                if attachments:
                    parsed.setdefault("attachments", []).extend(attachments)
                    # aggregate OCR text
                    agg = "\n".join(a.get("ocr_text","") for a in parsed.get("attachments",[]))
                    parsed["ocr_text"] = agg
                self.save_parsed(post_id, parsed)
                self.index[post_id] = {"url": url, "title": item.get("title"), "fetched_at": int(time.time())}
                new_count += 1
                # be polite
                time.sleep(0.3)
            # small delay between pages
            time.sleep(0.5)
        if new_count:
            self._save_index()
        print(f"Done. New posts: {new_count}")
