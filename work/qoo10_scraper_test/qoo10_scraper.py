from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

from PIL import Image, ImageOps
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


CSV_HEADER = [
    "商品名", "種類名", "説明", "価格", "税率", "在庫数", "公開状態", "表示順", "種類在庫数",
] + [f"画像{i}" for i in range(1, 22)]

BLOCK_MARKERS = (
    "captcha", "robot", "ロボットではありません", "画像認証", "アクセスが集中",
    "access denied", "forbidden", "523 error", "エラーが発生しました",
)


class AccessBlocked(RuntimeError):
    pass


@dataclass
class SearchItem:
    product_id: str
    name: str
    url: str
    price_yen: int | None


@dataclass
class Failure:
    product_id: str
    url: str
    stage: str
    reason: str


def log_event(path: Path, event: str, **data: object) -> None:
    record = {"time": datetime.now().astimezone().isoformat(timespec="seconds"), "event": event, **data}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def normalize_price(value: str) -> int | None:
    matches = re.findall(r"([0-9][0-9,]*)\s*円", value or "")
    if not matches:
        return None
    return int(matches[-1].replace(",", ""))


def detect_block(page: Page) -> None:
    title = page.title().lower()
    body = page.locator("body").inner_text(timeout=10_000).lower()
    hit = next((marker for marker in BLOCK_MARKERS if marker in title or marker in body), None)
    if hit:
        raise AccessBlocked(f"access restriction detected: {hit}")


