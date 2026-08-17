#!/usr/bin/env python3
"""从平台官方公开页面同步模型价格，不发起任何付费调用。"""

from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
PRICING_PATH = ROOT / "data" / "model_capabilities" / "pricing.json"
RUNNINGHUB_STANDARD_URL = "https://www.runninghub.cn/call-api/search-api/standard-model"
RUNNINGHUB_LLM_URL = "https://www.runninghub.cn/call-api/llm/models"
SYNC_SOURCE_ID = "runninghub-official-catalog"


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "LaohuCanvasPricingSync/1.0"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def clean_html(value: str) -> str:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.S)
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def runninghub_profiles() -> list[dict[str, Any]]:
    try:
        catalog = json.loads(fetch_text("http://127.0.0.1:3000/api/model-capabilities"))
        provider = next((item for item in catalog.get("providers", []) if item.get("id") == "runninghub"), None)
        if provider:
            return list(provider.get("models") or [])
    except Exception:
        pass
    snapshot_path = ROOT / "data" / "model_capabilities" / "snapshots" / "runninghub-global.json"
    with snapshot_path.open("r", encoding="utf-8") as handle:
        snapshot = json.load(handle)
    node_types = {
        "text": "text_generation",
        "image": "image_generation",
        "video": "video_generation",
        "audio": "audio_generation",
    }
    return [
        {
            "model_id": item.get("name_en"),
            "display_name": item.get("name_cn") or item.get("display_name") or item.get("name_en"),
            "node_type": node_types.get(str(item.get("output_type") or "").lower(), ""),
        }
        for item in snapshot.get("items") or []
        if item.get("name_en")
    ]


def parse_standard_prices(page: str) -> dict[str, str]:
    prices: dict[str, str] = {}
    for chunk in page.split('<div class="api-list-item"')[1:]:
        name_match = re.search(r'<h3 class="api-list-item-name"[^>]*>(.*?)</h3>', chunk, re.S)
        if not name_match:
            continue
        name = clean_html(name_match.group(1))
        price_match = re.search(
            r'<span class="api-list-item-price-new"[^>]*>(.*?)</span>\s*<!--\]-->',
            chunk,
            re.S,
        )
        price = clean_html(price_match.group(1)) if price_match else ""
        if name and price:
            prices[name] = price
    return prices


def effective_tier_values(title: str) -> list[float]:
    values = []
    for line in html.unescape(title).splitlines():
        amounts = re.findall(r"[￥¥]([0-9]+(?:\.[0-9]+)?)", line)
        if amounts:
            values.append(float(amounts[-1]))
    return values


def range_text(values: list[float]) -> str:
    if not values:
        return ""
    low, high = min(values), max(values)
    format_number = lambda value: f"{value:g}"
    return format_number(low) if low == high else f"{format_number(low)}–{format_number(high)}"


def parse_llm_prices(page: str) -> dict[str, dict[str, Any]]:
    prices: dict[str, dict[str, Any]] = {}
    for chunk in page.split('<li class="llm-card"')[1:]:
        name_match = re.search(r'<span class="llm-card__display-name"[^>]*>(.*?)</span>', chunk, re.S)
        panels = re.findall(r'<div class="llm-card__price-panel" title="(.*?)"', chunk, re.S)
        if not name_match or len(panels) < 2:
            continue
        name = clean_html(name_match.group(1))
        input_values = effective_tier_values(panels[0])
        output_values = effective_tier_values(panels[1])
        if not input_values and not output_values:
            continue
        input_text = range_text(input_values)
        output_text = range_text(output_values)
        prices[name] = {
            "status": "tiered",
            "unit": "input_output_million_tokens",
            "display_zh": f"输入 ¥{input_text} / 输出 ¥{output_text}",
            "display_en": f"Input ¥{input_text} / output ¥{output_text}",
            "details_zh": "阶梯价格按本次输入上下文长度确定，单位为每百万 Token。",
            "details_en": "Tier prices depend on input context length and are billed per 1M tokens.",
            "input_amount_min": min(input_values) if input_values else None,
            "input_amount_max": max(input_values) if input_values else None,
            "output_amount_min": min(output_values) if output_values else None,
            "output_amount_max": max(output_values) if output_values else None,
        }
    return prices


