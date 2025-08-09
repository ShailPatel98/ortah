import os, json, time, re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import requests
from dotenv import load_dotenv

load_dotenv()
BASE_URL = os.getenv("BASE_URL", "https://ortahaus.com").rstrip("/")
OUT_PATH = os.path.join("data", "products.json")
HEADERS = {"User-Agent": "OrtahausBot/0.1 (contact: staging@example.com)"}

os.makedirs("data", exist_ok=True)
PRODUCTS = {}

def get(url):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp

def parse_sitemap(url):
    r = get(url)
    soup = BeautifulSoup(r.text, "xml")
    return [loc.text for loc in soup.find_all("loc")]

def fetch_product_json(product_url):
    m = re.search(r"/products/([a-z0-9-]+)", product_url)
    if not m:
        return None
    handle = m.group(1)
    js_url = urljoin(BASE_URL, f"/products/{handle}.js")
    try:
        r = get(js_url)
        if r.status_code == 200 and r.headers.get("content-type","").startswith("application/json"):
            return r.json()
    except Exception:
        return None
    return None

def scrape_product(product_url):
    data = {"url": product_url, "title": None, "description": None, "price": None, "images": [], "tags": [], "options": {}}
    pj = fetch_product_json(product_url)
    if pj:
        data["title"] = pj.get("title")
        data["description"] = pj.get("description")
        data["images"] = pj.get("images", [])
        data["tags"] = pj.get("tags", [])
        variants = pj.get("variants", [])
        if variants:
            data["price"] = variants[0].get("price")
            data["options"] = {opt.get("name"): opt.get("values") for opt in pj.get("options", [])}
        return data

    html = get(product_url).text
    soup = BeautifulSoup(html, "lxml")
    if soup.title:
        data["title"] = soup.title.text.strip()
    desc = soup.find("meta", {"name": "description"})
    if desc and desc.get("content"):
        data["description"] = desc["content"].strip()
    for img in soup.select("img"):
        src = img.get("src") or img.get("data-src")
        if src and src.startswith("http"):
            data["images"].append(src)
    data["images"] = list(dict.fromkeys(data["images"]))
    return data

def main():
    print("Discovering product URLs via sitemap…")
    urls = []
    rootmap = urljoin(BASE_URL, "/sitemap.xml")
    try:
        for u in parse_sitemap(rootmap):
            if "sitemap_products" in u:
                for pu in parse_sitemap(u):
                    if "/products/" in pu:
                        urls.append(pu)
            elif "/products/" in u:
                urls.append(u)
    except Exception as e:
        print("Sitemap parse failed, fallback to collections:", e)
        for path in ["/collections/all"]:
            try:
                html = get(urljoin(BASE_URL, path)).text
                soup = BeautifulSoup(html, "lxml")
                for a in soup.select("a[href*='/products/']"):
                    urls.append(urljoin(BASE_URL, a["href"]))
            except Exception:
                pass

    urls = sorted(list(set(urls)))
    print(f"Found {len(urls)} product URLs")

    for i, url in enumerate(urls, 1):
        try:
            prod = scrape_product(url)
            if prod.get("title"):
                PRODUCTS[url] = prod
                print(f"[{i}/{len(urls)}] scraped: {prod['title']}")
            time.sleep(0.6)
        except Exception as e:
            print("Failed:", url, e)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(list(PRODUCTS.values()), f, ensure_ascii=False, indent=2)
    print("Wrote:", OUT_PATH)

if __name__ == "__main__":
    main()
