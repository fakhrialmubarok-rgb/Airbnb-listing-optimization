"""
photo_regen_free.py — Multi-backend photo regeneration with 14+ AI engines

BACKEND CHAIN (tries in order, first success wins):
  REPLICATE  (token: REPLICATE_API_TOKEN)
    1. replicate_flux_dev   — FLUX.1-dev img2img (best Western open model)
    2. replicate_kolors     — Kolors by Kwai/Kuaishou 可图 (top Chinese model)
    3. replicate_hunyuan    — HunyuanDiT by Tencent 混元 (Chinese)
    4. replicate_sdxl       — SDXL img2img (reliable fallback)
    5. replicate_playground — Playground v2.5 (high aesthetic quality)

  HUGGING FACE  (token: HF_TOKEN)
    6. hf_flux_dev          — FLUX.1-dev on HF Inference
    7. hf_kolors            — Kolors by Kwai on HF Inference
    8. hf_sdxl              — SDXL on HF Inference

  FAL.AI  (token: FAL_KEY)
    9. fal_flux             — FLUX img2img on fal.ai (fast free credits)

  TOGETHER.AI  (token: TOGETHER_API_KEY)
   10. together_flux        — FLUX.1 on Together.ai (free credits)

  CHINESE AI — DIRECT APIs
   11. dashscope_wanx       — Alibaba Tongyi Wanxiang 通义万象 (DASHSCOPE_API_KEY)
                              Free 100 images/mo → https://dashscope.aliyun.com
   12. zhipu_cogview        — ZhipuAI CogView-3 智谱 (ZHIPU_API_KEY)
                              Free tier → https://open.bigmodel.cn
   13. siliconflow_flux     — SiliconFlow FLUX (free Chinese hosting, SILICONFLOW_API_KEY)
                              https://cloud.siliconflow.cn — very generous free tier
   14. novita_sdxl          — Novita.ai SDXL img2img (NOVITA_API_KEY, $0.002/image)

  STABILITY AI  (token: STABILITY_API_KEY)
   15. stability_sd3        — Stable Diffusion 3 via Stability AI API

ENVIRONMENT (.env):
  REPLICATE_API_TOKEN=r8_...
  HF_TOKEN=hf_...
  FAL_KEY=...
  TOGETHER_API_KEY=...
  DASHSCOPE_API_KEY=...      # Alibaba Cloud
  ZHIPU_API_KEY=...          # ZhipuAI bigmodel.cn
  SILICONFLOW_API_KEY=...    # cloud.siliconflow.cn (free)
  NOVITA_API_KEY=...
  STABILITY_API_KEY=...

Usage:
  python photo_regen_free.py --listing-dir /tmp/listingboost_photos/20669368_Tanya
  python photo_regen_free.py --retry-missing --results-dir /tmp/regen_results/20669368_Tanya
  python photo_regen_free.py --backend replicate_flux_dev --max-photos 3
  python photo_regen_free.py --list-backends
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import io
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

RESULTS_DIR = Path("/tmp/regen_results")
RESULTS_DIR.mkdir(exist_ok=True)

# ─── Tokens ───────────────────────────────────────────────────────────────────
REPLICATE_TOKEN    = os.getenv("REPLICATE_API_TOKEN", "")
HF_TOKEN           = os.getenv("HF_TOKEN", "")
FAL_KEY            = os.getenv("FAL_KEY", "")
TOGETHER_KEY       = os.getenv("TOGETHER_API_KEY", "")
DASHSCOPE_KEY      = os.getenv("DASHSCOPE_API_KEY", "")
ZHIPU_KEY          = os.getenv("ZHIPU_API_KEY", "")
SILICONFLOW_KEY    = os.getenv("SILICONFLOW_API_KEY", "")
NOVITA_KEY         = os.getenv("NOVITA_API_KEY", "")
STABILITY_KEY      = os.getenv("STABILITY_API_KEY", "")


# ─── ML strategy ──────────────────────────────────────────────────────────────
def _load_ml_strategy() -> dict:
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from learning_store import get_strategy
        kill_list  = json.loads(get_strategy("regen", "variant_kill_list") or "[]")
        priority   = json.loads(get_strategy("regen", "variant_priority") or "[]")
        min_pres   = float(get_strategy("regen", "qc_min_preserve") or "8.1")
        return {"kill_list": kill_list, "priority": priority, "min_preserve": min_pres}
    except Exception as e:
        print(f"  [ml] Could not read learning.db: {e}")
        return {"kill_list": ["candlelight_evening", "moody_warm"], "priority": [], "min_preserve": 8.1}


# ─── Prompt variants ──────────────────────────────────────────────────────────
PROMPT_VARIANTS = [
    {"id": "wider_angle",     "category": "composition", "strength": 0.35,
     "prompt": "Professional Airbnb listing photo, same room same furniture same layout, wider angle shot showing more of the room, warm soft natural window light, bright and airy, clean composition. Do not change or add furniture."},
    {"id": "blue_hour",       "category": "lighting",    "strength": 0.40,
     "prompt": "Professional Airbnb exterior/patio photo at blue hour dusk, same layout same furniture preserved, warm glowing interior lights visible through windows, dramatic deep blue sky, cozy Alpine atmosphere. Preserve all objects exactly."},
    {"id": "rule_of_thirds",  "category": "composition", "strength": 0.32,
     "prompt": "Professional interior photo using rule of thirds composition, same room same furniture, warm natural window light, bright airy feel, hospitality photography quality. Nothing added or removed."},
    {"id": "nordic_minimal",  "category": "style",       "strength": 0.33,
     "prompt": "Scandinavian minimal interior photography, same room same furniture preserved, clean bright diffused natural light, bright white balance, airy spacious feel. Do not change furniture."},
    {"id": "airbnb_plus",     "category": "style",       "strength": 0.35,
     "prompt": "Airbnb Plus tier listing photo quality, same furniture same room exactly, professional bright hospitality lighting, editorial composition, warm and inviting, luxury short-term rental aesthetic. Bright not dark."},
    {"id": "warm_window",     "category": "lighting",    "strength": 0.35,
     "prompt": "Professional Airbnb listing photo, same room same furniture same layout, warm soft natural light streaming from left window, golden afternoon glow, bright and airy. Keep all furniture exactly as-is."},
    {"id": "overcast_clean",  "category": "lighting",    "strength": 0.30,
     "prompt": "Professional interior photo, same room same furniture, soft diffused natural light, bright and airy, no harsh shadows, clean white balance, bright hospitality feel. Do not move or add any furniture."},
    {"id": "boutique_hotel",  "category": "style",       "strength": 0.35,
     "prompt": "Boutique hotel photography quality, same room same furniture preserved, professional bright hospitality lighting, warm and inviting, bright not dark. The Airbnb guest must feel they want to book this immediately."},
    {"id": "alpine_luxury",   "category": "style",       "strength": 0.35,
     "prompt": "Swiss Alpine luxury chalet interior photography style, same furniture and room layout preserved, warm wood tones enhanced, soft bright natural window light, cozy premium feel. Like a 5-star Zermatt chalet brochure, bright not dark."},
    {"id": "symmetry",        "category": "composition", "strength": 0.30,
     "prompt": "Architectural symmetrical composition, same room same furniture layout, centered framing, warm diffused natural bright light, magazine-quality interior photography. Nothing added or removed."},
    {"id": "hdr_natural",     "category": "technical",   "strength": 0.28,
     "prompt": "Natural HDR interior photo, balanced exposure, no blown highlights, deep shadows lifted, same room furniture preserved, warm color grade, bright airy result."},
    {"id": "bright_airy",     "category": "technical",   "strength": 0.30,
     "prompt": "Bright airy interior photo, lifted shadows, warm whites, clean and fresh feel, same room layout and furniture exactly preserved. Professional real estate photography, bright not dark."},
    {"id": "golden_hour",     "category": "lighting",    "strength": 0.38,
     "prompt": "Professional real estate photo, same room same furniture, warm golden hour sunlight from window, soft shadows, bright and airy, hospitality photography quality. Do not change furniture."},
    {"id": "wider_angle_v2",  "category": "composition", "strength": 0.33,
     "prompt": "Real estate wide-angle interior shot showing maximum room space, same furniture same objects, bright clean natural light, professional property photography. Wider field of view than original."},
]

NEGATIVE_PROMPT = (
    "dark, moody, dim lighting, night scene without ambient, blurry, distorted, "
    "extra furniture, missing furniture, different room layout, oversaturated, "
    "artificial looking, painting style, cartoon, watermark, text, logo"
)


# ─── Image helpers ─────────────────────────────────────────────────────────────
def _detect_mime(data: bytes) -> str:
    h = data[:12]
    if h[:4] == b'RIFF' and h[8:12] == b'WEBP':
        return "image/webp"
    if h[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    return "image/jpeg"


def _to_png_bytes(path: Path, max_px: int = 1024) -> bytes:
    """Load any image (incl WebP), resize to max_px, return PNG bytes."""
    from PIL import Image as PILImage
    img = PILImage.open(path).convert("RGB")
    img.thumbnail((max_px, max_px), PILImage.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _to_b64_datauri(path: Path, max_px: int = 1024) -> str:
    data = _to_png_bytes(path, max_px)
    return f"data:image/png;base64,{base64.b64encode(data).decode()}"


def _to_b64(path: Path, max_px: int = 1024) -> str:
    return base64.b64encode(_to_png_bytes(path, max_px)).decode()


# ─── Replicate helpers ─────────────────────────────────────────────────────────
def _replicate_post(endpoint: str, payload: dict, timeout: int = 120) -> tuple[bool, str]:
    """POST to Replicate, poll until done, return (ok, result_url_or_error)."""
    if not REPLICATE_TOKEN:
        return False, "REPLICATE_API_TOKEN not set"
    headers = {
        "Authorization": f"Token {REPLICATE_TOKEN}",
        "Content-Type": "application/json",
        "Prefer": "wait=55",
    }
    r = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
    if r.status_code not in (200, 201):
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
    result = r.json()
    # poll if still running
    if result.get("status") not in ("succeeded", "failed", "canceled"):
        pred_id = result["id"]
        poll_hdrs = {"Authorization": f"Token {REPLICATE_TOKEN}"}
        for _ in range(40):
            time.sleep(8)
            pr = requests.get(f"https://api.replicate.com/v1/predictions/{pred_id}", headers=poll_hdrs, timeout=30)
            result = pr.json()
            if result.get("status") in ("succeeded", "failed", "canceled"):
                break
    if result.get("status") != "succeeded":
        return False, f"Replicate error: {result.get('error','unknown')}"
    output = result.get("output", [])
    url = output[0] if isinstance(output, list) else output
    if not url:
        return False, "No output URL"
    return True, url


def _download_to(url: str, out_path: Path) -> bool:
    r = requests.get(url, timeout=60)
    if r.status_code != 200:
        return False
    out_path.write_bytes(r.content)
    return True


# ══════════════════════════════════════════════════════════════════════════════
# BACKEND IMPLEMENTATIONS
# ══════════════════════════════════════════════════════════════════════════════

# 1. FLUX.1-dev on Replicate (best quality open model)
def _backend_replicate_flux_dev(photo_path: Path, variant: dict, out_dir: Path) -> tuple[bool, str]:
    data_uri = _to_b64_datauri(photo_path)
    # Use model-slug API (no version pinning needed)
    payload = {"input": {
        "image":              data_uri,
        "prompt":             variant["prompt"],
        "strength":           variant.get("strength", 0.35),
        "num_inference_steps": 28,
        "guidance":           3.5,
    }}
    ok, result = _replicate_post(
        "https://api.replicate.com/v1/models/black-forest-labs/flux-dev/predictions",
        payload
    )
    if not ok:
        return False, result
    out_path = out_dir / "output.png"
    if _download_to(result, out_path):
        return True, str(out_path)
    return False, f"Download failed: {result}"


# 2. Kolors by Kwai/Kuaishou 可图 on Replicate (top Chinese model, SDXL++ quality)
def _backend_replicate_kolors(photo_path: Path, variant: dict, out_dir: Path) -> tuple[bool, str]:
    data_uri = _to_b64_datauri(photo_path)
    payload = {"input": {
        "image":               data_uri,
        "prompt":              variant["prompt"],
        "negative_prompt":     NEGATIVE_PROMPT,
        "strength":            variant.get("strength", 0.35),
        "num_inference_steps": 50,
        "guidance_scale":      5.0,
    }}
    ok, result = _replicate_post(
        "https://api.replicate.com/v1/models/lucataco/kolors/predictions",
        payload
    )
    if not ok:
        return False, result
    out_path = out_dir / "output.png"
    if _download_to(result, out_path):
        return True, str(out_path)
    return False, f"Download failed: {result}"


# 3. HunyuanDiT by Tencent 混元 on Replicate (Chinese DiT model)
def _backend_replicate_hunyuan(photo_path: Path, variant: dict, out_dir: Path) -> tuple[bool, str]:
    data_uri = _to_b64_datauri(photo_path)
    payload = {"input": {
        "image":               data_uri,
        "prompt":              variant["prompt"],
        "negative_prompt":     NEGATIVE_PROMPT,
        "image_strength":      1.0 - variant.get("strength", 0.35),  # inverted
        "num_inference_steps": 50,
        "guidance_scale":      6.0,
    }}
    ok, result = _replicate_post(
        "https://api.replicate.com/v1/models/tencent/hunyuan-dit/predictions",
        payload
    )
    if not ok:
        return False, result
    out_path = out_dir / "output.png"
    if _download_to(result, out_path):
        return True, str(out_path)
    return False, f"Download failed: {result}"


# 4. SDXL on Replicate (reliable workhorse)
def _backend_replicate_sdxl(photo_path: Path, variant: dict, out_dir: Path) -> tuple[bool, str]:
    data_uri = _to_b64_datauri(photo_path)
    payload = {"input": {
        "image":               data_uri,
        "prompt":              variant["prompt"],
        "negative_prompt":     NEGATIVE_PROMPT,
        "prompt_strength":     variant.get("strength", 0.35),
        "num_inference_steps": 30,
        "guidance_scale":      7.5,
        "scheduler":           "K_EULER",
        "apply_watermark":     False,
    }}
    ok, result = _replicate_post(
        "https://api.replicate.com/v1/models/stability-ai/sdxl/predictions",
        payload
    )
    if not ok:
        return False, result
    out_path = out_dir / "output.png"
    if _download_to(result, out_path):
        return True, str(out_path)
    return False, f"Download failed: {result}"


# 5. Playground v2.5 on Replicate (highest aesthetic scores in benchmarks)
def _backend_replicate_playground(photo_path: Path, variant: dict, out_dir: Path) -> tuple[bool, str]:
    data_uri = _to_b64_datauri(photo_path)
    payload = {"input": {
        "image":               data_uri,
        "prompt":              variant["prompt"],
        "negative_prompt":     NEGATIVE_PROMPT,
        "strength":            variant.get("strength", 0.35),
        "num_inference_steps": 50,
        "guidance_scale":      3.0,
    }}
    ok, result = _replicate_post(
        "https://api.replicate.com/v1/models/playgroundai/playground-v2-5-1024px-aesthetic/predictions",
        payload
    )
    if not ok:
        return False, result
    out_path = out_dir / "output.png"
    if _download_to(result, out_path):
        return True, str(out_path)
    return False, f"Download failed: {result}"


# 6. FLUX.1-dev on HuggingFace Inference
def _backend_hf_flux_dev(photo_path: Path, variant: dict, out_dir: Path) -> tuple[bool, str]:
    if not HF_TOKEN:
        return False, "HF_TOKEN not set"
    png_bytes = _to_png_bytes(photo_path)
    b64img = base64.b64encode(png_bytes).decode()
    url = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-dev"
    payload = {
        "inputs": variant["prompt"],
        "parameters": {
            "image": b64img,
            "strength": variant.get("strength", 0.35),
            "num_inference_steps": 28,
            "guidance_scale": 3.5,
            "negative_prompt": NEGATIVE_PROMPT,
        }
    }
    r = requests.post(url, headers={"Authorization": f"Bearer {HF_TOKEN}"}, json=payload, timeout=120)
    if r.status_code != 200:
        return False, f"HF HTTP {r.status_code}: {r.text[:200]}"
    out_path = out_dir / "output.png"
    out_path.write_bytes(r.content)
    return True, str(out_path)


# 7. Kolors by Kwai on HuggingFace Inference
def _backend_hf_kolors(photo_path: Path, variant: dict, out_dir: Path) -> tuple[bool, str]:
    if not HF_TOKEN:
        return False, "HF_TOKEN not set"
    png_bytes = _to_png_bytes(photo_path)
    b64img = base64.b64encode(png_bytes).decode()
    url = "https://api-inference.huggingface.co/models/Kwai-Kolors/Kolors"
    payload = {
        "inputs": variant["prompt"],
        "parameters": {
            "image": b64img,
            "strength": variant.get("strength", 0.35),
            "num_inference_steps": 50,
            "negative_prompt": NEGATIVE_PROMPT,
        }
    }
    r = requests.post(url, headers={"Authorization": f"Bearer {HF_TOKEN}"}, json=payload, timeout=180)
    if r.status_code != 200:
        return False, f"HF Kolors HTTP {r.status_code}: {r.text[:200]}"
    out_path = out_dir / "output.png"
    out_path.write_bytes(r.content)
    return True, str(out_path)


# 8. SDXL on HuggingFace Inference
def _backend_hf_sdxl(photo_path: Path, variant: dict, out_dir: Path) -> tuple[bool, str]:
    if not HF_TOKEN:
        return False, "HF_TOKEN not set"
    png_bytes = _to_png_bytes(photo_path)
    b64img = base64.b64encode(png_bytes).decode()
    url = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
    payload = {
        "inputs": variant["prompt"],
        "parameters": {
            "image": b64img,
            "strength": variant.get("strength", 0.35),
            "num_inference_steps": 30,
            "negative_prompt": NEGATIVE_PROMPT,
        }
    }
    r = requests.post(url, headers={"Authorization": f"Bearer {HF_TOKEN}"}, json=payload, timeout=120)
    if r.status_code != 200:
        return False, f"HF SDXL HTTP {r.status_code}: {r.text[:200]}"
    out_path = out_dir / "output.png"
    out_path.write_bytes(r.content)
    return True, str(out_path)


# 9. fal.ai FLUX img2img (fast, generous free credits)
def _backend_fal_flux(photo_path: Path, variant: dict, out_dir: Path) -> tuple[bool, str]:
    if not FAL_KEY:
        return False, "FAL_KEY not set"
    b64img = _to_b64(photo_path)
    data_uri = f"data:image/png;base64,{b64img}"
    payload = {
        "image_url": data_uri,
        "prompt": variant["prompt"],
        "negative_prompt": NEGATIVE_PROMPT,
        "strength": variant.get("strength", 0.35),
        "num_inference_steps": 28,
        "guidance_scale": 3.5,
    }
    r = requests.post(
        "https://fal.run/fal-ai/flux/dev/image-to-image",
        headers={"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    if r.status_code != 200:
        return False, f"fal.ai HTTP {r.status_code}: {r.text[:200]}"
    result = r.json()
    img_url = (result.get("images") or [{}])[0].get("url", "")
    if not img_url:
        return False, f"No image URL in fal.ai response: {result}"
    out_path = out_dir / "output.png"
    if _download_to(img_url, out_path):
        return True, str(out_path)
    return False, "Download failed"


# 10. Together.ai FLUX img2img
def _backend_together_flux(photo_path: Path, variant: dict, out_dir: Path) -> tuple[bool, str]:
    if not TOGETHER_KEY:
        return False, "TOGETHER_API_KEY not set"
    b64img = _to_b64(photo_path)
    payload = {
        "model":  "black-forest-labs/FLUX.1-dev",
        "prompt": variant["prompt"],
        "image_base64": b64img,
        "strength": variant.get("strength", 0.35),
        "steps":  28,
        "n": 1,
    }
    r = requests.post(
        "https://api.together.xyz/v1/images/generations",
        headers={"Authorization": f"Bearer {TOGETHER_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    if r.status_code != 200:
        return False, f"Together HTTP {r.status_code}: {r.text[:200]}"
    result = r.json()
    b64out = (result.get("data") or [{}])[0].get("b64_json", "")
    if not b64out:
        url = (result.get("data") or [{}])[0].get("url", "")
        if url:
            out_path = out_dir / "output.png"
            if _download_to(url, out_path):
                return True, str(out_path)
        return False, f"No output in Together response: {result}"
    out_path = out_dir / "output.png"
    out_path.write_bytes(base64.b64decode(b64out))
    return True, str(out_path)


# 11. Alibaba Tongyi Wanxiang 通义万象 img2img
#     Sign up: https://dashscope.aliyun.com  Free: 100 img/mo  Model: wanx2.1-i2i-plus
def _backend_dashscope_wanx(photo_path: Path, variant: dict, out_dir: Path) -> tuple[bool, str]:
    if not DASHSCOPE_KEY:
        return False, "DASHSCOPE_API_KEY not set"
    b64img = _to_b64(photo_path)
    payload = {
        "model": "wanx2.1-i2i-plus",
        "input": {
            "base_image_url": f"data:image/png;base64,{b64img}",
            "prompt": variant["prompt"],
            "negative_prompt": NEGATIVE_PROMPT,
        },
        "parameters": {
            "strength": variant.get("strength", 0.35),
            "n": 1,
            "size": "1024*1024",
        }
    }
    r = requests.post(
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generation",
        headers={
            "Authorization": f"Bearer {DASHSCOPE_KEY}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        },
        json=payload, timeout=30,
    )
    if r.status_code not in (200, 201):
        return False, f"DashScope HTTP {r.status_code}: {r.text[:200]}"
    result = r.json()
    task_id = result.get("output", {}).get("task_id")
    if not task_id:
        return False, f"No task_id: {result}"
    # Poll
    for _ in range(30):
        time.sleep(8)
        pr = requests.get(
            f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}",
            headers={"Authorization": f"Bearer {DASHSCOPE_KEY}"},
            timeout=30,
        )
        pj = pr.json()
        status = pj.get("output", {}).get("task_status", "")
        if status == "SUCCEEDED":
            img_url = pj["output"]["results"][0]["url"]
            out_path = out_dir / "output.png"
            if _download_to(img_url, out_path):
                return True, str(out_path)
            return False, "Download failed"
        if status in ("FAILED", "CANCELED"):
            return False, f"DashScope task {status}: {pj}"
    return False, "DashScope timeout"


# 12. ZhipuAI CogView-3 智谱 (best Chinese text→image, also does img variation)
#     Sign up: https://open.bigmodel.cn  Free tier available
def _backend_zhipu_cogview(photo_path: Path, variant: dict, out_dir: Path) -> tuple[bool, str]:
    if not ZHIPU_KEY:
        return False, "ZHIPU_API_KEY not set"
    b64img = _to_b64(photo_path)
    # CogView-3-Plus supports image reference via base64
    payload = {
        "model": "cogview-3-plus",
        "prompt": variant["prompt"],
        "image_base64": b64img,
        "size": "1024x1024",
        "quality": "standard",
        "n": 1,
    }
    r = requests.post(
        "https://open.bigmodel.cn/api/paas/v4/images/generations",
        headers={"Authorization": f"Bearer {ZHIPU_KEY}", "Content-Type": "application/json"},
        json=payload, timeout=120,
    )
    if r.status_code != 200:
        return False, f"ZhipuAI HTTP {r.status_code}: {r.text[:200]}"
    result = r.json()
    img_url = (result.get("data") or [{}])[0].get("url", "")
    b64out  = (result.get("data") or [{}])[0].get("b64_json", "")
    if b64out:
        out_path = out_dir / "output.png"
        out_path.write_bytes(base64.b64decode(b64out))
        return True, str(out_path)
    if img_url:
        out_path = out_dir / "output.png"
        if _download_to(img_url, out_path):
            return True, str(out_path)
    return False, f"ZhipuAI: no output URL: {result}"


# 13. SiliconFlow FLUX (Chinese cloud, very generous free tier)
#     Sign up: https://cloud.siliconflow.cn  ~¥14 free credits = hundreds of images
def _backend_siliconflow_flux(photo_path: Path, variant: dict, out_dir: Path) -> tuple[bool, str]:
    if not SILICONFLOW_KEY:
        return False, "SILICONFLOW_API_KEY not set"
    b64img = _to_b64(photo_path)
    payload = {
        "model": "black-forest-labs/FLUX.1-dev",
        "prompt": variant["prompt"],
        "negative_prompt": NEGATIVE_PROMPT,
        "image": f"data:image/png;base64,{b64img}",
        "strength": variant.get("strength", 0.35),
        "num_inference_steps": 28,
        "guidance_scale": 3.5,
        "batch_size": 1,
        "image_size": "1024x1024",
    }
    r = requests.post(
        "https://api.siliconflow.cn/v1/image/generations",
        headers={"Authorization": f"Bearer {SILICONFLOW_KEY}", "Content-Type": "application/json"},
        json=payload, timeout=120,
    )
    if r.status_code != 200:
        return False, f"SiliconFlow HTTP {r.status_code}: {r.text[:200]}"
    result = r.json()
    img_url = (result.get("images") or [{}])[0].get("url", "")
    b64out  = (result.get("images") or [{}])[0].get("b64_json", "")
    if b64out:
        out_path = out_dir / "output.png"
        out_path.write_bytes(base64.b64decode(b64out))
        return True, str(out_path)
    if img_url:
        out_path = out_dir / "output.png"
        if _download_to(img_url, out_path):
            return True, str(out_path)
    return False, f"SiliconFlow: no output: {result}"


# 14. Novita.ai SDXL img2img (~$0.002/image, OpenAI-compatible)
def _backend_novita_sdxl(photo_path: Path, variant: dict, out_dir: Path) -> tuple[bool, str]:
    if not NOVITA_KEY:
        return False, "NOVITA_API_KEY not set"
    b64img = _to_b64(photo_path)
    payload = {
        "model_name": "sdxl/realvisxlV40_v40Bakedvae_154205.safetensors",
        "image_base64": b64img,
        "prompt": variant["prompt"],
        "negative_prompt": NEGATIVE_PROMPT,
        "denoising_strength": variant.get("strength", 0.35),
        "steps": 30,
        "cfg_scale": 7.5,
        "sampler_name": "DPM++ 2M Karras",
        "width": 1024,
        "height": 1024,
    }
    r = requests.post(
        "https://api.novita.ai/v3/async/img2img",
        headers={"Authorization": f"Bearer {NOVITA_KEY}", "Content-Type": "application/json"},
        json=payload, timeout=30,
    )
    if r.status_code not in (200, 201):
        return False, f"Novita HTTP {r.status_code}: {r.text[:200]}"
    task_id = r.json().get("task_id")
    if not task_id:
        return False, f"No task_id: {r.json()}"
    for _ in range(30):
        time.sleep(6)
        pr = requests.get(
            f"https://api.novita.ai/v3/async/task-result?task_id={task_id}",
            headers={"Authorization": f"Bearer {NOVITA_KEY}"},
            timeout=30,
        )
        pj = pr.json()
        status = pj.get("task", {}).get("status", "")
        if status == "TASK_STATUS_SUCCEED":
            b64out = pj["images"][0]["image_base64"]
            out_path = out_dir / "output.png"
            out_path.write_bytes(base64.b64decode(b64out))
            return True, str(out_path)
        if "FAIL" in status or "ERROR" in status:
            return False, f"Novita task failed: {pj}"
    return False, "Novita timeout"


# 15. Stability AI SD3 (via Stability API)
def _backend_stability_sd3(photo_path: Path, variant: dict, out_dir: Path) -> tuple[bool, str]:
    if not STABILITY_KEY:
        return False, "STABILITY_API_KEY not set"
    png_bytes = _to_png_bytes(photo_path)
    strength = variant.get("strength", 0.35)
    files = {
        "init_image": ("init.png", io.BytesIO(png_bytes), "image/png"),
    }
    data = {
        "init_image_mode": "IMAGE_STRENGTH",
        "image_strength": 1.0 - strength,
        "text_prompts[0][text]": variant["prompt"],
        "text_prompts[0][weight]": "1",
        "text_prompts[1][text]": NEGATIVE_PROMPT,
        "text_prompts[1][weight]": "-1",
        "cfg_scale": "7",
        "steps": "30",
        "engine": "stable-diffusion-xl-1024-v1-0",
    }
    r = requests.post(
        "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/image-to-image",
        headers={"Authorization": f"Bearer {STABILITY_KEY}", "Accept": "application/json"},
        files=files, data=data, timeout=120,
    )
    if r.status_code != 200:
        return False, f"Stability HTTP {r.status_code}: {r.text[:200]}"
    result = r.json()
    b64out = (result.get("artifacts") or [{}])[0].get("base64", "")
    if not b64out:
        return False, f"No base64 in Stability response: {result}"
    out_path = out_dir / "output.png"
    out_path.write_bytes(base64.b64decode(b64out))
    return True, str(out_path)


# ─── Backend registry ──────────────────────────────────────────────────────────
BACKENDS: list[tuple[str, Callable, Callable]] = [
    # (id, fn, available_check)
    ("replicate_flux_dev",   _backend_replicate_flux_dev,   lambda: bool(REPLICATE_TOKEN)),
    ("replicate_kolors",     _backend_replicate_kolors,     lambda: bool(REPLICATE_TOKEN)),
    ("replicate_hunyuan",    _backend_replicate_hunyuan,    lambda: bool(REPLICATE_TOKEN)),
    ("replicate_sdxl",       _backend_replicate_sdxl,       lambda: bool(REPLICATE_TOKEN)),
    ("replicate_playground", _backend_replicate_playground, lambda: bool(REPLICATE_TOKEN)),
    ("hf_flux_dev",          _backend_hf_flux_dev,          lambda: bool(HF_TOKEN)),
    ("hf_kolors",            _backend_hf_kolors,            lambda: bool(HF_TOKEN)),
    ("hf_sdxl",              _backend_hf_sdxl,              lambda: bool(HF_TOKEN)),
    ("fal_flux",             _backend_fal_flux,             lambda: bool(FAL_KEY)),
    ("together_flux",        _backend_together_flux,        lambda: bool(TOGETHER_KEY)),
    ("siliconflow_flux",     _backend_siliconflow_flux,     lambda: bool(SILICONFLOW_KEY)),
    ("dashscope_wanx",       _backend_dashscope_wanx,       lambda: bool(DASHSCOPE_KEY)),
    ("zhipu_cogview",        _backend_zhipu_cogview,        lambda: bool(ZHIPU_KEY)),
    ("novita_sdxl",          _backend_novita_sdxl,          lambda: bool(NOVITA_KEY)),
    ("stability_sd3",        _backend_stability_sd3,        lambda: bool(STABILITY_KEY)),
]
BACKEND_MAP = {b[0]: b for b in BACKENDS}


def list_backends() -> None:
    print("\nAvailable backends (15 total):\n")
    print(f"  {'ID':30s} {'TOKEN':25s} {'STATUS'}")
    print(f"  {'-'*30} {'-'*25} {'-'*10}")
    checks = {
        "replicate_flux_dev":   (REPLICATE_TOKEN, "REPLICATE_API_TOKEN"),
        "replicate_kolors":     (REPLICATE_TOKEN, "REPLICATE_API_TOKEN"),
        "replicate_hunyuan":    (REPLICATE_TOKEN, "REPLICATE_API_TOKEN"),
        "replicate_sdxl":       (REPLICATE_TOKEN, "REPLICATE_API_TOKEN"),
        "replicate_playground": (REPLICATE_TOKEN, "REPLICATE_API_TOKEN"),
        "hf_flux_dev":          (HF_TOKEN,        "HF_TOKEN"),
        "hf_kolors":            (HF_TOKEN,        "HF_TOKEN"),
        "hf_sdxl":              (HF_TOKEN,        "HF_TOKEN"),
        "fal_flux":             (FAL_KEY,         "FAL_KEY"),
        "together_flux":        (TOGETHER_KEY,    "TOGETHER_API_KEY"),
        "siliconflow_flux":     (SILICONFLOW_KEY, "SILICONFLOW_API_KEY"),
        "dashscope_wanx":       (DASHSCOPE_KEY,   "DASHSCOPE_API_KEY"),
        "zhipu_cogview":        (ZHIPU_KEY,       "ZHIPU_API_KEY"),
        "novita_sdxl":          (NOVITA_KEY,      "NOVITA_API_KEY"),
        "stability_sd3":        (STABILITY_KEY,   "STABILITY_API_KEY"),
    }
    for bid, (token, env_name) in checks.items():
        status = "✓ READY" if token else "✗ need " + env_name
        print(f"  {bid:30s} {env_name:25s} {status}")
    print()
    ready = sum(1 for t,_ in checks.values() if t)
    print(f"  {ready}/15 backends ready\n")


# ─── Main generate (fallback chain) ───────────────────────────────────────────
@dataclass
class RegenResult:
    photo_name: str
    variant_id: str
    category: str
    prompt: str
    output_path: str
    success: bool
    backend: str = ""
    error: str = ""
    qc_score: float = 0.0
    qc_reasoning: str = ""
    qc_preserve_score: float = 0.0
    qc_light_score: float = 0.0
    qc_appeal_score: float = 0.0


def generate_variant(
    photo_path: Path,
    variant: dict,
    results_dir: Path,
    force_backend: str = "",
) -> RegenResult:
    vid = variant["id"]
    photo_name = photo_path.stem
    out_dir = results_dir / f"{photo_name}__{vid}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"  [regen] {photo_name[:35]:35s} × {vid:18s} ... ", end="", flush=True)
    t0 = time.time()

    if force_backend:
        chain = [BACKEND_MAP[force_backend]] if force_backend in BACKEND_MAP else []
    else:
        chain = BACKENDS

    last_error = "no backends available"
    tried = []
    for bid, fn, available in chain:
        if not available():
            continue
        try:
            ok, result = fn(photo_path, variant, out_dir)
            tried.append(bid)
            if ok:
                elapsed = time.time() - t0
                print(f"OK  ({elapsed:.0f}s) [{bid}]")
                (out_dir / "meta.json").write_text(json.dumps({
                    "photo_name": photo_name, "source_path": str(photo_path),
                    "variant_id": vid, "category": variant["category"],
                    "prompt": variant["prompt"], "backend": bid,
                }, indent=2))
                return RegenResult(
                    photo_name=photo_name, variant_id=vid,
                    category=variant["category"], prompt=variant["prompt"],
                    output_path=result, success=True, backend=bid,
                )
            last_error = f"[{bid}] {result}"
        except Exception as e:
            tried.append(bid)
            last_error = f"[{bid}] exception: {e}"

    elapsed = time.time() - t0
    print(f"FAIL ({elapsed:.0f}s)  tried={tried}  last={last_error[:80]}")
    return RegenResult(
        photo_name=photo_name, variant_id=vid,
        category=variant["category"], prompt=variant["prompt"],
        output_path="", success=False, backend="", error=last_error,
    )


# ─── QC scoring ───────────────────────────────────────────────────────────────
def score_variant(original_path: Path, result: RegenResult, min_preserve: float = 8.1) -> RegenResult:
    if not result.success or not result.output_path:
        return result
    out_path = Path(result.output_path)
    if not out_path.exists():
        return result
    try:
        import anthropic
        client = anthropic.Anthropic()

        def _read_b64(p: Path) -> tuple[str, str]:
            data = p.read_bytes()
            mime = _detect_mime(data)
            return mime, base64.b64encode(data).decode()

        orig_mime, orig_b64 = _read_b64(original_path)
        out_mime, out_b64   = _read_b64(out_path)

        prompt = f"""You are a professional Airbnb listing photo quality judge.

