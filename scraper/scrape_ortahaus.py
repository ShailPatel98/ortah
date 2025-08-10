#!/usr/bin/env python3
import os
import json
import time
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = os.environ.get("BASE_URL", "https://ortahaus.com")
OUT_PATH = "data/products.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; OrtahausBot/1.0; +https://ortahaus.com)"
}

def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def get_sitemap_product_urls() -> list:
    urls = set()
    # try root sitemap
    for path in ["/sitemap.xml", "/sitemap_products_1.xml"]:
        try:
            xml = fetch(urljoin(BASE_URL, path))
            # naive parse for Shopify product links
            for m in re.finditer(r"<loc>(.*?)</loc>", xml):
                u = m.group(1).strip()
                if "/products/" in u:
                    urls.add(u)
        except Exception:
            pass
    return sorted(urls)

def text_of(el):
    return re.sub(r"\s+", " ", (el.get_text(" ", strip=True) if el else "")).strip()

def first_meta(soup, name, prop) -> str:
    tag = soup.find("meta", attrs={name: prop}) or soup.find("meta", attrs={"property": prop})
    return tag["content"].strip() if tag and tag.has_attr("content") else ""

def ld_json_product(soup) -> dict:
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "{}")
            if isinstance(data, dict) and data.get("@type") in ("Product", "product"):
                return data
        except Exception:
            continue
    return {}

def parse_product(url: str) -> dict:
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.get_text(strip=True) if soup.title else ""
    # Prefer og:title if present
    og_title = first_meta(soup, "property", "og:title")
    if og_title:
        title = og_title

    desc = first_meta(soup, "name", "description")
    og_img = first_meta(soup, "property", "og:image")
    ld = ld_json_product(soup)
    price = ""
    if isinstance(ld.get("offers"), dict):
        price = ld["offers"].get("price") or ""

    # Try to find bullets/how-to-use/ingredients by keyword sections
    bullets = []
    for li in soup.select("li"):
        txt = text_of(li)
        if (
            any(k in txt.lower() for k in ["hold", "finish", "texture", "volume", "frizz", "shine"])
            and 7 <= len(txt) <= 220
        ):
            bullets.append(txt)
    bullets = list(dict.fromkeys(bullets))[:12]

    def find_section(label_words: list) -> str:
        # look for a heading with those words, then grab the next paragraph/list
        for h in soup.find_all(re.compile("^h[1-6]$")):
            htxt = text_of(h).lower()
            if any(w in htxt for w in label_words):
                # next sibling text
                texts = []
                nxt = h.find_next_sibling()
                for _ in range(3):
                    if not nxt:
                        break
                    if nxt.name in ("p", "ul", "ol", "div"):
                        texts.append(text_of(nxt))
                    nxt = nxt.find_next_sibling()
                joined = " ".join([t for t in texts if t])
                if joined:
                    return joined
        return ""

    how_to_use = find_section(["how to use", "how-to", "use", "usage"])
    ingredients = find_section(["ingredients", "what's inside", "what’s inside"])

    tags = []
    # rough tag guesses from collections and keywords
    if "curl" in (title + " " + desc).lower():
        tags.append("curly")
    if "spray" in title.lower():
        tags.append("spray")
    if "powder" in title.lower():
        tags.append("powder")
    if "clay" in title.lower():
        tags.append("clay")
    if "pomade" in title.lower() or "cement" in title.lower():
        tags.append("pomade")

    record = {
        "id": url,
        "url": url,
        "title": title.strip(),
        "description": (ld.get("description") or desc or "").strip(),
        "price": price,
        "image": og_img or (ld.get("image") or ""),
        "bullets": bullets,
        "how_to_use": how_to_use,
        "ingredients": ingredients,
        "tags": tags,
    }

    # strip None, force types for safety
    for k, v in list(record.items()):
        if v is None:
            record[k] = ""
        elif isinstance(v, list):
            record[k] = [str(x) for x in v if x is not None]

    return record

def main():
    os.makedirs("data", exist_ok=True)
    product_urls = get_sitemap_product_urls()
    print(f"Found {len(product_urls)} product URLs")

    records = []
    for i, u in enumerate(product_urls, 1):
        try:
            rec = parse_product(u)
            print(f"[{i}/{len(product_urls)}] scraped: {rec['title']}")
            records.append(rec)
            time.sleep(0.2)
        except Exception as e:
            print(f"[{i}/{len(product_urls)}] ERROR {u} -> {e}")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"Wrote: {OUT_PATH} ({len(records)} items)")

if __name__ == "__main__":
    main()
