"""Sync clients from Notion Clients database into state.json."""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from notion_client import Client

from src.bot.medspa import STATE_FILE, load_state, save_state

logger = logging.getLogger("fb-ads-bot")

# Stages that appear in the "Active Clients" view (everything except Inactive & Churned)
ACTIVE_STAGES = {
    "Onboarding",
    "System Setup",
    "Offer and assets",
    "Campaign launch",
    "Launch/active ads",
    "Optimization",
    "Ads Paused",
    "Coaching ended",
}


def _slugify(name: str) -> str:
    """Convert business name to a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s.-]", "", slug)  # remove non-word chars (keep hyphens, dots)
    slug = re.sub(r"[.\s_]+", "-", slug)  # dots/spaces/underscores → hyphens
    slug = re.sub(r"-+", "-", slug)  # collapse multiple hyphens
    return slug.strip("-")


# Business names to skip (internal, not actual clients)
_SKIP_NAMES = {"MARKTR™", "New Client [TEMPLATE]"}


def _extract_resources_db_id(page: dict) -> str | None:
    """Extract Resources inline database collection ID from page children."""
    # This requires fetching the page blocks; we'll populate it as empty
    # and let the medspa-ads skill fill it in on first use.
    return None


def sync_clients(notion_api_key: str, clients_db_id: str) -> dict:
    """Query Notion Clients DB, merge into state.json, return summary.

    Returns dict with keys: added, updated, removed, total.
    """
    notion = Client(auth=notion_api_key)

    # First retrieve the database to get its data source ID
    db = notion.databases.retrieve(database_id=clients_db_id)
    data_source_id = None
    for ds in db.get("data_sources", []):
        data_source_id = ds.get("data_source_id") or ds.get("id")
        break

    # Query all pages via data_sources.query (notion-client v2+)
    results = []
    cursor = None
    while True:
        kwargs: dict = {"page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        if data_source_id:
            response = notion.data_sources.query(data_source_id=data_source_id, **kwargs)
        else:
            # Fallback: use search filtered to this database
            kwargs["filter"] = {"property": "object", "value": "page"}
            response = notion.search(**kwargs)
        results.extend(response.get("results", []))
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")

    state = load_state()
    old_clients = state.get("clients", {})
    new_clients: dict[str, dict] = {}

    added = 0
    updated = 0

    for page in results:
        props = page["properties"]

        # Extract business name (title property)
        title_parts = props.get("Business Name", {}).get("title", [])
        name = "".join(t.get("plain_text", "") for t in title_parts).strip()
        if not name:
            continue

        # Skip internal/template pages
        if name in _SKIP_NAMES:
            continue

        # Extract stage
        stage_prop = props.get("Stage", {}).get("select")
        stage = stage_prop["name"] if stage_prop else ""

        # Filter to active stages only
        if stage not in ACTIVE_STAGES:
            continue

        slug = _slugify(name)
        page_id = page["id"]

        existing = old_clients.get(slug, {})
        entry = {
            "name": name,
            "notion_page_id": page_id,
            "resources_db_id": existing.get("resources_db_id", ""),
            "stage": stage,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        if slug in old_clients:
            if old_clients[slug].get("stage") != stage:
                updated += 1
        else:
            added += 1

        new_clients[slug] = entry

    # Detect removed clients
    removed_slugs = set(old_clients.keys()) - set(new_clients.keys())
    removed = len(removed_slugs)

    state["clients"] = new_clients
    save_state(state)

    logger.info(
        "Notion sync: %d total, %d added, %d updated, %d removed",
        len(new_clients),
        added,
        updated,
        removed,
    )

    return {
        "added": added,
        "updated": updated,
        "removed": removed,
        "total": len(new_clients),
    }


# ---------------------------------------------------------------------------
# Offer sync
# ---------------------------------------------------------------------------

def _get_all_text(notion: Client, block_id: str, depth: int = 0) -> str:
    """Recursively extract plain text from all blocks under a page/block."""
    if depth > 5:
        return ""
    parts: list[str] = []
    cursor = None
    while True:
        kwargs: dict = {"block_id": block_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = notion.blocks.children.list(**kwargs)
        for block in resp.get("results", []):
            btype = block.get("type", "")
            # Extract rich_text from the block type's data
            type_data = block.get(btype, {})
            if isinstance(type_data, dict):
                for rt in type_data.get("rich_text", []):
                    parts.append(rt.get("plain_text", ""))
                # Title for child_page blocks
                if "title" in type_data:
                    parts.append(type_data["title"])
            # Recurse into children and synced blocks
            if block.get("has_children"):
                parts.append(_get_all_text(notion, block["id"], depth + 1))
            # Handle synced_block references
            if btype == "synced_block":
                ref = type_data.get("synced_from")
                if ref and ref.get("block_id"):
                    parts.append(_get_all_text(notion, ref["block_id"], depth + 1))
            parts.append("\n")
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return "".join(parts)


def _parse_offers(text: str) -> list[dict]:
    """Parse offer blocks from the Intro Offer page text."""
    # Split on "Intro Offer" headings (may or may not have # prefix)
    offers: list[str] = re.split(r"(?=(?:#\s*)?Intro Offer(?:\s*\d+)?(?:\s*\()?\b)", text)
    results = []
    seen_names: set[str] = set()
    for block in offers:
        if not block.strip():
            continue

        # Extract offer name from "Offer/Special Name:" or first quoted string
        name_match = re.search(
            r'Offer/Special Name[:\s]*["\u201c\u2018]([^"\u201d\u2019]+)["\u201d\u2019]', block
        )
        if not name_match:
            # Try quoted string near start of block
            name_match = re.search(r'["\u201c]([^"\u201d]+)["\u201d]', block)
        if not name_match:
            continue
        # Skip duplicates (synced blocks can repeat)
        name = name_match.group(1).strip()
        if name in seen_names:
            continue
        seen_names.add(name)

        name = name_match.group(1).strip()

        # Extract intro offer price
        price_match = re.search(
            r'Intro offer price[^$C]*([C$]+\s*\$?\s*[\d,.]+)', block, re.IGNORECASE
        )
        if not price_match:
            price_match = re.search(r'Intro offer price[^\d]*([\d,.]+)', block, re.IGNORECASE)
        price = price_match.group(1).strip() if price_match else ""
        # Normalize price format
        if price and not price.startswith(("$", "C")):
            price = f"${price}"

        # Extract regular price
        reg_match = re.search(
            r'Reg price[^$C]*([C$]+\s*\$?\s*[\d,.]+)', block, re.IGNORECASE
        )
        if not reg_match:
            reg_match = re.search(r'Reg price[^\d]*([\d,.]+)', block, re.IGNORECASE)
        regular_price = reg_match.group(1).strip() if reg_match else ""
        if regular_price and not regular_price.startswith(("$", "C")):
            regular_price = f"${regular_price}"

        # Extract treatment summary (from numbered list item 2)
        summary_match = re.search(r'2\.\s*Treatment\s*→\s*([^-\n(C$]+)', block)
        summary = summary_match.group(1).strip().rstrip(" -") if summary_match else name

        results.append({
            "slug": _slugify(name),
            "name": name,
            "price": price,
            "regular_price": regular_price,
            "summary": summary,
        })

    return results


def _find_intro_offer_page(notion: Client, client_page_id: str) -> str | None:
    """Find the 'Intro Offer' child page within a client's page."""
    cursor = None
    while True:
        kwargs: dict = {"block_id": client_page_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = notion.blocks.children.list(**kwargs)
        for block in resp.get("results", []):
            btype = block.get("type", "")
            # Check child_page blocks
            if btype == "child_page":
                title = block.get("child_page", {}).get("title", "")
                if "intro offer" in title.lower():
                    return block["id"]
            # Check child_database blocks for Resources DB, then search within
            if btype == "child_database":
                db_title = block.get("child_database", {}).get("title", "")
                if "resources" in db_title.lower():
                    # Search within this database for Intro Offer page
                    page_id = _search_resources_db(notion, block["id"])
                    if page_id:
                        return page_id
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")
    return None


def _search_resources_db(notion: Client, db_id: str) -> str | None:
    """Search a Resources database for an 'Intro Offer' page."""
    try:
        db = notion.databases.retrieve(database_id=db_id)
        data_source_id = None
        for ds in db.get("data_sources", []):
            data_source_id = ds.get("data_source_id") or ds.get("id")
            break
        if not data_source_id:
            return None
        resp = notion.data_sources.query(data_source_id=data_source_id, page_size=50)
        for page in resp.get("results", []):
            props = page.get("properties", {})
            name_parts = props.get("Name", {}).get("title", [])
            name = "".join(t.get("plain_text", "") for t in name_parts).strip()
            if "intro offer" in name.lower():
                return page["id"]
    except Exception as e:
        logger.warning("Failed to search resources DB %s: %s", db_id, e)
    return None


def sync_offers(notion_api_key: str, client_slug: str) -> dict:
    """Sync offers for a single client from their Notion Intro Offer page.

    Returns dict with keys: total, intro_offers_page_id.
    """
    notion = Client(auth=notion_api_key)
    state = load_state()

    client = state.get("clients", {}).get(client_slug)
    if not client:
        raise ValueError(f"Client '{client_slug}' not found in state")

    # Check if we already know the intro offers page ID
    offers_data = state.setdefault("offers", {}).setdefault(client_slug, {})
    page_id = offers_data.get("intro_offers_page_id")

    if not page_id:
        # Find it by traversing the client page
        page_id = _find_intro_offer_page(notion, client["notion_page_id"])
        if not page_id:
            raise ValueError(f"No 'Intro Offer' page found for {client['name']}")

    # Fetch all text from the Intro Offer page
    text = _get_all_text(notion, page_id)
    parsed = _parse_offers(text)

    if not parsed:
        raise ValueError(f"Could not parse any offers from the Intro Offer page")

    # Update state
    offers_data["intro_offers_page_id"] = page_id
    offers_data["cached_offers"] = parsed
    save_state(state)

    logger.info("Synced %d offers for %s", len(parsed), client_slug)

    return {"total": len(parsed), "intro_offers_page_id": page_id}
