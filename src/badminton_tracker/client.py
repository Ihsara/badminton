"""TournamentSoftware browser client: login, cookie consent, session reuse."""

from __future__ import annotations

import contextlib

from playwright.sync_api import BrowserContext, Page, Playwright

from .config import BASE_URL, PASSWORD, STATE_FILE, USERNAME

ACCEPT_LABELS = [
    "Accept all",
    "Accept",
    "Hyväksy kaikki",
    "Hyväksy",
    "Salli kaikki",
    "Agree",
    "OK",
]


def dismiss_cookies(page: Page) -> None:
    """Best-effort dismissal of the nojazz.eu consent iframe overlay."""
    page.wait_for_timeout(600)
    for frame in page.frames:
        url = (frame.url or "").lower()
        if not any(k in url for k in ("consent", "nojazz", "cmp")):
            continue
        for label in ACCEPT_LABELS:
            try:
                btn = frame.get_by_role("button", name=label, exact=False).first
                if btn.count() and btn.is_visible(timeout=800):
                    btn.click()
                    page.wait_for_timeout(400)
                    return
            except Exception:
                continue


def is_logged_in(page: Page) -> bool:
    try:
        return page.locator("a[href*='/user/LogOff'], a[href*='/user/Logoff']").count() > 0
    except Exception:
        return False


def login(page: Page) -> bool:
    page.goto(f"{BASE_URL}/user/Login", wait_until="domcontentloaded")
    dismiss_cookies(page)
    page.fill("input[name='Login']", USERNAME)
    page.fill("input[name='Password']", PASSWORD)
    # A JS click bypasses the consent iframe that otherwise intercepts pointer events.
    page.eval_on_selector("#btnLogin", "el => el.click()")
    with contextlib.suppress(Exception):
        page.wait_for_url(lambda u: "/user/login" not in u.lower(), timeout=15000)
    page.wait_for_load_state("domcontentloaded")
    return is_logged_in(page)


def ensure_login(ctx: BrowserContext) -> Page:
    """Return a logged-in page, reusing saved storage state when still valid."""
    page = ctx.new_page()
    page.goto(BASE_URL, wait_until="domcontentloaded")
    dismiss_cookies(page)
    if is_logged_in(page):
        return page
    if not USERNAME or not PASSWORD:
        raise RuntimeError("Missing credentials — set TOURNAMENTSOFTWARE_USERNAME/PASSWORD in .env")
    if login(page):
        ctx.storage_state(path=str(STATE_FILE))
        return page
    raise RuntimeError("Login failed — check credentials in .env")


def new_context(p: Playwright, headless: bool = True):
    browser = p.chromium.launch(headless=headless)
    if STATE_FILE.exists():
        ctx = browser.new_context(storage_state=str(STATE_FILE))
    else:
        ctx = browser.new_context()
    return browser, ctx