def translated_price(raw_price: str) -> str:
    if raw_price == "免费":
        return "Free"
    result = raw_price.replace("￥", "¥").replace("仅需 ", "")
    result = result.replace(" ，分辨率不可控，介意请用官方版", " · resolution not guaranteed")
    replacements = {
        "/1000字符": " / 1K characters",
        "/1000字": " / 1K characters",
        "/5秒": " / 5 sec",
        "/秒": " / sec",
        "/张": " / image",
        "/次": " / run",
        "按调用次数计费。 ": "",
    }
    for source, target in replacements.items():
        result = result.replace(source, target)
    return result


def standard_record(raw_price: str, node_type: str) -> dict[str, Any]:
    if raw_price == "免费":
        return {
            "status": "free",
            "unit": "run",
            "amount": 0,
            "display_zh": "免费",
            "display_en": "Free",
        }
    amount_match = re.search(r"[￥¥]([0-9]+(?:\.[0-9]+)?)", raw_price)
    if not amount_match:
        return {
            "status": "dynamic",
            "display_zh": raw_price,
            "display_en": translated_price(raw_price),
        }
    if "/1000" in raw_price:
        unit = "thousand_characters"
    elif "/5秒" in raw_price:
        unit = "video_5_seconds"
    elif "/秒" in raw_price:
        unit = "video_second" if node_type == "video_generation" else "audio_second"
    elif "/张" in raw_price:
        unit = "image"
    elif "/次" in raw_price:
        unit = "run"
    elif node_type == "image_generation":
        unit = "image"
    elif node_type == "music_generation":
        unit = "music_run"
    else:
        unit = "run"
    return {
        "status": "confirmed",
        "currency": "CNY",
        "amount": float(amount_match.group(1)),
        "unit": unit,
        "display_zh": raw_price.replace("￥", "¥"),
        "display_en": translated_price(raw_price),
    }


def load_pricing() -> dict[str, Any]:
    with PRICING_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    pricing = load_pricing()
    profiles = runninghub_profiles()
    standard_prices = parse_standard_prices(fetch_text(RUNNINGHUB_STANDARD_URL))
    llm_prices = parse_llm_prices(fetch_text(RUNNINGHUB_LLM_URL))
    entries = {
        key: value
        for key, value in (pricing.get("entries") or {}).items()
        if value.get("source_id") != SYNC_SOURCE_ID
    }
    matched_standard = 0
    matched_llm = 0
    for profile in profiles:
        model_id = str(profile.get("model_id") or "").strip()
        display_name = str(profile.get("display_name") or model_id).strip()
        node_type = str(profile.get("node_type") or "").strip()
        record = None
        if display_name in standard_prices:
            record = standard_record(standard_prices[display_name], node_type)
            record["source_price_text"] = standard_prices[display_name]
            record["source_url"] = RUNNINGHUB_STANDARD_URL
            matched_standard += 1
        elif model_id in llm_prices or display_name in llm_prices:
            record = dict(llm_prices.get(model_id) or llm_prices[display_name])
            record["source_url"] = RUNNINGHUB_LLM_URL
            matched_llm += 1
        if record is None:
            continue
        record.update({
            "provider_id": "runninghub",
            "model_id": model_id,
            "source_id": SYNC_SOURCE_ID,
            "source_label_zh": "RunningHub 官方公开价格",
            "source_label_en": "RunningHub official public price",
            "checked_at": date.today().isoformat(),
        })
        entries[f"runninghub:{model_id}"] = record
    pricing["updated_at"] = date.today().isoformat()
    pricing["entries"] = dict(sorted(entries.items()))
    pricing.setdefault("sync", {})[SYNC_SOURCE_ID] = {
        "checked_at": date.today().isoformat(),
        "standard_models_matched": matched_standard,
        "llm_models_matched": matched_llm,
        "source_urls": [RUNNINGHUB_STANDARD_URL, RUNNINGHUB_LLM_URL],
    }
    with PRICING_PATH.open("w", encoding="utf-8") as handle:
        json.dump(pricing, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"RunningHub 官方价格同步完成：标准模型 {matched_standard} 个，文本模型 {matched_llm} 个。")


if __name__ == "__main__":
    main()
