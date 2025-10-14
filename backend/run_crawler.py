#!/usr/bin/env python3
"""Simple CLI to run the crawler."""
import argparse
from crawler import KKUCrawler


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--max-pages", type=int, default=3, help="max list pages to crawl (<=0 means crawl until no more pages)")
    args = p.parse_args()

    crawler = KKUCrawler()
    maxp = args.max_pages
    if maxp <= 0:
        maxp = None
    crawler.run(max_pages=maxp)


if __name__ == "__main__":
    main()
