"""
Configuration for the crawler.

Adjust selectors here if the target site's HTML structure changes.
"""
BASE_URL = "https://cs.kku.ac.kr/cms/FR_CON/index.do?MENU_ID=140"

# CSS selector to find post link elements on a listing page.
# Example: 'div.board_list a' — update when you inspect the real page.
LIST_LINK_SELECTOR = "a[href*='index.do']"

# CSS selectors (or callables) to extract fields from a post HTML document.
POST_SELECTORS = {
    "title": "h3, .subject, .title",
    "content": "#contents, .contents, .bbs_view_content",
    "date": ".date, .wdate",
}

# AJAX list endpoint. If the board loads list via AJAX, prefer requesting this
# endpoint directly. The crawler will POST `AJAX_LIST_PARAMS` merged with the
# paging params (`pageNo`, `pagePerCnt`).
AJAX_LIST_URL = "https://cs.kku.ac.kr/ajax/FR_SVC/BBSViewList2.do"
AJAX_LIST_PARAMS = {
    "MENU_ID": "140",
    "SITE_NO": "23",
    "BOARD_SEQ": "3",
    "pagePerCnt": "20",
}

import os
BASE_DIR = os.path.dirname(__file__)
# Storage folders (absolute paths under the backend folder)
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PARSED_DIR = os.path.join(DATA_DIR, "parsed")
INDEX_FILE = os.path.join(DATA_DIR, "index.json")