def collect_search_items(page: Page, search_url: str, limit: int) -> list[SearchItem]:
    page.goto(search_url, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(3_000)
    detect_block(page)
    seen: dict[str, SearchItem] = {}
    idle_rounds = 0
    while len(seen) < limit and idle_rounds < 3:
        raw = page.locator('a[href*="/item/"]').evaluate_all(
            """els => els.map(a => ({href:a.href, text:(a.innerText||a.title||'').trim(),
               parent:(a.closest('[id^="g_"]')?.innerText||'').trim()}))"""
        )
        before = len(seen)
        for entry in raw:
            match = re.search(r"/(\d{7,})(?:[/?#]|$)", entry["href"])
            if not match:
                continue
            product_id = match.group(1)
            parent = entry["parent"]
            name = entry["text"].splitlines()[0].strip() if entry["text"] else ""
            if not name:
                lines = [line.strip() for line in parent.splitlines() if line.strip()]
                name = next((line for line in lines if "円" not in line), f"Qoo10 item {product_id}")
            seen.setdefault(product_id, SearchItem(product_id, name, entry["href"], normalize_price(parent)))
            if len(seen) >= limit:
                break
        idle_rounds = idle_rounds + 1 if len(seen) == before else 0
        if len(seen) < limit:
            more = page.get_by_text("もっと見る", exact=True)
            if more.count() and more.first.is_visible():
                more.first.click()
                page.wait_for_timeout(2_000)
            else:
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(1_500)
    if not seen:
        raise RuntimeError("search page loaded but no product links were found")
    return list(seen.values())[:limit]


def unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        cleaned = re.sub(r"\s+", " ", value).strip(" -|/\n\t")
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def extract_variants(page: Page) -> list[str]:
    colors = page.locator(
        '#ul_basic_option_list li.original span.option_img:not(.disabled), '
        '#ul_basic_option_list li:not(.original) span.option_img:not(.disabled)'
    )
    color_names = unique(colors.evaluate_all("els => els.map(e => e.dataset.itemName || e.innerText)"))
    combinations: list[str] = []
    for color_name in color_names:
        color = page.locator(
            f'#ul_basic_option_list span.option_img[data-item-name="{color_name}"]:not(.disabled)'
        ).first
        try:
            color.click(timeout=3_000)
            page.wait_for_timeout(250)
        except Exception:
            continue
        sizes = page.locator(
            '#div_detail_option_size .option_selectBox li:not(.sold_out) span.value[data-value], '
            '#div_detail_option_size .option_selectBox li:not(.sold_out) .option_text .value'
        ).evaluate_all("els => els.map(e => e.dataset.value || e.innerText)")
        sizes = unique(sizes)
        if sizes:
            combinations.extend(f"{color_name} / {size}" for size in sizes)
        else:
            combinations.append(color_name)
    if combinations:
        return unique(combinations)[:500]

    groups: list[list[str]] = []
    for option_box in page.locator('.option_selectBox ul').all():
        options = option_box.locator('li:not(.sold_out) span.value[data-value]').evaluate_all(
            "els => els.map(e => e.dataset.value || e.innerText)"
        )
        options = unique(options)
        if options:
            groups.append(options)
    if groups:
        return unique(" / ".join(parts) for parts in product(*groups))[:500]

    for select in page.locator("select").all():
        options = unique(select.locator("option").all_inner_texts())
        options = [v for v in options if not re.search(r"選択|option|choose|loading|品切|sold out", v, re.I)]
        if options:
            groups.append(options)
    return unique(" / ".join(parts) for parts in product(*groups))[:500] if groups else []


def extract_sale_price(page: Page, fallback: int | None) -> int | None:
    for selector in ('.after_price', '[class*="after_price"]', '.price_wrap .price', '.detail_price'):
        locator = page.locator(selector)
        if locator.count():
            price = normalize_price(locator.first.inner_text(timeout=3_000))
            if price is not None:
                return price
    return fallback


def extract_images(page: Page) -> list[str]:
    urls = page.locator("img").evaluate_all(
        """els => els.flatMap(img => [img.currentSrc, img.src, img.dataset?.src, img.dataset?.original])
            .filter(Boolean)"""
    )
    cleaned = []
    for url in unique(urls):
        if not re.search(r"image-qoo10|qoo10.*\.(?:jpg|jpeg|png|webp)", url, re.I):
            continue
        if re.search(r"logo|icon|banner|sprite|flag|seller", url, re.I):
            continue
        cleaned.append(url)
    return cleaned[:20]


def extract_description(page: Page, fallback: str) -> str:
    for selector in ('[id*="detail"]', '[class*="detail"]', '[class*="description"]'):
        locator = page.locator(selector)
        if locator.count():
            text = re.sub(r"\s+", " ", locator.first.inner_text(timeout=3_000)).strip()
            if len(text) >= 20:
                return text[:30_000]
    return fallback


def download_jpg(url: str, path: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.qoo10.jp/"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()
    with Image.open(io.BytesIO(payload)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((600, 600), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (600, 600), "white")
        canvas.paste(image, ((600 - image.width) // 2, (600 - image.height) // 2))
        canvas.save(path, "JPEG", quality=90, optimize=True)


def write_csv(path: Path, rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADER)
        writer.writerows(rows)


def run(config: dict[str, object]) -> int:
    output = Path(str(config.get("output_dir", "output"))).resolve()
    images_dir = output / "images"
    output.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(exist_ok=True)
    log_path = output / "run_log.jsonl"
    failures: list[Failure] = []
    rows: list[list[object]] = []
    start = time.monotonic()
    log_event(log_path, "start", search_url=config["search_url"])

    with sync_playwright() as playwright:
        launch = {"headless": bool(config.get("headless", False))}
        channel = str(config.get("browser_channel", "chrome")).strip()
        if channel:
            launch["channel"] = channel
        browser = playwright.chromium.launch(**launch)
        context = browser.new_context(locale="ja-JP", timezone_id="Asia/Tokyo", viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        try:
            items = collect_search_items(page, str(config["search_url"]), int(config.get("max_products", 10)))
            log_event(log_path, "search_complete", count=len(items))
            for index, item in enumerate(items, 1):
                try:
                    page.goto(item.url, wait_until="domcontentloaded", timeout=60_000)
                    page.wait_for_timeout(3_000)
                    detect_block(page)
                    variants = extract_variants(page)
                    if not variants:
                        raise RuntimeError("color/size variants were not exposed in the product DOM")
                    price = extract_sale_price(page, item.price_yen)
                    if price is None:
                        raise RuntimeError("sale price was not found")
                    image_urls = extract_images(page)
                    image_names: list[str] = []
                    for image_index, image_url in enumerate(image_urls, 1):
                        name = f"{item.product_id}_{image_index:02d}.jpg"
                        try:
                            download_jpg(image_url, images_dir / name)
                            image_names.append(name)
                        except Exception as exc:
                            log_event(log_path, "image_failed", product_id=item.product_id, url=image_url, error=str(exc))
                    description = str(config.get("description", ""))
                    padded_images = (image_names + [""] * 21)[:21]
                    for variant in variants:
                        rows.append([item.name, variant, description, price * 4, "", 10, 1, 1, 10, *padded_images])
                    log_event(log_path, "product_complete", product_id=item.product_id, variants=len(variants), images=len(image_names))
                except AccessBlocked as exc:
                    failures.append(Failure(item.product_id, item.url, "access", str(exc)))
                    log_event(log_path, "blocked", product_id=item.product_id, error=str(exc))
                    break
                except Exception as exc:
                    failures.append(Failure(item.product_id, item.url, "detail", str(exc)))
                    log_event(log_path, "product_failed", product_id=item.product_id, error=str(exc))
                if index < len(items):
                    page.wait_for_timeout(int(float(config.get("delay_seconds", 2.0)) * 1000))
        finally:
            context.close()
            browser.close()

    write_csv(output / "qoo10_sample.csv", rows)
    with (output / "failures.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["product_id", "url", "stage", "reason"])
        writer.writeheader()
        writer.writerows(asdict(failure) for failure in failures)
    summary = {
        "rows": len(rows), "failed_products": len(failures),
        "elapsed_seconds": round(time.monotonic() - start, 1),
        "images": len(list(images_dir.glob("*.jpg"))),
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    log_event(log_path, "finish", **summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if rows else 2


def load_config(path: Path) -> dict[str, object]:
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if not str(config.get("search_url", "")).startswith("https://www.qoo10.jp/"):
        raise ValueError("search_url must be an https://www.qoo10.jp/ URL")
    return config


def main() -> int:
    parser = argparse.ArgumentParser(description="Qoo10 public-page small-scale validation scraper")
    parser.add_argument("--config", default="config.json")
    args = parser.parse_args()
    try:
        return run(load_config(Path(args.config)))
    except (AccessBlocked, PlaywrightTimeoutError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
