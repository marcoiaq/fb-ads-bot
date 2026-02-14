from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("fb-ads-bot")

STATE_FILE = Path.home() / ".claude/skills/medspa-ads/state.json"
GEMINI_BIN = Path.home() / ".npm-global/bin/gemini"
OUTPUT_DIR = Path.home() / "nanobanana-output"
MODELS = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"clients": {}, "offers": {}, "hooks_history": {}}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


STAGE_EMOJI = {
    "Launch/active ads": "🟢",
    "Optimization": "🔧",
    "Campaign launch": "🚀",
    "Offer and assets": "📝",
    "Onboarding": "📋",
    "System Setup": "⚙️",
    "Ads Paused": "⏸",
    "Coaching ended": "🔴",
}


def get_clients(state: dict) -> list[dict]:
    """Return [{slug, name, stage, emoji}, ...] from state."""
    return [
        {
            "slug": slug,
            "name": info["name"],
            "stage": info.get("stage", ""),
            "emoji": STAGE_EMOJI.get(info.get("stage", ""), "⚪"),
        }
        for slug, info in state.get("clients", {}).items()
    ]


def get_offers(state: dict, client_slug: str) -> list[dict]:
    """Return cached_offers for a client."""
    client_offers = state.get("offers", {}).get(client_slug, {})
    return client_offers.get("cached_offers", [])


def get_hooks(state: dict, client_slug: str, offer_slug: str) -> list[dict]:
    """Return hooks from hooks_history for a client:offer pair."""
    key = f"{client_slug}:{offer_slug}"
    return state.get("hooks_history", {}).get(key, [])


def _build_prompt(hook: dict, offer: dict, size: str) -> str:
    """Build the Gemini image generation prompt."""
    hook_text = hook["hook"]
    visual = hook.get("visual", "Close-up portrait of a woman with radiant skin")
    offer_line = f"{offer['name']} — {offer['price']}"

    if size == "square":
        return (
            f"Ultra-realistic professional photography, {visual}. "
            f"Soft golden-hour window light, professional studio lighting. "
            f'Elegant text overlay reading "{hook_text}" in modern sans-serif font at top, '
            f'smaller text "{offer_line}" below in accent color. '
            f"Shot on Canon EOS R5, 85mm lens, f/2.8, shallow depth of field. "
            f"Beauty advertising campaign quality, high-end med-spa aesthetic, "
            f"square 1:1 aspect ratio, 1080x1080."
        )
    else:  # vertical
        return (
            f"Ultra-realistic professional photography, {visual}. "
            f"Soft golden-hour window light, professional studio lighting. "
            f'Elegant text overlay reading "{hook_text}" in modern sans-serif font at upper third, '
            f'smaller text "{offer_line}" in lower third. '
            f"Shot on Canon EOS R5, 85mm lens, f/2.8, shallow depth of field. "
            f"Beauty advertising campaign quality, high-end med-spa aesthetic, "
            f"vertical 9:16 aspect ratio, 1080x1920."
        )


async def generate_image(
    hook: dict, offer: dict, size: str, model_idx: int = 0
) -> Path | None:
    """Generate a single image via Gemini CLI with model fallback.

    Returns path to the generated image, or None if all models exhausted.
    """
    if model_idx >= len(MODELS):
        return None

    prompt = _build_prompt(hook, offer, size)
    model = MODELS[model_idx]

    # Snapshot existing files before generation
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    before = set(OUTPUT_DIR.iterdir())

    cmd = [
        str(GEMINI_BIN),
        "--model", model,
        "--yolo",
        f"/generate '{prompt}' --preview",
    ]

    logger.info("Generating %s image with %s: %.80s...", size, model, hook["hook"])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
    except asyncio.TimeoutError:
        logger.warning("Gemini timed out for model %s", model)
        return await generate_image(hook, offer, size, model_idx + 1)

    output = (stdout or b"").decode() + (stderr or b"").decode()

    # Check for quota errors → fallback to next model
    if proc.returncode != 0 or "QuotaError" in output or "429" in output:
        logger.warning("Quota/error on %s, falling back...", model)
        return await generate_image(hook, offer, size, model_idx + 1)

    # Find the newly created file
    after = set(OUTPUT_DIR.iterdir())
    new_files = sorted(after - before, key=lambda p: p.stat().st_mtime, reverse=True)
    if new_files:
        return new_files[0]

    logger.warning("No new file found after generation")
    return None


async def run_generation(
    hooks: list[dict],
    offer: dict,
    progress_callback,
) -> list[Path]:
    """Generate square + vertical for each hook, sequentially.

    Calls progress_callback(current, total, hook_text, size) after each image.
    """
    results: list[Path] = []
    total = len(hooks) * 2
    current = 0

    for hook in hooks:
        for size in ("square", "vertical"):
            current += 1
            await progress_callback(current, total, hook["hook"], size)
            path = await generate_image(hook, offer, size)
            if path:
                results.append(path)

    return results


def update_state_after_generation(
    state: dict, client_slug: str, offer_slug: str, hooks: list[dict]
) -> None:
    """Update state.json after a generation run."""
    now = datetime.now(timezone.utc).isoformat()

    # Update last_used offer
    if client_slug in state.get("offers", {}):
        state["offers"][client_slug]["last_used"] = offer_slug

    # Update client last_updated
    if client_slug in state.get("clients", {}):
        state["clients"][client_slug]["last_updated"] = now

    # Append hooks to history (avoid duplicates)
    key = f"{client_slug}:{offer_slug}"
    history = state.setdefault("hooks_history", {})
    existing = history.get(key, [])
    existing_texts = {h["hook"] for h in existing}

    for hook in hooks:
        if hook["hook"] not in existing_texts:
            existing.append(hook)
            existing_texts.add(hook["hook"])

    history[key] = existing
    save_state(state)
