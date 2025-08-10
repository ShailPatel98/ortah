import os, re, json, time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = os.getenv("BASE_URL", "https://ortahaus.com")

OUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
os.makedirs(OUT_DIR, exist_ok=True)
OUT_FILE = os.path.join(OUT_DIR, "products.json")

session = requests.Session()
session.headers.update({"User-Agent": "OrtahausBot/1.0 (+https://ortahaus.com)"})

def get_sitemap_urls():
    # Try /sitemap.xml then fallback to shopify product sitemap
    urls = set()
    for path in ["/sitemap.xml", "/sitemap_products_1.xml"]:
        try:
            resp = session.get(urljoin(BASE_URL, path), timeout=20)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "xml")
                for loc in soup.find_all("loc"):
                    u = loc.get_text(strip=True)
                    if "/products/" in u:
                        urls.add(u)
        except Exception:
            pass
    return sorted(urls)

def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())

def extract_product_fields(html: str, url: str):
    soup = BeautifulSoup(html, "lxml")

    title = soup.find("title").get_text(strip=True) if soup.find("title") else url
    # meta description
    desc = ""
    md = soup.find("meta", attrs={"name": "description"})
    if md and md.get("content"):
        desc = md["content"]

    # Try LD+JSON Product
    how_to_use, ingredients = "", ""
    bullets = []

    for script in soup.find_all("script", attrs={"type":"application/ld+json"}):
        try:
            data = json.loads(script.string or "{}")
            if isinstance(data, dict) and data.get("@type") == "Product":
                ddesc = data.get("description") or ""
                if ddesc and not desc:
                    desc = ddesc
                # nothing else standardized here
        except Exception:
            continue

    # Try to find sections by headings
    def section_text(label: str) -> str:
        # look for heading containing label
        for hx in soup.find_all(re.compile("^h[1-6]$")):
            if label.lower() in hx.get_text(" ", strip=True).lower():
                frag = []
                for sib in hx.find_all_next(["p","li"], limit=8):
                    t = clean_text(sib.get_text(" ", strip=True))
                    if t: frag.append(t)
                return " ".join(frag)[:500]
        return ""

    how_to_use = section_text("How to use") or section_text("How To Use")
    ingredients = section_text("Ingredients")

    # Collect a few bullets if present (li items near details)
    for li in soup.find_all("li"):
        txt = clean_text(li.get_text(" ", strip=True))
        if txt and len(bullets) < 8 and 8 <= len(txt) <= 180:
            bullets.append(txt)

    return {
        "id": url,
        "url": url,
        "title": title,
        "description": desc,
        "how_to_use": how_to_use,
        "ingredients": ingredients,
        "bullets": bullets,
        "tags": [],
    }

def main():
    product_urls = get_sitemap_urls()
    if not product_urls:
        print("No product URLs found via sitemap.")
        return

    out = []
    print(f"Found {len(product_urls)} product URLs")
    for i,u in enumerate(product_urls, start=1):
        try:
            r = session.get(u, timeout=30)
            if r.status_code == 200:
                data = extract_product_fields(r.text, u)
                out.append(data)
                print(f"[{i}/{len(product_urls)}] scraped:", data["title"][:80])
            else:
                print(f"[{i}/{len(product_urls)}] skip {u} status={r.status_code}")
        except Exception as e:
            print(f"[{i}/{len(product_urls)}] error {u} -> {e}")

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("Wrote:", OUT_FILE)

if __name__ == "__main__":
    main()