Image 1 = ORIGINAL. Image 2 = AI-REGENERATED using variant "{result.variant_id}" (backend: {result.backend}).

PLATFORM RULE (critical): Airbnb app has a white/bright background throughout.
Dark or moody photos look empty against this and guests skip them instantly.
ANY dark output scores light_score ≤ 3. Bright/airy = 8-10.

PRESERVATION RULE: preserve_score must reach {min_preserve} to be usable.
Furniture positions, wall colors, fixtures, layout must closely match original.
Score strictly — minor differences = 7, layout drift = 5, different room = 2.

Score dimensions (0-10):
1. preserve_score — furniture/layout match (strict, {min_preserve}+ = acceptable)
2. light_score — brightness for Airbnb: dark=1-3, flat=4-5, bright natural=7-8, warm+bright=9-10
3. appeal_score — booking appeal on white bg: dark images ≤ 3
4. total_score — preserve×0.4 + light×0.35 + appeal×0.25 (cap at 5.0 if preserve < {min_preserve})

Return ONLY valid JSON:
{{"preserve_score": <0-10>, "light_score": <0-10>, "appeal_score": <0-10>,
  "total_score": <0-10>, "reasoning": "<2 sentences>",
  "usable": <true if total >= 6.5 AND preserve >= {min_preserve}>}}"""

        resp = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=400,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": orig_mime, "data": orig_b64}},
                {"type": "image", "source": {"type": "base64", "media_type": out_mime, "data": out_b64}},
                {"type": "text", "text": prompt},
            ]}],
        )
        text = resp.content[0].text
        scores = json.loads(text[text.find("{"):text.rfind("}")+1])

        result.qc_score          = scores.get("total_score", 0)
        result.qc_preserve_score = scores.get("preserve_score", 0)
        result.qc_light_score    = scores.get("light_score", 0)
        result.qc_appeal_score   = scores.get("appeal_score", 0)
        result.qc_reasoning      = scores.get("reasoning", "")

        flag = "✓" if scores.get("usable") else "✗"
        print(f"  [qc] {flag} {result.photo_name[:28]:28s} × {result.variant_id:18s} "
              f"[{result.backend}] "
              f"total={result.qc_score:.1f} p={result.qc_preserve_score:.1f} "
              f"l={result.qc_light_score:.1f} a={result.qc_appeal_score:.1f}")
    except Exception as e:
        print(f"  [qc] Error scoring {result.variant_id}: {e}")
    return result


# ─── Report ───────────────────────────────────────────────────────────────────
def generate_and_print_report(results: list, results_dir: Path) -> dict:
    successful = [r for r in results if r.success and r.qc_score > 0]
    if not successful:
        print("No scored results yet.")
        return {}

    ranked = sorted(successful, key=lambda r: r.qc_score, reverse=True)
    usable = [r for r in ranked if r.qc_score >= 6.5 and r.qc_preserve_score >= 8.1]

    variant_avgs: dict[str, list] = {}
    backend_wins: dict[str, int] = {}
    for r in successful:
        variant_avgs.setdefault(r.variant_id, []).append(r.qc_score)
        backend_wins[r.backend] = backend_wins.get(r.backend, 0) + (1 if r.qc_score >= 7.0 else 0)

    best_variants = sorted(
        {k: sum(v)/len(v) for k,v in variant_avgs.items()}.items(),
        key=lambda x: x[1], reverse=True
    )

    report = {
        "summary": {
            "total": len(results), "successful": len(successful),
            "usable": len(usable), "avg_score": round(sum(r.qc_score for r in successful)/len(successful), 2),
        },
        "winner": best_variants[0][0] if best_variants else "N/A",
        "winner_avg": round(best_variants[0][1], 2) if best_variants else 0,
        "backend_wins": backend_wins,
        "top_10": [{"rank": i+1, "photo": r.photo_name, "variant": r.variant_id,
                    "backend": r.backend,
                    "total": round(r.qc_score,1), "preserve": round(r.qc_preserve_score,1),
                    "light": round(r.qc_light_score,1), "appeal": round(r.qc_appeal_score,1),
                    "reasoning": r.qc_reasoning, "output": r.output_path}
                   for i, r in enumerate(ranked[:10])],
        "best_variants": [{"variant": v, "avg": round(a,2)} for v,a in best_variants[:6]],
        "all_results": [asdict(r) for r in ranked],
    }

    (results_dir / "qc_report_free.json").write_text(json.dumps(report, indent=2))

    s = report["summary"]
    print(f"\n{'='*70}")
    print("MULTI-BACKEND PHOTO REGEN REPORT")
    print(f"{'='*70}")
    print(f"Total: {s['total']}  OK: {s['successful']}  Usable(≥6.5+p≥8.1): {s['usable']}  Avg: {s['avg_score']}")
    print(f"\nWINNER VARIANT: {report['winner']}  (avg {report['winner_avg']})")
    if backend_wins:
        print(f"BACKEND WINS (score≥7): {dict(sorted(backend_wins.items(), key=lambda x: x[1], reverse=True))}")
    print(f"\nTOP 10:")
    for item in report["top_10"]:
        flag = "✓" if item["preserve"] >= 8.1 and item["total"] >= 6.5 else "✗"
        print(f"  {flag} #{item['rank']} {item['total']:4.1f}  {item['photo'][:30]:30s} "
              f"[{item['variant']}] via {item['backend']}")
        print(f"         p={item['preserve']} l={item['light']} a={item['appeal']}")
    print(f"\nBEST VARIANTS (avg QC score across all backends):")
    for bv in report["best_variants"]:
        print(f"  {bv['avg']:4.2f}  {bv['variant']}")
    return report


# ─── Export / assemble final set ──────────────────────────────────────────────
def assemble_export(listing_dir: Path, results_dir: Path, export_dir: Path) -> None:
    """
    Build a final photo set whose count matches the original listing upload.

    Strategy per position (determined by subfolder):
      00_COVER_HERO  → hero file (regen best or file already there)
      01_keep        → best regen variant if one exists; else original
      02_retake      → must use best regen variant (original is too weak)
      03_REMOVE      → still need a photo; use best regen if available, else original

    All positions are emitted as 01.jpg … NN.jpg (zero-padded).
    """
    import shutil, csv

    manifest_path = listing_dir / "manifest.csv"
    if not manifest_path.exists():
        print("[export] ERROR: manifest.csv not found in listing_dir")
        return

    with open(manifest_path) as f:
        rows = list(csv.DictReader(f))

    total = len(rows)
    print(f"[export] Original listing: {total} photos")

    # Load best regen result per photo_name (highest qc_score)
    qc_path = results_dir / "qc_report_free.json"
    best_regen: dict[str, Path] = {}
    if qc_path.exists():
        report = json.loads(qc_path.read_text())
        for item in report.get("all_results", []):
            if not item.get("success"):
                continue
            pname = item["photo_name"]
            score = item.get("qc_score", 0)
            out   = item.get("output_path", "")
            if not out or not Path(out).exists():
                continue
            if pname not in best_regen or score > best_regen[pname][1]:
                best_regen[pname] = (Path(out), score)
        best_regen = {k: v[0] for k, v in best_regen.items()}

    # Hero cover override
    hero_dir = listing_dir / "00_COVER_HERO"
    hero_file: Path | None = None
    if hero_dir.exists():
        heroes = sorted(hero_dir.glob("*.png")) + sorted(hero_dir.glob("*.jpg"))
        if heroes:
            hero_file = heroes[0]

    export_dir.mkdir(parents=True, exist_ok=True)
    placed = 0
    for i, row in enumerate(rows, 1):
        pos = str(i).zfill(2)
        verdict   = row.get("verdict", "keep").lower()
        local_path = row.get("local_path", "").strip()
        src: Path | None = None

        # Derive photo_name key (stem of local_path without extension)
        pname = Path(local_path).stem if local_path else ""
        # Normalise to position prefix for lookup (e.g. "06_Bedroom")
        pname_short = "_".join(pname.split("_")[:2]) if pname else ""

        # Try to find regen match by full stem first, then by position prefix
        regen = best_regen.get(pname) or next(
            (v for k, v in best_regen.items() if "_".join(k.split("_")[:2]) == pname_short), None
        )

        if i == 1 and hero_file:
            src = hero_file
        elif regen:
            src = regen
        elif local_path and Path(local_path).exists():
            src = Path(local_path)
        else:
            # Fallback: search subfolder
            for sub in ["00_COVER_HERO", "01_keep", "02_retake", "03_REMOVE"]:
                subdir = listing_dir / sub
                if subdir.exists():
                    matches = list(subdir.glob(f"{pos}_*.jpg")) + list(subdir.glob(f"{pos}_*.png"))
                    if matches:
                        src = matches[0]
                        break

        if src and src.exists():
            ext = src.suffix
            dst = export_dir / f"{pos}{ext}"
            shutil.copy2(src, dst)
            tag = "regen" if regen and src == regen else ("hero" if (i==1 and hero_file) else "orig")
            print(f"  [{tag}] {pos} ← {src.name}")
            placed += 1
        else:
            print(f"  [MISS] {pos} — no source found for position {i} (verdict={verdict})")

    print(f"\n[export] Done. {placed}/{total} photos exported to {export_dir}")
    if placed != total:
        print(f"[export] WARNING: count mismatch — {placed} exported vs {total} original")


# ─── CLI ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Multi-backend photo regen (15 AI engines)")
    parser.add_argument("--listing-dir",    help="Source photos directory")
    parser.add_argument("--results-dir",    help="Results directory (for --retry-missing)")
    parser.add_argument("--export",         action="store_true",
                        help="Assemble final photo set matching original listing count")
    parser.add_argument("--export-dir",     help="Output directory for --export (default: results-dir/FINAL_EXPORT)")
    parser.add_argument("--retry-missing",  action="store_true")
    parser.add_argument("--max-photos",     type=int, default=5)
    parser.add_argument("--workers",        type=int, default=2)
    parser.add_argument("--dry-run",        action="store_true")
    parser.add_argument("--backend",        help="Force specific backend ID")
    parser.add_argument("--list-backends",  action="store_true")
    args = parser.parse_args()

    if args.list_backends:
        list_backends()
        return

    if args.export:
        if not args.listing_dir or not args.results_dir:
            parser.error("--export requires --listing-dir and --results-dir")
        listing_dir = Path(args.listing_dir)
        results_dir = Path(args.results_dir)
        export_dir  = Path(args.export_dir) if args.export_dir else results_dir / "FINAL_EXPORT"
        assemble_export(listing_dir, results_dir, export_dir)
        return

    ml = _load_ml_strategy()
    kill_list   = ml["kill_list"]
    min_preserve = ml["min_preserve"]
    print(f"[ml] Kill list: {kill_list}")
    print(f"[ml] Min preserve: {min_preserve}")

    variants = [v for v in PROMPT_VARIANTS if v["id"] not in kill_list]

    # Check which backends are available
    ready = [(bid, fn, chk) for bid, fn, chk in BACKENDS if chk()]
    if args.backend:
        print(f"[backends] Forced: {args.backend}")
    else:
        print(f"[backends] {len(ready)}/15 ready: {[b[0] for b in ready]}")
    if not ready and not args.backend:
        print("\n[ERROR] No backends available. Run:  python photo_regen_free.py --list-backends")
        return

    # ── Retry missing ──
    if args.retry_missing and args.results_dir:
        results_dir = Path(args.results_dir)
        raw_path = results_dir / "raw_results.json"
        existing = json.loads(raw_path.read_text()) if raw_path.exists() else []
        failed = [r for r in existing if not r.get("success") and r.get("error","") != "dry_run"]
        missing = [r for r in failed if r["variant_id"] not in kill_list]
        print(f"\n[retry] {len(missing)} missing variants to run\n")

        listing_dir = Path(args.listing_dir) if args.listing_dir else None
        photo_paths: dict[str, Path] = {}
        if listing_dir:
            for sub in ["00_COVER_HERO", "01_keep", "02_retake"]:
                subdir = listing_dir / sub
                if subdir.exists():
                    for p in subdir.glob("*.jpg"):
                        photo_paths[p.stem] = p
        for r in missing:
            if r["photo_name"] not in photo_paths:
                meta_p = results_dir / f"{r['photo_name']}__{r['variant_id']}" / "meta.json"
                if meta_p.exists():
                    src = json.loads(meta_p.read_text()).get("source_path", "")
                    if src and Path(src).exists():
                        photo_paths[r["photo_name"]] = Path(src)

        variant_map = {v["id"]: v for v in variants}
        tasks = [(photo_paths[r["photo_name"]], variant_map[r["variant_id"]])
                 for r in missing
                 if r["photo_name"] in photo_paths and r["variant_id"] in variant_map]

        existing_map = {(r["photo_name"], r["variant_id"]): i for i, r in enumerate(existing)}
        new_results: list[RegenResult] = []

        for photo, variant in tasks:
            if args.dry_run:
                print(f"  [dry] {photo.stem} × {variant['id']}")
                continue
            res = generate_variant(photo, variant, results_dir, force_backend=args.backend or "")
            new_results.append(res)
            key = (res.photo_name, res.variant_id)
            if key in existing_map:
                existing[existing_map[key]] = asdict(res)
            else:
                existing.append(asdict(res))
            time.sleep(2)

        raw_path.write_text(json.dumps(existing, indent=2))
        n_ok = sum(1 for r in new_results if r.success)
        print(f"\n[retry] Done. {n_ok}/{len(new_results)} successful.")

        if listing_dir:
            to_score = [r for r in new_results if r.success]
            print(f"[qc] Scoring {len(to_score)} new results...")
            for r in to_score:
                orig = photo_paths.get(r.photo_name)
                if orig and orig.exists():
                    r = score_variant(orig, r, min_preserve)
                    key = (r.photo_name, r.variant_id)
                    if key in existing_map:
                        existing[existing_map[key]] = asdict(r)
            raw_path.write_text(json.dumps(existing, indent=2))

        from dataclasses import fields as dc_fields
        rf = {f.name for f in dc_fields(RegenResult)}
        all_results = [RegenResult(**{k: v for k, v in r.items() if k in rf}) for r in existing]
        generate_and_print_report(all_results, results_dir)
        return

    # ── Fresh run ──
    if not args.listing_dir:
        parser.error("Provide --listing-dir or --retry-missing")
    listing_dir = Path(args.listing_dir)
    results_dir = RESULTS_DIR / listing_dir.name
    results_dir.mkdir(parents=True, exist_ok=True)

    photos: list[Path] = []
    seen: set[str] = set()
    for sub in ["00_COVER_HERO", "01_keep", "02_retake"]:
        subdir = listing_dir / sub
        if subdir.exists():
            for p in sorted(subdir.glob("*.jpg")):
                key = "_".join(p.stem.split("_")[:2])
                if key not in seen:
                    seen.add(key)
                    photos.append(p)
    photos = photos[:args.max_photos]

    total = len(photos) * len(variants)
    print(f"\n[free] {len(photos)} photos × {len(variants)} variants = {total} generations")
    print(f"[free] Kill list: {kill_list}\n")

    if args.dry_run:
        for p in photos:
            for v in variants:
                print(f"  [dry] {p.stem} × {v['id']}")
        return

    results: list[RegenResult] = []
    tasks = [(p, v) for p in photos for v in variants]

    def _run(task):
        p, v = task
        return generate_variant(p, v, results_dir, force_backend=args.backend or "")

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(_run, t) for t in tasks]
        for f in concurrent.futures.as_completed(futures):
            try:
                results.append(f.result())
            except Exception as e:
                print(f"  [err] {e}")

    raw_path = results_dir / "raw_results_free.json"
    raw_path.write_text(json.dumps([asdict(r) for r in results], indent=2))
    n_ok = sum(1 for r in results if r.success)
    print(f"\n[free] {n_ok}/{len(results)} generated")

    to_score  = [r for r in results if r.success]
    photo_map = {p.stem: p for p in photos}
    print(f"[qc] Scoring {len(to_score)} results...")
    for i, r in enumerate(results):
        if r.success:
            orig = photo_map.get(r.photo_name)
            if orig:
                results[i] = score_variant(orig, r, min_preserve)

    raw_path.write_text(json.dumps([asdict(r) for r in results], indent=2))
    generate_and_print_report(results, results_dir)


if __name__ == "__main__":
    main()
