"""Crawl every book on books.toscrape.com (a sandbox site built for scraping practice).

    python examples/books_crawler.py --pages 3 --output books.csv
"""
import argparse
import csv
import logging
from urllib.parse import urljoin

from lxml import html

from stealth_http import ProxyPool, StealthClient

START_URL = "https://books.toscrape.com/catalogue/page-1.html"
RATINGS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


def parse_listing(page_url, body):
    tree = html.fromstring(body)
    books = []
    for card in tree.xpath("//article[@class='product_pod']"):
        link = card.xpath(".//h3/a")[0]
        rating_class = card.xpath(".//p[contains(@class,'star-rating')]/@class")[0]
        books.append({
            "title": link.get("title"),
            "price": card.xpath("string(.//p[@class='price_color'])").strip(),
            "rating": RATINGS.get(rating_class.split()[-1]),
            "in_stock": "In stock" in card.xpath("string(.//p[contains(@class,'availability')])"),
            "url": urljoin(page_url, link.get("href")),
        })
    next_href = tree.xpath("//li[@class='next']/a/@href")
    next_url = urljoin(page_url, next_href[0]) if next_href else None
    return books, next_url


def crawl(client, max_pages=None):
    url, page = START_URL, 0
    while url and (max_pages is None or page < max_pages):
        resp = client.get(url)
        books, url = parse_listing(resp.url, resp.text)
        page += 1
        logging.info("page %d: %d books", page, len(books))
        yield from books


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=int, default=None, help="stop after N listing pages")
    parser.add_argument("--output", default="books.csv")
    parser.add_argument("--proxy-file", help="one proxy URL per line")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pool = ProxyPool.from_file(args.proxy_file) if args.proxy_file else ProxyPool.from_env()

    with StealthClient(proxy_pool=pool or None, min_interval=0.5) as client:
        rows = list(crawl(client, args.pages))

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["title", "price", "rating", "in_stock", "url"])
        writer.writeheader()
        writer.writerows(rows)
    logging.info("saved %d books to %s", len(rows), args.output)


if __name__ == "__main__":
    main()
