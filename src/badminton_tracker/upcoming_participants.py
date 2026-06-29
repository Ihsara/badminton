"""Pure participant parsing + full-name friend matching for the upcoming pipeline.

Matching rule (see ingest spec): a friend matches only when EVERY token of their
roster full_name appears in the participant name (order-independent — the site
renders "Surname, First"). Chau also matches his Vietnamese registrations
(chau+tran OR chau+long). Excluded names never match.
"""

from __future__ import annotations

import re

_PLAYER_RE = re.compile(r"player=(\d+)")
_ANCHOR_RE = re.compile(r'<a[^>]*href="[^"]*player\.aspx[^"]*"[^>]*>(.*?)</a>', re.I | re.S)


def _tokens(name: str) -> set[str]:
    return {t for t in re.sub(r"[.,]", " ", name).lower().split() if t}


def parse_participants(html: str) -> list[dict]:
    out: list[dict] = []
    for m in re.finditer(
        r'<a[^>]*href="([^"]*player\.aspx[^"]*)"[^>]*>(.*?)</a>', html, re.I | re.S
    ):
        href, inner = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        pm = _PLAYER_RE.search(href)
        if pm and inner and len(inner) > 2:
            out.append({"name": inner, "player_no": pm.group(1)})
    return out


def _chau_special(part_tokens: set[str]) -> bool:
    has_chau = "chau" in part_tokens or "châu" in part_tokens
    has_tran = "tran" in part_tokens or "trần" in part_tokens
    has_long = "long" in part_tokens
    if not has_chau:
        return False
    # exclude "Chau Vu" / "Quan Chau": require chau + (tran OR long)
    return has_tran or has_long


def match_friends(participants: list[dict], roster: list[dict], exclude: set[str]) -> list[dict]:
    hits: list[dict] = []
    seen: set[str] = set()
    for part in participants:
        pt = _tokens(part["name"])
        for r in roster:
            full = r.get("full_name") or ""
            if not full:
                continue
            if full.lower() in exclude:
                continue
            ft = _tokens(full)
            is_chau = r.get("nickname", "").lower() == "chau"
            matched = (ft and ft <= pt) or (is_chau and _chau_special(pt))
            if matched and part["player_no"] not in seen:
                seen.add(part["player_no"])
                hits.append({
                    "nickname": r["nickname"], "full_name": full,
                    "player_no": part["player_no"],
                })
                break
    return hits
