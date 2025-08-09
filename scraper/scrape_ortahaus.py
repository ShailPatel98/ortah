import os, json, time, re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import requests
from dotenv import load_dotenv

load_dotenv()
BASE_URL = os.getenv("BASE_URL", "https://ortahaus.com").rstrip("/")
OUT_PATH = os.path.join("data", "products.json")
HEADERS = {"User-Agent": "OrtahausBot/0.2 (contact: staging@example.com)"}

os.makedirs("data", exist_ok=True)
PRODUCTS = {}

# ---- helpers ---------------------------------------------------------------

def get(url):
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r

def parse_sitemap(url):
    soup = BeautifulSoup(get(url).text, "xml")
    return [loc.text for loc in soup.find_all("loc")]

def shopify_product_json(product_url):
    m = re.search(r"/products/([a-z0-9-]+)", product_url)
    if not m: return None
    js_url = urljoin(BASE_URL, f"/products/{m.group(1)}.js")
    try:
        r = get(js_url)
        if r.ok and r.headers.get("content-type","").startswith("application/json"):
            return r.json()
    except Exception:
        return None
    return None

def try_ld_json(html):
    soup = BeautifulSoup(html, "lxml")
    for s in soup.find_all("script", {"type":"application/ld+json"}):
        try:
            data = json.loads(s.text.strip())
            if isinstance(data, dict) and data.get("@type") in ("Product","BreadcrumbList"):
                return data
        except Exception:
            continue
    return None

def extract_text_blocks(soup):
    # Try to grab meaningful bullets/sections from PDP
    blocks = []
    # common content area; fallback to all <li> and <p>
    for sel in ["section", ".product", ".product__description", ".rte", "main", "body"]:
        for el in soup.select(sel):
            for li in el.find_all("li"):
                t = " ".join(li.get_text(" ", strip=True).split())
                if len(t) > 0 and len(t) <= 300:
                    blocks.append(t)
            for p in el.find_all("p"):
                t = " ".join(p.get_text(" ", strip=True).split())
                if 20 <= len(t) <= 300:
                    blocks.append(t)
    # de-dup
    seen, uniq = set(), []
    for t in blocks:
        if t not in seen:
            seen.add(t); uniq.append(t)
    return uniq[:20]

HAIR_TYPES = ["fine", "thick", "coarse", "medium", "straight", "wavy", "curly", "coily"]
CONCERNS = ["volume", "frizz", "dry", "dryness", "oily", "oiliness", "hold", "definition", "shine", "matte"]
FINISHES = ["matte", "natural", "satin", "shine", "gloss"]
HOLDS = ["light", "medium", "firm", "strong", "high"]

def infer_attributes(text):
    L = text.lower()
    attrs = {"hair_type": [], "concern": [], "finish": [], "hold": []}
    for w in HAIR_TYPES:
        if re.search(rf"\\b{re.escape(w)}\\b", L): attrs["hair_type"].append(w)
    for w in CONCERNS:
        if re.search(rf"\\b{re.escape(w)}\\b", L): attrs["concern"].append(w)
    for w in FINISHES:
        if re.search(rf"\\b{re.escape(w)}\\b", L): attrs["finish"].append(w)
    for w in HOLDS:
        if re.search(rf"\\b{re.escape(w)}\\b", L): attrs["hold"].append(w)
    # unique
    for k in attrs: attrs[k] = sorted(list(set(attrs[k])))
    return attrs

# ---- main scraping ---------------------------------------------------------

def scrape_product(url):
    data = {
        "url": url, "title": None, "description": None, "price": None,
        "images": [], "tags": [], "attributes": {}, "bullets": [], "how_to_use": "", "ingredients": ""
    }

    pj = shopify_product_json(url)
    if pj:
        data["title"] = pj.get("title")
        data["description"] = pj.get("description")
        data["images"] = pj.get("images", [])
        data["tags"] = pj.get("tags", [])
        variants = pj.get("variants", [])
        if variants:
            data["price"] = variants[0].get("price")

    html = get(url).text
    soup = BeautifulSoup(html, "lxml")

    # Fallback title/desc
    if not data["title"] and soup.title:
        data["title"] = soup.title.get_text(strip=True)
    mdesc = soup.find("meta", {"name":"description"})
    if (not data["description"]) and mdesc and mdesc.get("content"):
        data["description"] = mdesc["content"].strip()

    # Pull bullets/paragraphs & infer attributes
    blocks = extract_text_blocks(soup)
    data["bullets"] = blocks[:12]

    # Try headings for "How to use" / "Ingredients"
    text = soup.get_text(" ", strip=True)
    # naive splits
    for label in ["How to use", "HOW TO USE", "How To Use"]:
        m = re.search(rf"{label}[:\\-\\s]+(.{{20,200}})", text)
        if m:
            data["how_to_use"] = m.group(1).strip()
            break
    for label in ["Ingredients", "INGREDIENTS"]:
        m = re.search(rf"{label}[:\\-\\s]+(.{{20,300}})", text)
        if m:
            data["ingredients"] = m.group(1).strip()
            break

    # Attributes inferred from all text we have
    big_text = " ".join(filter(None, [
        data.get("title") or "",
        data.get("description") or "",
        " ".join(blocks)
    ]))
    data["attributes"] = infer_attributes(big_text)

    # Clean images
    if not data["images"]:
        for img in soup.select("img"):
            src = img.get("src") or img.get("data-src")
            if src and src.startswith("http"):
                data["images"].append(src)
        data["images"] = list(dict.fromkeys(data["images"]))

    return data

def main():
    print("Discovering product URLs via sitemap…")
    urls = []
    root = urljoin(BASE_URL, "/sitemap.xml")
    try:
        for u in parse_sitemap(root):
            if "sitemap_products" in u:
                for pu in parse_sitemap(u):
                    if "/products/" in pu: urls.append(pu)
            elif "/products/" in u:
                urls.append(u)
    except Exception as e:
        print("Sitemap parse failed, fallback to /collections/all:", e)
        html = get(urljoin(BASE_URL, "/collections/all")).text
        soup = BeautifulSoup(html, "lxml")
        for a in soup.select("a[href*='/products/']"):
            urls.append(urljoin(BASE_URL, a["href"]))

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
