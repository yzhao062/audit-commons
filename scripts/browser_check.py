#!/usr/bin/env python3
"""
scripts/browser_check.py - Browser acceptance test suite using Python Playwright.

Covers:
- Contract routes HTTP success and semantic structure (title, single h1, landmarks, nav)
- Console JS errors & uncaught exceptions
- Horizontal overflow detection on desktop (1440x1000), mobile (390x844), and narrow (320x780)
- Keyboard skip link navigation and focus verification (main#main tabindex=-1)
- Resources filtering: category buttons, text search, combined filtering, aria-pressed, no-results state, reset All
- No-JS degradation: controls hidden, all resource cards visible, all major page content readable
- Screenshots capture (desktop & mobile for home, resources, guide; 404 page)
- Machine-readable JSON evidence report with pass/fail and exact observations
"""

import argparse
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Error as PlaywrightError

CONTRACT_ROUTES = [
    "/",
    "/latest/",
    "/features/",
    "/learn/",
    "/start-here/",
    "/resources/",
    "/guides/",
    "/guides/audit-an-agent-action/",
    "/updates/",
    "/updates/catchbench-0-1-2/",
    "/about/",
    "/404.html",
]

for article in json.loads((Path(__file__).resolve().parents[1] / "content/pages.json").read_text(encoding="utf-8")):
    article_route = f"/{article['slug']}/"
    if article_route not in CONTRACT_ROUTES:
        CONTRACT_ROUTES.append(article_route)

zh_dir = Path(__file__).resolve().parents[1] / "content/zh"
if zh_dir.exists():
    zh_base = [
        "/zh/",
        "/zh/latest/",
        "/zh/features/",
        "/zh/learn/",
        "/zh/resources/",
        "/zh/guides/",
        "/zh/updates/",
        "/zh/about/",
        "/zh/404.html",
    ]
    for r in zh_base:
        if r not in CONTRACT_ROUTES:
            CONTRACT_ROUTES.append(r)
    for article in json.loads((Path(__file__).resolve().parents[1] / "content/pages.json").read_text(encoding="utf-8")):
        zh_article_route = f"/zh/{article['slug']}/"
        if zh_article_route not in CONTRACT_ROUTES:
            CONTRACT_ROUTES.append(zh_article_route)

VIEWPORTS = [
    {"name": "desktop", "width": 1440, "height": 1000},
    {"name": "mobile", "width": 390, "height": 844},
    {"name": "narrow", "width": 320, "height": 780},
]


@dataclass
class CheckResult:
    id: str
    category: str
    name: str
    status: str  # "PASS" or "FAIL"
    observation: str
    details: Optional[Dict[str, Any]] = None


class BrowserAcceptanceChecker:
    def __init__(self, base_url: str, screenshots_dir: Optional[str] = None, headless: bool = True):
        self.base_url = base_url.rstrip("/")
        self.screenshots_dir = screenshots_dir
        self.headless = headless
        self.checks: List[CheckResult] = []
        self.screenshots_taken: List[Dict[str, Any]] = []

    def log(self, message: str) -> None:
        print(f"[qa-browser] {message}", file=sys.stderr, flush=True)

    def add_check(
        self,
        check_id: str,
        category: str,
        name: str,
        status: str,
        observation: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        result = CheckResult(
            id=check_id,
            category=category,
            name=name,
            status=status,
            observation=observation,
            details=details,
        )
        self.checks.append(result)
        prefix = "✓ PASS" if status == "PASS" else "✗ FAIL"
        self.log(f"{prefix}: [{category}] {name} - {observation}")

    def make_url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def run(self) -> int:
        start_time = datetime.now(timezone.utc).isoformat()
        self.log(f"Starting browser acceptance checks against base URL: {self.base_url}")

        if self.screenshots_dir:
            os.makedirs(self.screenshots_dir, exist_ok=True)
            self.log(f"Screenshots will be stored in: {self.screenshots_dir}")

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                try:
                    # 1. Standard JS-enabled checks across all contract routes
                    self.run_standard_route_checks(browser)

                    # 2. Keyboard skip link focus verification
                    self.run_skip_link_check(browser)

                    # 3. Resources filtering, search, aria-pressed, reset
                    self.run_resources_filter_checks(browser)

                    # 3b. Latest all-content filtering, back/forward, EN/ZH switch
                    self.run_latest_filter_checks(browser)

                    # 4. No-JS verification
                    self.run_no_js_checks(browser)

                    self.run_media_checks(browser)

                    # Localization browser acceptance checks
                    self.run_localization_browser_checks(browser)
                    self.run_language_reading_checks(browser)

                    # 5. Screenshots capture if requested
                    if self.screenshots_dir:
                        self.run_screenshots_capture(browser)

                finally:
                    browser.close()

        except PlaywrightError as pe:
            self.add_check(
                check_id="browser_runtime_error",
                category="runtime",
                name="Playwright Browser Execution",
                status="FAIL",
                observation=f"Playwright error during suite execution: {pe}",
            )
        except Exception as e:
            self.add_check(
                check_id="unexpected_exception",
                category="runtime",
                name="Execution Exception",
                status="FAIL",
                observation=f"Unexpected exception during test run: {e}",
            )

        # Generate report
        passed_checks = sum(1 for c in self.checks if c.status == "PASS")
        failed_checks = sum(1 for c in self.checks if c.status == "FAIL")
        total_checks = len(self.checks)
        all_passed = (total_checks > 0) and (failed_checks == 0)

        report = {
            "summary": {
                "base_url": self.base_url,
                "timestamp": start_time,
                "passed": all_passed,
                "total_checks": total_checks,
                "passed_checks": passed_checks,
                "failed_checks": failed_checks,
            },
            "checks": [asdict(c) for c in self.checks],
            "screenshots": self.screenshots_taken,
        }

        # Print machine-readable JSON to stdout
        print(json.dumps(report, indent=2))
        return 0 if all_passed else 1

    def run_localization_browser_checks(self, browser: Browser) -> None:
        """Verify language switcher navigation and query parameter retention in browser."""
        context = browser.new_context()
        page = context.new_page()

        try:
            test_url = self.make_url("/resources/?category=Reading&q=audit")
            page.goto(test_url, wait_until="networkidle")

            zh_switch = page.locator(".lang-switch a[hreflang='zh-CN']")
            if zh_switch.count() == 0:
                self.add_check(
                    check_id="lang_switch_present",
                    category="localization",
                    name="Language switcher presence",
                    status="FAIL",
                    observation="Language switcher zh-CN link missing on /resources/",
                )
                context.close()
                return

            zh_switch.click()
            page.wait_for_load_state("networkidle")

            current_url = page.url
            has_zh_path = "/zh/resources/" in current_url
            has_cat = "category=Reading" in current_url
            has_q = "q=audit" in current_url

            if has_zh_path and has_cat and has_q:
                self.add_check(
                    check_id="lang_switch_param_retention",
                    category="localization",
                    name="Language switch query retention",
                    status="PASS",
                    observation=f"Successfully navigated to Chinese edition with params preserved: {current_url}",
                )
            else:
                self.add_check(
                    check_id="lang_switch_param_retention",
                    category="localization",
                    name="Language switch query retention",
                    status="FAIL",
                    observation=f"Expected /zh/resources/?category=Reading&q=audit, got {current_url}",
                )

            count_text = page.locator("#resource-count").inner_text()
            if "显示" in count_text or "资源" in count_text:
                self.add_check(
                    check_id="zh_resource_count_localized",
                    category="localization",
                    name="Chinese resource count localization",
                    status="PASS",
                    observation=f"Resource count announced in Chinese: '{count_text}'",
                )
            else:
                self.add_check(
                    check_id="zh_resource_count_localized",
                    category="localization",
                    name="Chinese resource count localization",
                    status="FAIL",
                    observation=f"Resource count not localized: '{count_text}'",
                )

            en_switch = page.locator(".lang-switch a[hreflang='en']")
            en_switch.click()
            page.wait_for_load_state("networkidle")
            en_url = page.url
            if "/resources/" in en_url and "/zh/" not in en_url and "category=Reading" in en_url:
                self.add_check(
                    check_id="lang_switch_return",
                    category="localization",
                    name="Language switch return to English",
                    status="PASS",
                    observation=f"Successfully returned to English edition with params preserved: {en_url}",
                )
            else:
                self.add_check(
                    check_id="lang_switch_return",
                    category="localization",
                    name="Language switch return to English",
                    status="FAIL",
                    observation=f"Failed return to English: {en_url}",
                )

        except Exception as e:
            self.add_check(
                check_id="localization_browser_error",
                category="localization",
                name="Language switcher browser interaction",
                status="FAIL",
                observation=f"Exception during localization browser checks: {e}",
            )
        finally:
            context.close()

    def run_language_reading_checks(self, browser: Browser) -> None:
        """Keep search results and reading position consistent across languages."""
        context = browser.new_context()
        page = context.new_page()
        try:
            for query in ("voluntary", "自愿性"):
                page.goto(self.make_url("/resources/"), wait_until="networkidle")
                page.locator("#resource-search").fill(query)
                before = page.locator(".resource-card:visible .resource-title").all_text_contents()
                assert before, f"No English results for {query}"
                page.locator(".lang-switch a[hreflang='zh-CN']").click()
                page.wait_for_load_state("networkidle")
                after = page.locator(".resource-card:visible .resource-title").all_text_contents()
                assert before == after, f"Search results changed on language switch for {query}"
            self.add_check(check_id="bilingual_summary_search", category="localization",
                           name="Bilingual search equivalence", status="PASS",
                           observation="English and Chinese summary queries retain identical results after switching")

            page.goto(self.make_url("/guides/how-to-read-an-agent-eval-report/?view=reading#five-questions"), wait_until="networkidle")
            page.locator(".lang-switch a[hreflang='zh-CN']").click()
            page.wait_for_load_state("networkidle")
            assert "/zh/guides/" in page.url and page.url.endswith("?view=reading#five-questions"), page.url
            page.locator('.article-toc a[href="#worked-example"]').click()
            page.locator(".lang-switch a[hreflang='en']").click()
            page.wait_for_load_state("networkidle")
            assert "/zh/" not in page.url and page.url.endswith("?view=reading#worked-example"), page.url
            self.add_check(check_id="article_language_anchor", category="localization",
                           name="Article query and updated anchor retention", status="PASS",
                           observation="Switching preserves the article query and the newly selected table-of-contents anchor")

            with browser.new_context(java_script_enabled=False) as plain:
                document = plain.new_page()
                document.goto(self.make_url("/zh/guides/how-to-read-an-agent-eval-report/"), wait_until="networkidle")
                assert document.locator("html").get_attribute("lang") == "zh-CN"
                document.locator(".lang-switch a[hreflang='en']").click()
                document.wait_for_load_state("networkidle")
                assert document.url.endswith("/guides/how-to-read-an-agent-eval-report/") and "/zh/" not in document.url
            self.add_check(check_id="language_switch_no_js", category="localization",
                           name="Language switch without JavaScript", status="PASS",
                           observation="Chinese article switches to its English equivalent using a plain link")
        except Exception as exc:
            self.add_check(check_id="language_reading_regression", category="localization",
                           name="Bilingual reading continuity", status="FAIL", observation=str(exc))
        finally:
            context.close()

    def run_media_checks(self, browser: Browser) -> None:
        """Decode actual local images, including lazy images hidden by catalog filters."""
        context = browser.new_context()
        page = context.new_page()
        for route in ('/latest/', '/resources/'):
            page.goto(self.make_url(route), wait_until='networkidle')
            results = page.locator('img[src^="/assets/media/"]').evaluate_all('''async images =>
                Promise.all(images.map(async image => {
                    const probe = new Image();
                    probe.src = image.src;
                    try { await probe.decode(); }
                    catch { return {src: image.getAttribute('src'), ok: false}; }
                    return {src: image.getAttribute('src'), ok: probe.naturalWidth > 0 && probe.naturalHeight > 0};
                }))''')
            failed = [r['src'] for r in results if not r['ok']]
            self.add_check(
                check_id='media_decode_' + route.strip('/'), category='media',
                name=f'Editorial images decode on {route}',
                status='PASS' if results and not failed else 'FAIL',
                observation=f'{len(results)} images; decode failures: {failed}',
            )
        context.close()

    def run_standard_route_checks(self, browser: Browser) -> None:
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()

        for route in CONTRACT_ROUTES:
            route_url = self.make_url(route)
            console_errors: List[str] = []
            page_errors: List[str] = []

            def handle_console(msg):
                if msg.type == "error":
                    console_errors.append(msg.text)

            def handle_pageerror(err):
                page_errors.append(str(err))

            page.on("console", handle_console)
            page.on("pageerror", handle_pageerror)

            try:
                response = page.goto(route_url, wait_until="networkidle", timeout=15000)
            except Exception as e:
                page.remove_listener("console", handle_console)
                page.remove_listener("pageerror", handle_pageerror)
                self.add_check(
                    check_id=f"route_navigation_{route}",
                    category="routes",
                    name=f"Navigation to {route}",
                    status="FAIL",
                    observation=f"Failed to load {route_url}: {e}",
                )
                continue

            # HTTP status check
            status_code = response.status if response else 0
            if route.endswith("404.html"):
                # Static servers often serve 404.html directly with 200, custom servers with 404
                if status_code in (200, 404):
                    self.add_check(
                        check_id=f"http_status_{route}",
                        category="routes",
                        name=f"HTTP status for {route}",
                        status="PASS",
                        observation=f"Received expected HTTP {status_code}",
                        details={"status_code": status_code},
                    )
                else:
                    self.add_check(
                        check_id=f"http_status_{route}",
                        category="routes",
                        name=f"HTTP status for {route}",
                        status="FAIL",
                        observation=f"Unexpected status code {status_code} for {route}",
                        details={"status_code": status_code},
                    )
            else:
                if status_code == 200:
                    self.add_check(
                        check_id=f"http_status_{route}",
                        category="routes",
                        name=f"HTTP status for {route}",
                        status="PASS",
                        observation=f"Received HTTP 200 OK",
                        details={"status_code": status_code},
                    )
                else:
                    self.add_check(
                        check_id=f"http_status_{route}",
                        category="routes",
                        name=f"HTTP status for {route}",
                        status="FAIL",
                        observation=f"Expected HTTP 200 but received {status_code}",
                        details={"status_code": status_code},
                    )

            # Console JS error check
            if console_errors or page_errors:
                self.add_check(
                    check_id=f"console_errors_{route}",
                    category="console",
                    name=f"Console error check for {route}",
                    status="FAIL",
                    observation=f"Encountered JS errors: console={console_errors}, pageerror={page_errors}",
                    details={"console_errors": console_errors, "page_errors": page_errors},
                )
            else:
                self.add_check(
                    check_id=f"console_errors_{route}",
                    category="console",
                    name=f"Console error check for {route}",
                    status="PASS",
                    observation="Zero console JS errors or uncaught exceptions",
                )

            # Page Title check
            title = page.title().strip()
            if title:
                self.add_check(
                    check_id=f"title_{route}",
                    category="title",
                    name=f"Document title on {route}",
                    status="PASS",
                    observation=f"Title present: '{title}'",
                    details={"title": title},
                )
            else:
                self.add_check(
                    check_id=f"title_{route}",
                    category="title",
                    name=f"Document title on {route}",
                    status="FAIL",
                    observation="Document title is missing or empty",
                )

            # H1 check: exactly one visible h1
            h1_loc = page.locator("h1")
            h1_count = h1_loc.count()
            if h1_count == 1:
                h1_text = h1_loc.first.inner_text().strip()
                if h1_text and h1_loc.first.is_visible():
                    self.add_check(
                        check_id=f"h1_{route}",
                        category="h1",
                        name=f"Single H1 on {route}",
                        status="PASS",
                        observation=f"Exactly one visible <h1>: '{h1_text}'",
                        details={"h1_text": h1_text},
                    )
                else:
                    self.add_check(
                        check_id=f"h1_{route}",
                        category="h1",
                        name=f"Single H1 on {route}",
                        status="FAIL",
                        observation=f"<h1> is empty or not visible (text: '{h1_text}')",
                        details={"h1_text": h1_text},
                    )
            else:
                self.add_check(
                    check_id=f"h1_{route}",
                    category="h1",
                    name=f"Single H1 on {route}",
                    status="FAIL",
                    observation=f"Expected exactly 1 <h1>, found {h1_count}",
                    details={"h1_count": h1_count},
                )

            # Landmarks: header, nav, main#main, footer
            landmarks = {
                "header": page.locator("header.site-header, header, [role='banner']").count() > 0,
                "nav": page.locator("nav.site-nav, nav, [role='navigation']").count() > 0,
                "main#main": page.locator("main#main").count() > 0,
                "footer": page.locator("footer.site-footer, footer, [role='contentinfo']").count() > 0,
            }
            missing_landmarks = [lm for lm, present in landmarks.items() if not present]
            if not missing_landmarks:
                self.add_check(
                    check_id=f"landmarks_{route}",
                    category="landmarks",
                    name=f"Semantic landmarks on {route}",
                    status="PASS",
                    observation="All primary landmarks verified: header, nav, main#main, footer",
                    details=landmarks,
                )
            else:
                self.add_check(
                    check_id=f"landmarks_{route}",
                    category="landmarks",
                    name=f"Semantic landmarks on {route}",
                    status="FAIL",
                    observation=f"Missing landmarks on {route}: {missing_landmarks}",
                    details=landmarks,
                )

            # Internal navigation check on header nav (4 items: latest, learn, resources, about)
            nav_links = page.locator("nav.site-nav a")
            link_hrefs = [nav_links.nth(i).get_attribute("href") or "" for i in range(nav_links.count())]
            expected_destinations = ["latest", "learn", "resources", "about"]
            missing_links = []
            for dest in expected_destinations:
                matched = any(dest in href for href in link_hrefs)
                if not matched:
                    missing_links.append(dest)

            unexpected_features = [h for h in link_hrefs if "/features/" in h or "/zh/features/" in h]

            if not missing_links and not unexpected_features:
                self.add_check(
                    check_id=f"nav_links_{route}",
                    category="navigation",
                    name=f"Primary nav links on {route}",
                    status="PASS",
                    observation=f"Found internal navigation links (4 items): {link_hrefs}",
                    details={"hrefs": link_hrefs},
                )
            else:
                self.add_check(
                    check_id=f"nav_links_{route}",
                    category="navigation",
                    name=f"Primary nav links on {route}",
                    status="FAIL",
                    observation=f"Nav links mismatch: missing={missing_links}, unexpected_features={unexpected_features} in {link_hrefs}",
                    details={"missing": missing_links, "unexpected": unexpected_features, "hrefs": link_hrefs},
                )

            # Horizontal overflow check across 3 viewports
            self.check_horizontal_overflow(page, route)
            page.remove_listener("console", handle_console)
            page.remove_listener("pageerror", handle_pageerror)

        context.close()

    def check_horizontal_overflow(self, page: Page, route: str) -> None:
        for vp in VIEWPORTS:
            w, h = vp["width"], vp["height"]
            vp_name = vp["name"]
            page.set_viewport_size({"width": w, "height": h})
            page.wait_for_timeout(50)  # settle reflow

            overflow_info = page.evaluate("""() => {
                const clientWidth = document.documentElement.clientWidth || window.innerWidth;
                const scrollWidth = document.documentElement.scrollWidth;
                const bodyScrollWidth = document.body ? document.body.scrollWidth : 0;
                const maxScroll = Math.max(scrollWidth, bodyScrollWidth);
                // 1px subpixel tolerance
                const overflows = maxScroll > (clientWidth + 1);

                let offending = [];
                if (overflows) {
                    const elements = document.querySelectorAll('*');
                    for (const el of elements) {
                        const rect = el.getBoundingClientRect();
                        if (rect.right > clientWidth + 1 || rect.width > clientWidth + 1) {
                            offending.push({
                                tag: el.tagName.toLowerCase(),
                                id: el.id || null,
                                className: typeof el.className === 'string' ? el.className.trim() : '',
                                right: Math.round(rect.right),
                                width: Math.round(rect.width)
                            });
                            if (offending.length >= 5) break;
                        }
                    }
                }
                return {
                    clientWidth: clientWidth,
                    scrollWidth: scrollWidth,
                    bodyScrollWidth: bodyScrollWidth,
                    maxScroll: maxScroll,
                    overflows: overflows,
                    offending: offending
                };
            }""")

            if not overflow_info["overflows"]:
                self.add_check(
                    check_id=f"overflow_{route}_{vp_name}",
                    category="overflow",
                    name=f"Horizontal overflow {vp_name} ({w}x{h}) on {route}",
                    status="PASS",
                    observation=f"No horizontal overflow (scrollWidth: {overflow_info['scrollWidth']}, clientWidth: {overflow_info['clientWidth']})",
                    details=overflow_info,
                )
            else:
                self.add_check(
                    check_id=f"overflow_{route}_{vp_name}",
                    category="overflow",
                    name=f"Horizontal overflow {vp_name} ({w}x{h}) on {route}",
                    status="FAIL",
                    observation=f"Horizontal overflow detected at {w}x{h}: scrollWidth={overflow_info['scrollWidth']}, clientWidth={overflow_info['clientWidth']}. Offending elements: {overflow_info['offending']}",
                    details=overflow_info,
                )

    def run_skip_link_check(self, browser: Browser) -> None:
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.goto(self.make_url("/"), wait_until="networkidle")

        skip_link = page.locator(".skip-link, a[href='#main']")
        if skip_link.count() == 0:
            self.add_check(
                check_id="skip_link_existence",
                category="accessibility",
                name="Skip link presence",
                status="FAIL",
                observation="No skip link matching selector '.skip-link, a[href=\"#main\"]' found",
            )
            context.close()
            return

        href = skip_link.first.get_attribute("href") or ""
        if not href.endswith("#main"):
            self.add_check(
                check_id="skip_link_href",
                category="accessibility",
                name="Skip link target",
                status="FAIL",
                observation=f"Skip link href '{href}' does not target '#main'",
            )
            context.close()
            return

        # Focus skip link via keyboard Tab
        focused = False
        for _ in range(3):
            page.keyboard.press("Tab")
            is_active = page.evaluate("""(target) => document.activeElement === target""", skip_link.first.element_handle())
            if is_active:
                focused = True
                break

        if not focused:
            active_desc = page.evaluate("""() => ({
                tag: document.activeElement ? document.activeElement.tagName : null,
                class: document.activeElement ? document.activeElement.className : null,
                id: document.activeElement ? document.activeElement.id : null
            })""")
            self.add_check(
                check_id="skip_link_focus",
                category="accessibility",
                name="Skip link keyboard focus",
                status="FAIL",
                observation=f"Tabbing did not focus skip link. Active element: {active_desc}",
            )
            context.close()
            return

        # Verify skip link is visible when focused
        is_visible_when_focused = skip_link.first.is_visible()
        if not is_visible_when_focused:
            self.add_check(
                check_id="skip_link_visibility",
                category="accessibility",
                name="Skip link visibility on focus",
                status="FAIL",
                observation="Skip link is not visible when focused",
            )
            context.close()
            return

        # Activate skip link via Enter key
        page.keyboard.press("Enter")
        page.wait_for_timeout(100)

        main_state = page.evaluate("""() => {
            const active = document.activeElement;
            const main = document.querySelector('main#main') || document.querySelector('main');
            return {
                isMainActive: active === main,
                activeTag: active ? active.tagName.toLowerCase() : null,
                activeId: active ? active.id : null,
                mainExists: !!main,
                mainTabIndex: main ? main.getAttribute('tabindex') : null,
                urlHash: window.location.hash
            };
        }""")

        if main_state["mainTabIndex"] != "-1":
            self.add_check(
                check_id="main_tabindex",
                category="accessibility",
                name="Main landmark tabindex=-1",
                status="FAIL",
                observation=f"main#main has tabindex='{main_state['mainTabIndex']}', expected '-1'",
                details=main_state,
            )
        else:
            self.add_check(
                check_id="main_tabindex",
                category="accessibility",
                name="Main landmark tabindex=-1",
                status="PASS",
                observation="main#main correctly configured with tabindex='-1'",
                details=main_state,
            )

        if main_state["isMainActive"]:
            self.add_check(
                check_id="skip_link_focus_main",
                category="accessibility",
                name="Skip link focuses main element",
                status="PASS",
                observation="Activating skip link via Enter focused main#main",
                details=main_state,
            )
        else:
            self.add_check(
                check_id="skip_link_focus_main",
                category="accessibility",
                name="Skip link focuses main element",
                status="FAIL",
                observation=f"Active element after skip link activation is {main_state['activeTag']}#{main_state['activeId']}, expected main#main",
                details=main_state,
            )

        context.close()

    def run_resources_filter_checks(self, browser: Browser) -> None:
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.goto(self.make_url("/resources/"), wait_until="networkidle")

        # 1. Verify cards count (query actual cards, non-hardcoded)
        cards = page.locator(".resource-card")
        total_cards = cards.count()
        if total_cards == 0:
            self.add_check(
                check_id="resources_initial_count",
                category="resources",
                name="Resources initial card count",
                status="FAIL",
                observation="Zero .resource-card elements found on /resources/",
            )
            context.close()
            return

        self.add_check(
            check_id="resources_initial_count",
            category="resources",
            name="Resources initial card count",
            status="PASS",
            observation=f"Found {total_cards} resource cards rendered",
            details={"total_cards": total_cards},
        )

        # 2. Verify controls visibility in JS mode
        controls = page.locator("#resource-controls")
        if controls.count() > 0 and controls.first.is_visible():
            self.add_check(
                check_id="resources_controls_visible_js",
                category="resources",
                name="Filter controls visible with JS",
                status="PASS",
                observation="#resource-controls is visible when JS is enabled",
            )
        else:
            self.add_check(
                check_id="resources_controls_visible_js",
                category="resources",
                name="Filter controls visible with JS",
                status="FAIL",
                observation="#resource-controls is missing or not visible with JS",
            )

        # 3. Verify #resource-count role=status and count text
        count_el = page.locator("#resource-count")
        if count_el.count() > 0 and count_el.first.is_visible():
            role_attr = count_el.first.get_attribute("role")
            count_text = count_el.first.inner_text().strip()
            if role_attr == "status" and str(total_cards) in count_text:
                self.add_check(
                    check_id="resources_count_element",
                    category="resources",
                    name="#resource-count role and text",
                    status="PASS",
                    observation=f"#resource-count has role='status' and displays count: '{count_text}'",
                    details={"count_text": count_text, "role": role_attr},
                )
            else:
                self.add_check(
                    check_id="resources_count_element",
                    category="resources",
                    name="#resource-count role and text",
                    status="FAIL",
                    observation=f"#resource-count role='{role_attr}', text='{count_text}' (expected role='status' containing '{total_cards}')",
                    details={"count_text": count_text, "role": role_attr},
                )
        else:
            self.add_check(
                check_id="resources_count_element",
                category="resources",
                name="#resource-count role and text",
                status="FAIL",
                observation="#resource-count element is missing or not visible",
            )

        # 4. Verify filter buttons initial aria-pressed
        all_button = page.locator("button[data-filter='All']")
        other_buttons = page.locator("button[data-filter]:not([data-filter='All'])")
        all_pressed = all_button.first.get_attribute("aria-pressed") if all_button.count() > 0 else None

        other_pressed_states = []
        for i in range(other_buttons.count()):
            btn = other_buttons.nth(i)
            other_pressed_states.append({
                "filter": btn.get_attribute("data-filter"),
                "aria_pressed": btn.get_attribute("aria-pressed"),
            })

        if all_pressed == "true" and all(b["aria_pressed"] == "false" for b in other_pressed_states):
            self.add_check(
                check_id="resources_aria_pressed_initial",
                category="resources",
                name="Initial filter button aria-pressed",
                status="PASS",
                observation=f"'All' button aria-pressed='true', {len(other_pressed_states)} category buttons aria-pressed='false'",
                details={"all_pressed": all_pressed, "other_buttons": other_pressed_states},
            )
        else:
            self.add_check(
                check_id="resources_aria_pressed_initial",
                category="resources",
                name="Initial filter button aria-pressed",
                status="FAIL",
                observation=f"Incorrect aria-pressed: All={all_pressed}, categories={other_pressed_states}",
                details={"all_pressed": all_pressed, "other_buttons": other_pressed_states},
            )

        # 4b. Verify Format Tabs and Tabpanel ARIA Contract
        tablist = page.locator("[role='tablist']")
        tabs = page.locator("[role='tab']")
        panels = page.locator("[role='tabpanel']")

        tablist_label = tablist.first.get_attribute("aria-label") if tablist.count() > 0 else None
        tab_count = tabs.count()
        panel_count = panels.count()
        panel_id = panels.first.get_attribute("id") if panel_count > 0 else None
        panel_tabindex = panels.first.get_attribute("tabindex") if panel_count > 0 else None
        panel_labelled = panels.first.get_attribute("aria-labelledby") if panel_count > 0 else None

        all_tab = page.locator("#tab-all")
        all_tab_selected = all_tab.first.get_attribute("aria-selected") if all_tab.count() > 0 else None
        all_tab_tabindex = all_tab.first.get_attribute("tabindex") if all_tab.count() > 0 else None

        if (
            tablist.count() > 0
            and tablist_label
            and tab_count >= 1
            and panel_count == 1
            and panel_id == "resources-panel"
            and panel_tabindex == "0"
            and panel_labelled == "tab-all"
            and all_tab_selected == "true"
            and all_tab_tabindex == "0"
        ):
            self.add_check(
                check_id="resources_format_tabs_aria_contract",
                category="resources",
                name="Format tabs and single tabpanel ARIA contract",
                status="PASS",
                observation=f"Tablist has aria-label='{tablist_label}', {tab_count} tabs, single panel#resources-panel with aria-labelledby='tab-all', tabindex='0'",
                details={"tabs": tab_count, "panels": panel_count, "tablist_label": tablist_label},
            )
        else:
            self.add_check(
                check_id="resources_format_tabs_aria_contract",
                category="resources",
                name="Format tabs and single tabpanel ARIA contract",
                status="FAIL",
                observation=f"Tab ARIA contract violation: tablist={tablist.count()}, label={tablist_label}, tabs={tab_count}, panels={panel_count}, panel_id={panel_id}, panel_tabindex={panel_tabindex}, panel_labelled={panel_labelled}, all_selected={all_tab_selected}, all_tabindex={all_tab_tabindex}",
            )

        # 4c. Format Tabs Keyboard Navigation
        if tab_count > 1:
            all_tab.first.focus()
            page.wait_for_timeout(50)

            # Press ArrowRight to move to next tab
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(50)

            kb_state_1 = page.evaluate("""() => {
                const active = document.activeElement;
                const panel = document.getElementById('resources-panel');
                return {
                    activeId: active ? active.id : null,
                    activeRole: active ? active.getAttribute('role') : null,
                    activeSelected: active ? active.getAttribute('aria-selected') : null,
                    activeTabindex: active ? active.getAttribute('tabindex') : null,
                    panelLabelledBy: panel ? panel.getAttribute('aria-labelledby') : null
                };
            }""")

            # Press ArrowLeft to move back to tab-all
            page.keyboard.press("ArrowLeft")
            page.wait_for_timeout(50)

            kb_state_2 = page.evaluate("""() => {
                const active = document.activeElement;
                const panel = document.getElementById('resources-panel');
                return {
                    activeId: active ? active.id : null,
                    activeRole: active ? active.getAttribute('role') : null,
                    activeSelected: active ? active.getAttribute('aria-selected') : null,
                    panelLabelledBy: panel ? panel.getAttribute('aria-labelledby') : null
                };
            }""")

            # Test Home and End keys
            page.keyboard.press("End")
            page.wait_for_timeout(50)
            end_active_id = page.evaluate("""() => document.activeElement ? document.activeElement.id : null""")

            page.keyboard.press("Home")
            page.wait_for_timeout(50)
            home_active_id = page.evaluate("""() => document.activeElement ? document.activeElement.id : null""")

            if (
                kb_state_1["activeId"] != "tab-all"
                and kb_state_1["activeSelected"] == "true"
                and kb_state_1["panelLabelledBy"] == kb_state_1["activeId"]
                and kb_state_2["activeId"] == "tab-all"
                and kb_state_2["activeSelected"] == "true"
                and home_active_id == "tab-all"
            ):
                self.add_check(
                    check_id="resources_tabs_keyboard_navigation",
                    category="resources",
                    name="Format tabs keyboard navigation (Arrow keys, Home, End)",
                    status="PASS",
                    observation=f"Arrow keys, Home, End navigated correctly between tabs (next={kb_state_1['activeId']}, home={home_active_id}, end={end_active_id})",
                    details={"kb_state_1": kb_state_1, "kb_state_2": kb_state_2, "end": end_active_id},
                )
            else:
                self.add_check(
                    check_id="resources_tabs_keyboard_navigation",
                    category="resources",
                    name="Format tabs keyboard navigation (Arrow keys, Home, End)",
                    status="FAIL",
                    observation=f"Keyboard navigation failed: step1={kb_state_1}, step2={kb_state_2}, end={end_active_id}, home={home_active_id}",
                )

        # A resource with a paper, benchmark, and dataset remains one card.
        cross_listed = page.locator('.resource-card').filter(
            has=page.locator('h2 a[href="https://arxiv.org/abs/2505.00212"]')
        )
        memberships_ok = cross_listed.count() == 1
        for format_name in ("paper", "dataset", "benchmark"):
            page.locator(f"#tab-{format_name}").click()
            memberships_ok = memberships_ok and cross_listed.is_visible()
        page.locator("#tab-dataset").click()
        dataset_total = page.locator('.resource-card:visible').count()
        dataset_label = page.locator('#tab-dataset .format-count').inner_text()
        memberships_ok = memberships_ok and dataset_label == f"({dataset_total})"
        memberships_ok = memberships_ok and page.locator('.resource-card').filter(
            has=page.locator('h2 a[href="https://arxiv.org/abs/2509.14295"]')
        ).is_visible()
        all_tab.first.click()
        memberships_ok = memberships_ok and page.locator('.resource-card:visible').count() == total_cards
        self.add_check(
            check_id="resources_cross_listed_formats", category="resources",
            name="Cross-listed resources appear under every supported format without duplication",
            status="PASS" if memberships_ok else "FAIL",
            observation=f"Who&When visible as Paper/Dataset/Benchmark; Dataset count {dataset_total}; All restores {total_cards} unique cards: {memberships_ok}",
        )

        # 5. Category Filtering
        # Collect distinct categories from actual cards
        card_categories = page.evaluate("""() => {
            const cards = Array.from(document.querySelectorAll('.resource-card'));
            return Array.from(new Set(cards.map(c => c.getAttribute('data-category')).filter(Boolean)));
        }""")

        if not card_categories:
            self.add_check(
                check_id="resources_card_data_categories",
                category="resources",
                name="Cards have data-category attribute",
                status="FAIL",
                observation="No data-category attributes found on .resource-card elements",
            )
            context.close()
            return

        target_category = card_categories[0]
        cat_button = page.locator(f"button[data-filter='{target_category}']")
        if cat_button.count() == 0:
            self.add_check(
                check_id="resources_category_button_found",
                category="resources",
                name=f"Filter button for '{target_category}'",
                status="FAIL",
                observation=f"Button button[data-filter='{target_category}'] not found",
            )
            context.close()
            return

        # Click category button
        cat_button.first.click()
        page.wait_for_timeout(100)

        # Verify aria-pressed after click
        cat_pressed = cat_button.first.get_attribute("aria-pressed")
        all_pressed_after = all_button.first.get_attribute("aria-pressed")
        if cat_pressed == "true" and all_pressed_after == "false":
            self.add_check(
                check_id="resources_category_aria_pressed",
                category="resources",
                name=f"Filter button aria-pressed on click '{target_category}'",
                status="PASS",
                observation=f"'{target_category}' aria-pressed='true' and 'All' aria-pressed='false'",
            )
        else:
            self.add_check(
                check_id="resources_category_aria_pressed",
                category="resources",
                name=f"Filter button aria-pressed on click '{target_category}'",
                status="FAIL",
                observation=f"Expected '{target_category}' aria-pressed='true' (got {cat_pressed}) and All aria-pressed='false' (got {all_pressed_after})",
            )

        # Verify card visibility matches category
        cat_filter_eval = page.evaluate("""(target) => {
            const cards = Array.from(document.querySelectorAll('.resource-card'));
            let visibleMatching = 0;
            let visibleNonMatching = 0;
            let hiddenMatching = 0;
            let hiddenNonMatching = 0;
            for (const c of cards) {
                const isVisible = (c.offsetParent !== null) && !c.hidden && window.getComputedStyle(c).display !== 'none';
                const matches = (c.getAttribute('data-category') === target);
                if (isVisible) {
                    if (matches) visibleMatching++;
                    else visibleNonMatching++;
                } else {
                    if (matches) hiddenMatching++;
                    else hiddenNonMatching++;
                }
            }
            return {
                visibleMatching,
                visibleNonMatching,
                hiddenMatching,
                hiddenNonMatching,
                total: cards.length
            };
        }""", target_category)

        if cat_filter_eval["visibleNonMatching"] == 0 and cat_filter_eval["visibleMatching"] > 0:
            self.add_check(
                check_id="resources_category_card_visibility",
                category="resources",
                name=f"Card visibility for category '{target_category}'",
                status="PASS",
                observation=f"Only {cat_filter_eval['visibleMatching']} matching cards visible, 0 non-matching visible",
                details=cat_filter_eval,
            )
        else:
            self.add_check(
                check_id="resources_category_card_visibility",
                category="resources",
                name=f"Card visibility for category '{target_category}'",
                status="FAIL",
                observation=f"Category filter leak: visibleNonMatching={cat_filter_eval['visibleNonMatching']}, visibleMatching={cat_filter_eval['visibleMatching']}",
                details=cat_filter_eval,
            )

        # 6. Combined Category + Text Search
        search_input = page.locator("input#resource-search")
        if search_input.count() == 0 or not search_input.first.is_visible():
            self.add_check(
                check_id="resources_search_input",
                category="resources",
                name="Search input input#resource-search",
                status="FAIL",
                observation="input#resource-search missing or not visible",
            )
            context.close()
            return

        # Pick search term from visible matching card
        search_term = page.evaluate("""(target) => {
            const cards = Array.from(document.querySelectorAll('.resource-card'));
            for (const c of cards) {
                if (c.getAttribute('data-category') === target) {
                    const ds = c.getAttribute('data-search') || '';
                    const words = ds.toLowerCase().split(/\\s+/).filter(w => w.length >= 4);
                    if (words.length > 0) return words[0];
                    const text = c.innerText.toLowerCase().split(/\\s+/).filter(w => w.length >= 4);
                    if (text.length > 0) return text[0];
                }
            }
            return null;
        }""", target_category)

        if search_term:
            search_input.first.fill(search_term)
            page.wait_for_timeout(100)

            combined_eval = page.evaluate("""(args) => {
                const { targetCat, term } = args;
                const cards = Array.from(document.querySelectorAll('.resource-card'));
                let visible = 0;
                let violations = 0;
                for (const c of cards) {
                    const isVisible = (c.offsetParent !== null) && !c.hidden && window.getComputedStyle(c).display !== 'none';
                    if (isVisible) {
                        visible++;
                        const catMatch = c.getAttribute('data-category') === targetCat;
                        const ds = (c.getAttribute('data-search') || '').toLowerCase();
                        const text = c.innerText.toLowerCase();
                        const textMatch = ds.includes(term) || text.includes(term);
                        if (!catMatch || !textMatch) {
                            violations++;
                        }
                    }
                }
                return { visible, violations, term };
            }""", {"targetCat": target_category, "term": search_term})

            if combined_eval["violations"] == 0 and combined_eval["visible"] > 0:
                self.add_check(
                    check_id="resources_combined_filter",
                    category="resources",
                    name="Combined category + text search",
                    status="PASS",
                    observation=f"Combined filter '{target_category}' + '{search_term}' yielded {combined_eval['visible']} valid cards with 0 violations",
                    details=combined_eval,
                )
            else:
                self.add_check(
                    check_id="resources_combined_filter",
                    category="resources",
                    name="Combined category + text search",
                    status="FAIL",
                    observation=f"Combined filter failure: visible={combined_eval['visible']}, violations={combined_eval['violations']}",
                    details=combined_eval,
                )

        # 7. No Results State
        search_input.first.fill("zzz_nonexistent_query_guaranteed_empty_state_12345")
        page.wait_for_timeout(100)

        no_results_eval = page.evaluate("""() => {
            const cards = Array.from(document.querySelectorAll('.resource-card'));
            const visibleCards = cards.filter(c => (c.offsetParent !== null) && !c.hidden && window.getComputedStyle(c).display !== 'none');
            const noResultsEl = document.getElementById('no-results');
            const noResultsVisible = noResultsEl && (noResultsEl.offsetParent !== null) && !noResultsEl.hidden && window.getComputedStyle(noResultsEl).display !== 'none';
            const countEl = document.getElementById('resource-count');
            const countText = countEl ? countEl.innerText.trim() : '';
            return {
                visibleCardCount: visibleCards.length,
                noResultsExists: !!noResultsEl,
                noResultsVisible: !!noResultsVisible,
                countText: countText
            };
        }""")

        if no_results_eval["visibleCardCount"] == 0 and no_results_eval["noResultsVisible"]:
            self.add_check(
                check_id="resources_no_results_state",
                category="resources",
                name="Empty state and #no-results display",
                status="PASS",
                observation=f"0 visible cards, #no-results is visible, count text: '{no_results_eval['countText']}'",
                details=no_results_eval,
            )
        else:
            self.add_check(
                check_id="resources_no_results_state",
                category="resources",
                name="Empty state and #no-results display",
                status="FAIL",
                observation=f"Expected 0 cards and visible #no-results: visibleCards={no_results_eval['visibleCardCount']}, noResultsVisible={no_results_eval['noResultsVisible']}",
                details=no_results_eval,
            )

        # 8. Clear search and reset All
        search_input.first.fill("")
        all_button.first.click()
        all_tab.first.click()
        page.wait_for_timeout(100)

        reset_eval = page.evaluate("""(totalExpected) => {
            const cards = Array.from(document.querySelectorAll('.resource-card'));
            const visibleCards = cards.filter(c => (c.offsetParent !== null) && !c.hidden && window.getComputedStyle(c).display !== 'none');
            const noResultsEl = document.getElementById('no-results');
            const noResultsVisible = noResultsEl && (noResultsEl.offsetParent !== null) && !noResultsEl.hidden && window.getComputedStyle(noResultsEl).display !== 'none';
            const allBtn = document.querySelector("button[data-filter='All']");
            const allPressed = allBtn ? allBtn.getAttribute('aria-pressed') : null;
            const allTab = document.getElementById('tab-all');
            const allTabSelected = allTab ? allTab.getAttribute('aria-selected') : null;
            const countEl = document.getElementById('resource-count');
            const countText = countEl ? countEl.innerText.trim() : '';
            return {
                visibleCount: visibleCards.length,
                noResultsVisible: !!noResultsVisible,
                allPressed: allPressed,
                allTabSelected: allTabSelected,
                countText: countText
            };
        }""", total_cards)

        if (
            reset_eval["visibleCount"] == total_cards
            and not reset_eval["noResultsVisible"]
            and reset_eval["allPressed"] == "true"
            and reset_eval["allTabSelected"] == "true"
        ):
            self.add_check(
                check_id="resources_reset_all",
                category="resources",
                name="Reset 'All' and clearing search",
                status="PASS",
                observation=f"Reset restored all {total_cards} cards, #no-results hidden, 'All' category and format tab active",
                details=reset_eval,
            )
        else:
            self.add_check(
                check_id="resources_reset_all",
                category="resources",
                name="Reset 'All' and clearing search",
                status="FAIL",
                observation=f"Reset failed: visibleCount={reset_eval['visibleCount']}/{total_cards}, allPressed={reset_eval['allPressed']}, allTabSelected={reset_eval['allTabSelected']}, noResultsVisible={reset_eval['noResultsVisible']}",
                details=reset_eval,
            )

        # 9. Deep-link URL state check (?q=Inspect)
        deep_url = self.make_url("/resources/?q=Inspect")
        page.goto(deep_url, wait_until="networkidle")
        page.wait_for_timeout(100)

        deep_eval = page.evaluate("""() => {
            const searchInput = document.getElementById('resource-search');
            const cards = Array.from(document.querySelectorAll('.resource-card'));
            const visibleCards = cards.filter(c => (c.offsetParent !== null) && !c.hidden && window.getComputedStyle(c).display !== 'none');
            return {
                inputValue: searchInput ? searchInput.value : '',
                visibleCards: visibleCards.length,
                totalCards: cards.length
            };
        }""")

        if deep_eval["inputValue"] == "Inspect" and deep_eval["visibleCards"] >= 1 and deep_eval["visibleCards"] < deep_eval["totalCards"]:
            self.add_check(
                check_id="resources_deep_link",
                category="resources",
                name="Deep-linking via URL parameters (?q=Inspect) with case preservation",
                status="PASS",
                observation=f"Loaded deep-link URL: search input populated with '{deep_eval['inputValue']}' and filtered to {deep_eval['visibleCards']} visible cards",
                details=deep_eval,
            )
        else:
            self.add_check(
                check_id="resources_deep_link",
                category="resources",
                name="Deep-linking via URL parameters (?q=Inspect) with case preservation",
                status="FAIL",
                observation=f"Deep-link check failed: input='{deep_eval['inputValue']}', visible={deep_eval['visibleCards']}/{deep_eval['totalCards']}",
                details=deep_eval,
            )

        # 10. Unknown format parameter fallback (?format=bogus)
        bogus_fmt_url = self.make_url("/resources/?format=bogus")
        page.goto(bogus_fmt_url, wait_until="networkidle")
        page.wait_for_timeout(100)

        bogus_fmt_eval = page.evaluate("""(totalExpected) => {
            const allTab = document.getElementById('tab-all');
            const allBtn = document.querySelector("button[data-filter='All'], button[data-filter='all']");
            const panel = document.getElementById('resources-panel');
            const cards = Array.from(document.querySelectorAll('.resource-card'));
            const visibleCards = cards.filter(c => (c.offsetParent !== null) && !c.hidden && window.getComputedStyle(c).display !== 'none');
            const noResultsEl = document.getElementById('no-results');
            const countEl = document.getElementById('resource-count');
            return {
                allTabSelected: allTab ? allTab.getAttribute('aria-selected') : null,
                allTabTabindex: allTab ? allTab.getAttribute('tabindex') : null,
                panelLabelledBy: panel ? panel.getAttribute('aria-labelledby') : null,
                allBtnPressed: allBtn ? allBtn.getAttribute('aria-pressed') : null,
                visibleCards: visibleCards.length,
                totalCards: cards.length,
                noResultsVisible: noResultsEl && (noResultsEl.offsetParent !== null) && !noResultsEl.hidden && window.getComputedStyle(noResultsEl).display !== 'none',
                countText: countEl ? countEl.innerText.trim() : ''
            };
        }""", total_cards)

        if (
            bogus_fmt_eval["allTabSelected"] == "true"
            and bogus_fmt_eval["allTabTabindex"] == "0"
            and bogus_fmt_eval["panelLabelledBy"] == "tab-all"
            and bogus_fmt_eval["allBtnPressed"] == "true"
            and bogus_fmt_eval["visibleCards"] == total_cards
            and not bogus_fmt_eval["noResultsVisible"]
            and str(total_cards) in bogus_fmt_eval["countText"]
        ):
            self.add_check(
                check_id="resources_unknown_format_fallback",
                category="resources",
                name="Unknown format falls back to All with all cards visible (?format=bogus)",
                status="PASS",
                observation=f"Normalized ?format=bogus to 'All': allTab selected, panel labelled, {bogus_fmt_eval['visibleCards']}/{total_cards} cards visible, empty state hidden",
                details=bogus_fmt_eval,
            )
        else:
            self.add_check(
                check_id="resources_unknown_format_fallback",
                category="resources",
                name="Unknown format falls back to All with all cards visible (?format=bogus)",
                status="FAIL",
                observation=f"Unknown format fallback failed: tabSelected={bogus_fmt_eval['allTabSelected']}, visible={bogus_fmt_eval['visibleCards']}/{total_cards}, noResultsVisible={bogus_fmt_eval['noResultsVisible']}",
                details=bogus_fmt_eval,
            )

        # 11. Unknown category parameter fallback (?category=bogus)
        bogus_cat_url = self.make_url("/resources/?category=bogus")
        page.goto(bogus_cat_url, wait_until="networkidle")
        page.wait_for_timeout(100)

        bogus_cat_eval = page.evaluate("""(totalExpected) => {
            const allTab = document.getElementById('tab-all');
            const allBtn = document.querySelector("button[data-filter='All'], button[data-filter='all']");
            const otherBtns = Array.from(document.querySelectorAll("button[data-filter]:not([data-filter='All']):not([data-filter='all'])"));
            const cards = Array.from(document.querySelectorAll('.resource-card'));
            const visibleCards = cards.filter(c => (c.offsetParent !== null) && !c.hidden && window.getComputedStyle(c).display !== 'none');
            const noResultsEl = document.getElementById('no-results');
            const countEl = document.getElementById('resource-count');
            return {
                allTabSelected: allTab ? allTab.getAttribute('aria-selected') : null,
                allBtnPressed: allBtn ? allBtn.getAttribute('aria-pressed') : null,
                otherPressed: otherBtns.map(b => b.getAttribute('aria-pressed')),
                visibleCards: visibleCards.length,
                totalCards: cards.length,
                noResultsVisible: noResultsEl && (noResultsEl.offsetParent !== null) && !noResultsEl.hidden && window.getComputedStyle(noResultsEl).display !== 'none',
                countText: countEl ? countEl.innerText.trim() : ''
            };
        }""", total_cards)

        if (
            bogus_cat_eval["allBtnPressed"] == "true"
            and all(p == "false" for p in bogus_cat_eval["otherPressed"])
            and bogus_cat_eval["allTabSelected"] == "true"
            and bogus_cat_eval["visibleCards"] == total_cards
            and not bogus_cat_eval["noResultsVisible"]
            and str(total_cards) in bogus_cat_eval["countText"]
        ):
            self.add_check(
                check_id="resources_unknown_category_fallback",
                category="resources",
                name="Unknown category falls back to All with all cards visible (?category=bogus)",
                status="PASS",
                observation=f"Normalized ?category=bogus to 'All': allBtn pressed, other categories unpressed, {bogus_cat_eval['visibleCards']}/{total_cards} cards visible",
                details=bogus_cat_eval,
            )
        else:
            self.add_check(
                check_id="resources_unknown_category_fallback",
                category="resources",
                name="Unknown category falls back to All with all cards visible (?category=bogus)",
                status="FAIL",
                observation=f"Unknown category fallback failed: allBtnPressed={bogus_cat_eval['allBtnPressed']}, otherPressed={bogus_cat_eval['otherPressed']}, visible={bogus_cat_eval['visibleCards']}/{total_cards}",
                details=bogus_cat_eval,
            )

        # 12. Real popstate/back transition from filtered URL to bare URL
        # Start at clean /resources/
        page.goto(self.make_url("/resources/"), wait_until="networkidle")
        page.wait_for_timeout(100)

        # Push a history entry with filters and dispatch popstate (controlled history fixture)
        page.evaluate("""() => {
            window.history.pushState({ test: "filtered" }, '', '/resources/?format=collection&category=governance&q=NIST');
            window.dispatchEvent(new PopStateEvent('popstate'));
        }""")
        page.wait_for_timeout(100)

        fixture_state = page.evaluate("""() => {
            const input = document.getElementById('resource-search');
            const cards = Array.from(document.querySelectorAll('.resource-card'));
            const visibleCards = cards.filter(c => (c.offsetParent !== null) && !c.hidden && window.getComputedStyle(c).display !== 'none');
            return {
                url: window.location.pathname + window.location.search,
                inputValue: input ? input.value : '',
                visibleCount: visibleCards.length,
                totalCount: cards.length
            };
        }""")

        # Execute browser back navigation to return to bare /resources/
        page.go_back(wait_until="networkidle")
        page.wait_for_timeout(150)

        popstate_bare_state = page.evaluate("""(totalExpected) => {
            const input = document.getElementById('resource-search');
            const cards = Array.from(document.querySelectorAll('.resource-card'));
            const visibleCards = cards.filter(c => (c.offsetParent !== null) && !c.hidden && window.getComputedStyle(c).display !== 'none');
            const allTab = document.getElementById('tab-all');
            const allBtn = document.querySelector("button[data-filter='All'], button[data-filter='all']");
            const countEl = document.getElementById('resource-count');
            const noResultsEl = document.getElementById('no-results');
            return {
                url: window.location.pathname + window.location.search,
                inputValue: input ? input.value : '',
                visibleCount: visibleCards.length,
                totalCount: cards.length,
                allTabSelected: allTab ? allTab.getAttribute('aria-selected') : null,
                allTabTabindex: allTab ? allTab.getAttribute('tabindex') : null,
                allBtnPressed: allBtn ? allBtn.getAttribute('aria-pressed') : null,
                countText: countEl ? countEl.innerText.trim() : '',
                noResultsVisible: noResultsEl && (noResultsEl.offsetParent !== null) && !noResultsEl.hidden && window.getComputedStyle(noResultsEl).display !== 'none'
            };
        }""", total_cards)

        if (
            popstate_bare_state["inputValue"] == ""
            and popstate_bare_state["visibleCount"] == total_cards
            and popstate_bare_state["allTabSelected"] == "true"
            and popstate_bare_state["allTabTabindex"] == "0"
            and popstate_bare_state["allBtnPressed"] == "true"
            and not popstate_bare_state["noResultsVisible"]
            and str(total_cards) in popstate_bare_state["countText"]
        ):
            self.add_check(
                check_id="resources_popstate_back_transition",
                category="resources",
                name="Popstate/back transition from filtered URL to bare URL resets state",
                status="PASS",
                observation=f"Navigated back to bare URL {popstate_bare_state['url']}: search cleared, allTab active, allBtn pressed, all {total_cards} cards restored",
                details={"fixture": fixture_state, "after_back": popstate_bare_state},
            )
        else:
            self.add_check(
                check_id="resources_popstate_back_transition",
                category="resources",
                name="Popstate/back transition from filtered URL to bare URL resets state",
                status="FAIL",
                observation=f"Popstate back transition failed: input='{popstate_bare_state['inputValue']}', visible={popstate_bare_state['visibleCount']}/{total_cards}, tabSelected={popstate_bare_state['allTabSelected']}, btnPressed={popstate_bare_state['allBtnPressed']}",
                details={"fixture": fixture_state, "after_back": popstate_bare_state},
            )

        context.close()

    def run_latest_filter_checks(self, browser: Browser) -> None:
        """Browser tests for Latest all-content list filters, URL persistence, back/forward, and EN/ZH retention."""
        self.log("Running Latest filter categories, history, and bilingual switch acceptance checks...")
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()

        # 1. Load /latest/
        latest_url = self.make_url("/latest/")
        page.goto(latest_url, wait_until="networkidle")

        # Verify #latest-controls revealed by progressive enhancement
        controls_visible = page.evaluate("""() => {
            const controls = document.getElementById('latest-controls');
            return controls && !controls.hidden && window.getComputedStyle(controls).display !== 'none';
        }""")
        self.add_check(
            check_id="latest_controls_visible_with_js",
            category="latest_filtering",
            name="Latest controls unhidden with JS",
            status="PASS" if controls_visible else "FAIL",
            observation="Latest filter controls revealed progressively by JS" if controls_visible else "Controls missing or hidden with JS",
        )

        # Initial state: "all" button pressed, all cards visible
        state = page.evaluate("""() => {
            const allBtn = document.querySelector('#latest-controls button[data-kind="all"]');
            const cards = Array.from(document.querySelectorAll('.article-list .article-card'));
            const visible = cards.filter(c => !c.hidden && window.getComputedStyle(c).display !== 'none');
            const countEl = document.getElementById('latest-count');
            return {
                allPressed: allBtn && allBtn.getAttribute('aria-pressed') === 'true',
                totalCards: cards.length,
                visibleCards: visible.length,
                countText: countEl ? countEl.textContent : '',
            };
        }""")
        self.add_check(
            check_id="latest_initial_filter_all",
            category="latest_filtering",
            name="Initial filter state 'all'",
            status="PASS" if (state["allPressed"] and state["visibleCards"] == state["totalCards"] and state["totalCards"] > 0) else "FAIL",
            observation=f"All button pressed, {state['visibleCards']}/{state['totalCards']} cards visible, count='{state['countText']}'",
        )

        # 2. Click "News" filter
        page.click('#latest-controls button[data-kind="news"]')
        page.wait_for_timeout(50)
        news_state = page.evaluate("""() => {
            const btn = document.querySelector('#latest-controls button[data-kind="news"]');
            const allBtn = document.querySelector('#latest-controls button[data-kind="all"]');
            const cards = Array.from(document.querySelectorAll('.article-list .article-card'));
            const visible = cards.filter(c => !c.hidden && window.getComputedStyle(c).display !== 'none');
            const allMatchNews = visible.every(c => c.getAttribute('data-kind') === 'news');
            return {
                newsPressed: btn && btn.getAttribute('aria-pressed') === 'true',
                allPressed: allBtn && allBtn.getAttribute('aria-pressed') === 'true',
                visibleCount: visible.length,
                allMatchNews: allMatchNews,
                url: window.location.href,
            };
        }""")
        has_kind_news = "?kind=news" in news_state["url"]
        self.add_check(
            check_id="latest_filter_news",
            category="latest_filtering",
            name="Filter by News category (?kind=news)",
            status="PASS" if (news_state["newsPressed"] and not news_state["allPressed"] and news_state["allMatchNews"] and has_kind_news) else "FAIL",
            observation=f"News pressed, {news_state['visibleCount']} cards visible (all news), url='{news_state['url']}'",
        )

        # 3. Click "Analysis" filter (data-kind="feature")
        page.click('#latest-controls button[data-kind="feature"]')
        page.wait_for_timeout(50)
        analysis_state = page.evaluate("""() => {
            const btn = document.querySelector('#latest-controls button[data-kind="feature"]');
            const visible = Array.from(document.querySelectorAll('.article-list .article-card')).filter(c => !c.hidden && window.getComputedStyle(c).display !== 'none');
            const allMatchFeature = visible.every(c => c.getAttribute('data-kind') === 'feature');
            return {
                featurePressed: btn && btn.getAttribute('aria-pressed') === 'true',
                visibleCount: visible.length,
                allMatchFeature: allMatchFeature,
                url: window.location.href,
            };
        }""")
        has_kind_feature = "?kind=feature" in analysis_state["url"]
        self.add_check(
            check_id="latest_filter_analysis",
            category="latest_filtering",
            name="Filter by Analysis category (?kind=feature)",
            status="PASS" if (analysis_state["featurePressed"] and analysis_state["allMatchFeature"] and has_kind_feature) else "FAIL",
            observation=f"Analysis pressed, {analysis_state['visibleCount']} cards visible (all feature), url='{analysis_state['url']}'",
        )

        # 4. Click "Guides" filter (tests introduction + guide mapping to Guides)
        page.click('#latest-controls button[data-kind="guide"]')
        page.wait_for_timeout(50)
        guides_state = page.evaluate("""() => {
            const btn = document.querySelector('#latest-controls button[data-kind="guide"]');
            const visible = Array.from(document.querySelectorAll('.article-list .article-card')).filter(c => !c.hidden && window.getComputedStyle(c).display !== 'none');
            const allMatchGuide = visible.every(c => {
                const k = c.getAttribute('data-kind');
                return k === 'guide' || k === 'introduction';
            });
            const hasIntro = visible.some(c => c.getAttribute('data-kind') === 'introduction');
            const hasGuide = visible.some(c => c.getAttribute('data-kind') === 'guide');
            return {
                guidePressed: btn && btn.getAttribute('aria-pressed') === 'true',
                visibleCount: visible.length,
                allMatchGuide: allMatchGuide,
                hasIntro: hasIntro,
                hasGuide: hasGuide,
                url: window.location.href,
            };
        }""")
        has_kind_guide = "?kind=guide" in guides_state["url"]
        guides_pass = (guides_state["guidePressed"] and guides_state["allMatchGuide"] and guides_state["hasIntro"] and guides_state["hasGuide"] and has_kind_guide)
        self.add_check(
            check_id="latest_filter_guides",
            category="latest_filtering",
            name="Filter by Guides category (introduction + guide mapped to Guides)",
            status="PASS" if guides_pass else "FAIL",
            observation=f"Guides pressed, {guides_state['visibleCount']} cards visible, hasIntro={guides_state['hasIntro']}, hasGuide={guides_state['hasGuide']}, url='{guides_state['url']}'",
        )

        # 5. Click "Releases" filter
        page.click('#latest-controls button[data-kind="release"]')
        page.wait_for_timeout(50)
        release_state = page.evaluate("""() => {
            const btn = document.querySelector('#latest-controls button[data-kind="release"]');
            const visible = Array.from(document.querySelectorAll('.article-list .article-card')).filter(c => !c.hidden && window.getComputedStyle(c).display !== 'none');
            const allMatchRelease = visible.every(c => c.getAttribute('data-kind') === 'release');
            return {
                releasePressed: btn && btn.getAttribute('aria-pressed') === 'true',
                visibleCount: visible.length,
                allMatchRelease: allMatchRelease,
                url: window.location.href,
            };
        }""")
        has_kind_release = "?kind=release" in release_state["url"]
        release_pass = (release_state["releasePressed"] and release_state["allMatchRelease"] and has_kind_release)
        self.add_check(
            check_id="latest_filter_releases",
            category="latest_filtering",
            name="Filter by Releases category (?kind=release)",
            status="PASS" if release_pass else "FAIL",
            observation=f"Releases pressed, {release_state['visibleCount']} cards visible (all release), url='{release_state['url']}'",
        )

        # 6. Browser Back and Forward navigation retention
        page.go_back()
        page.wait_for_timeout(50)
        back_state = page.evaluate("""() => {
            const btn = document.querySelector('#latest-controls button[data-kind="guide"]');
            return {
                guidePressed: btn && btn.getAttribute('aria-pressed') === 'true',
                url: window.location.href,
            };
        }""")
        back_pass = back_state["guidePressed"] and "?kind=guide" in back_state["url"]
        self.add_check(
            check_id="latest_history_back",
            category="latest_filtering",
            name="Browser Back retains Guides filter",
            status="PASS" if back_pass else "FAIL",
            observation=f"Back to Guides: guidePressed={back_state['guidePressed']}, url='{back_state['url']}'",
        )

        page.go_forward()
        page.wait_for_timeout(50)
        fwd_state = page.evaluate("""() => {
            const btn = document.querySelector('#latest-controls button[data-kind="release"]');
            return {
                releasePressed: btn && btn.getAttribute('aria-pressed') === 'true',
                url: window.location.href,
            };
        }""")
        fwd_pass = fwd_state["releasePressed"] and "?kind=release" in fwd_state["url"]
        self.add_check(
            check_id="latest_history_forward",
            category="latest_filtering",
            name="Browser Forward retains Releases filter",
            status="PASS" if fwd_pass else "FAIL",
            observation=f"Forward to Releases: releasePressed={fwd_state['releasePressed']}, url='{fwd_state['url']}'",
        )

        # 7. Language Switch retains category across locales
        # Navigate directly to /latest/?kind=feature
        page.goto(self.make_url("/latest/?kind=feature"), wait_until="networkidle")
        zh_link_href = page.locator('.lang-switch a[hreflang="zh-CN"]').get_attribute('href') or ""
        zh_has_kind = "?kind=feature" in zh_link_href
        self.add_check(
            check_id="latest_lang_switch_preserves_query",
            category="latest_filtering",
            name="Language switch link retains ?kind=feature",
            status="PASS" if zh_has_kind else "FAIL",
            observation=f"ZH switch link href: '{zh_link_href}'",
        )

        # Click language switcher to navigate to Chinese edition
        page.click('.lang-switch a[hreflang="zh-CN"]')
        page.wait_for_timeout(100)
        zh_page_state = page.evaluate("""() => {
            const btn = document.querySelector('#latest-controls button[data-kind="feature"]');
            const enLink = document.querySelector('.lang-switch a[hreflang="en"]');
            return {
                featurePressed: btn && btn.getAttribute('aria-pressed') === 'true',
                btnText: btn ? btn.textContent.trim() : '',
                enLinkHref: enLink ? enLink.getAttribute('href') : '',
                url: window.location.href,
            };
        }""")
        zh_pass = (zh_page_state["featurePressed"] and zh_page_state["btnText"] == "深度解读" and "?kind=feature" in zh_page_state.get("enLinkHref", ""))
        self.add_check(
            check_id="latest_zh_locale_category_retained",
            category="latest_filtering",
            name="Chinese page retains category (?kind=feature) and updates button to 深度解读",
            status="PASS" if zh_pass else "FAIL",
            observation=f"ZH page featurePressed={zh_page_state['featurePressed']}, btnText='{zh_page_state['btnText']}', enLink='{zh_page_state['enLinkHref']}'",
        )

        # 8. Invalid kind defaults to all
        page.goto(self.make_url("/latest/?kind=invalid_category_xyz"), wait_until="networkidle")
        invalid_state = page.evaluate("""() => {
            const allBtn = document.querySelector('#latest-controls button[data-kind="all"]');
            const cards = Array.from(document.querySelectorAll('.article-list .article-card'));
            const visible = cards.filter(c => !c.hidden && window.getComputedStyle(c).display !== 'none');
            return {
                allPressed: allBtn && allBtn.getAttribute('aria-pressed') === 'true',
                totalCards: cards.length,
                visibleCards: visible.length,
            };
        }""")
        invalid_pass = invalid_state["allPressed"] and (invalid_state["visibleCards"] == invalid_state["totalCards"])
        self.add_check(
            check_id="latest_invalid_kind_defaults_all",
            category="latest_filtering",
            name="Invalid ?kind= defaults to 'all'",
            status="PASS" if invalid_pass else "FAIL",
            observation=f"All button pressed={invalid_state['allPressed']}, {invalid_state['visibleCards']}/{invalid_state['totalCards']} visible",
        )

        context.close()

    def run_no_js_checks(self, browser: Browser) -> None:
        context = browser.new_context(java_script_enabled=False, viewport={"width": 1440, "height": 1000})
        page = context.new_page()

        # 1. On /resources/: verify controls hidden, all cards visible
        resources_url = self.make_url("/resources/")
        page.goto(resources_url, wait_until="load")

        no_js_res_eval = page.evaluate("""() => {
            const controls = document.getElementById('resource-controls');
            // Check computed style or hidden attribute or offsetParent
            const controlsVisible = controls ? (controls.offsetParent !== null && !controls.hidden && window.getComputedStyle(controls).display !== 'none') : false;
            const cards = Array.from(document.querySelectorAll('.resource-card'));
            const visibleCards = cards.filter(c => (c.offsetParent !== null) && !c.hidden && window.getComputedStyle(c).display !== 'none');
            return {
                controlsExists: !!controls,
                controlsVisible: controlsVisible,
                totalCards: cards.length,
                visibleCards: visibleCards.length
            };
        }""")

        if not no_js_res_eval["controlsVisible"]:
            self.add_check(
                check_id="no_js_resources_controls_hidden",
                category="no_js",
                name="No-JS: #resource-controls hidden",
                status="PASS",
                observation="Search and filter controls are cleanly hidden without JavaScript",
                details=no_js_res_eval,
            )
        else:
            self.add_check(
                check_id="no_js_resources_controls_hidden",
                category="no_js",
                name="No-JS: #resource-controls hidden",
                status="FAIL",
                observation="#resource-controls is visible without JavaScript (contract requires hidden parent unhidden by JS)",
                details=no_js_res_eval,
            )

        if no_js_res_eval["visibleCards"] > 0 and no_js_res_eval["visibleCards"] == no_js_res_eval["totalCards"]:
            self.add_check(
                check_id="no_js_resources_all_cards_visible",
                category="no_js",
                name="No-JS: All resource cards visible",
                status="PASS",
                observation=f"All {no_js_res_eval['visibleCards']} resource cards visible without JavaScript",
                details=no_js_res_eval,
            )
        else:
            self.add_check(
                check_id="no_js_resources_all_cards_visible",
                category="no_js",
                name="No-JS: All resource cards visible",
                status="FAIL",
                observation=f"Not all cards visible without JS: visible={no_js_res_eval['visibleCards']}, total={no_js_res_eval['totalCards']}",
                details=no_js_res_eval,
            )

        # 1b. On /latest/ and /zh/latest/: verify #latest-controls hidden, all article cards visible
        for latest_route in ("/latest/", "/zh/latest/"):
            latest_route_url = self.make_url(latest_route)
            page.goto(latest_route_url, wait_until="load")
            no_js_latest_eval = page.evaluate("""() => {
                const controls = document.getElementById('latest-controls');
                const controlsVisible = controls ? (controls.offsetParent !== null && !controls.hidden && window.getComputedStyle(controls).display !== 'none') : false;
                const cards = Array.from(document.querySelectorAll('.article-list .article-card'));
                const visibleCards = cards.filter(c => (c.offsetParent !== null) && !c.hidden && window.getComputedStyle(c).display !== 'none');
                return {
                    controlsExists: !!controls,
                    controlsVisible: controlsVisible,
                    totalCards: cards.length,
                    visibleCards: visibleCards.length
                };
            }""")
            is_hidden = not no_js_latest_eval["controlsVisible"]
            self.add_check(
                check_id=f"no_js_latest_controls_hidden_{latest_route.strip('/')}",
                category="no_js",
                name=f"No-JS: #latest-controls hidden on {latest_route}",
                status="PASS" if is_hidden else "FAIL",
                observation=f"#latest-controls is hidden without JS on {latest_route}" if is_hidden else f"#latest-controls visible without JS on {latest_route}",
                details=no_js_latest_eval,
            )
            all_visible = no_js_latest_eval["visibleCards"] > 0 and no_js_latest_eval["visibleCards"] == no_js_latest_eval["totalCards"]
            self.add_check(
                check_id=f"no_js_latest_all_cards_visible_{latest_route.strip('/')}",
                category="no_js",
                name=f"No-JS: All article cards visible on {latest_route}",
                status="PASS" if all_visible else "FAIL",
                observation=f"All {no_js_latest_eval['visibleCards']} article cards visible on {latest_route} without JS" if all_visible else f"Not all cards visible on {latest_route} without JS",
                details=no_js_latest_eval,
            )

        # 2. Verify all contract pages have readable content without JS
        for route in CONTRACT_ROUTES:
            route_url = self.make_url(route)
            try:
                resp = page.goto(route_url, wait_until="load")
                code = resp.status if resp else 0
                expected_codes = (200, 404) if route == "/404.html" else (200,)
                if code not in expected_codes:
                    self.add_check(
                        check_id=f"no_js_page_readable_{route}",
                        category="no_js",
                        name=f"No-JS readability on {route}",
                        status="FAIL",
                        observation=f"HTTP status {code} on {route} without JS",
                    )
                    continue

                page_eval = page.evaluate("""() => {
                    const h1 = document.querySelector('h1');
                    const main = document.querySelector('main#main') || document.querySelector('main');
                    const h1Text = h1 ? h1.innerText.trim() : '';
                    const mainText = main ? main.innerText.trim() : '';
                    return {
                        hasH1: !!h1 && h1Text.length > 0,
                        h1Text: h1Text,
                        mainLength: mainText.length
                    };
                }""")

                if page_eval["hasH1"] and page_eval["mainLength"] >= 50:
                    self.add_check(
                        check_id=f"no_js_page_readable_{route}",
                        category="no_js",
                        name=f"No-JS readability on {route}",
                        status="PASS",
                        observation=f"Page is readable without JS: h1='{page_eval['h1Text']}', main content length={page_eval['mainLength']} chars",
                        details=page_eval,
                    )
                else:
                    self.add_check(
                        check_id=f"no_js_page_readable_{route}",
                        category="no_js",
                        name=f"No-JS readability on {route}",
                        status="FAIL",
                        observation=f"Incomplete content without JS on {route}: hasH1={page_eval['hasH1']}, mainLength={page_eval['mainLength']}",
                        details=page_eval,
                    )
            except Exception as e:
                self.add_check(
                    check_id=f"no_js_page_readable_{route}",
                    category="no_js",
                    name=f"No-JS readability on {route}",
                    status="FAIL",
                    observation=f"Failed loading {route} without JS: {e}",
                )

        context.close()

    def run_screenshots_capture(self, browser: Browser) -> None:
        if not self.screenshots_dir:
            return

        targets = [
            {"id": "home_desktop", "name": "home-desktop.png", "route": "/", "width": 1440, "height": 1000},
            {"id": "home_mobile", "name": "home-mobile.png", "route": "/", "width": 390, "height": 844},
            {"id": "resources_desktop", "name": "resources-desktop.png", "route": "/resources/", "width": 1440, "height": 1000},
            {"id": "resources_mobile", "name": "resources-mobile.png", "route": "/resources/", "width": 390, "height": 844},
            {"id": "guide_desktop", "name": "guide-desktop.png", "route": "/guides/audit-an-agent-action/", "width": 1440, "height": 1000},
            {"id": "guide_mobile", "name": "guide-mobile.png", "route": "/guides/audit-an-agent-action/", "width": 390, "height": 844},
            {"id": "404_desktop", "name": "404-desktop.png", "route": "/404.html", "width": 1440, "height": 1000},
        ]

        context = browser.new_context()
        page = context.new_page()

        for t in targets:
            out_file = os.path.join(self.screenshots_dir, t["name"])
            try:
                page.set_viewport_size({"width": t["width"], "height": t["height"]})
                page.goto(self.make_url(t["route"]), wait_until="networkidle")
                page.screenshot(path=out_file, full_page=True)

                size_bytes = os.path.getsize(out_file) if os.path.exists(out_file) else 0
                if size_bytes > 0:
                    self.screenshots_taken.append({
                        "id": t["id"],
                        "file": out_file,
                        "name": t["name"],
                        "route": t["route"],
                        "viewport": f"{t['width']}x{t['height']}",
                        "size_bytes": size_bytes,
                    })
                    self.add_check(
                        check_id=f"screenshot_{t['id']}",
                        category="screenshots",
                        name=f"Capture {t['name']}",
                        status="PASS",
                        observation=f"Captured {t['name']} ({size_bytes} bytes)",
                        details={"file": out_file, "size_bytes": size_bytes},
                    )
                else:
                    self.add_check(
                        check_id=f"screenshot_{t['id']}",
                        category="screenshots",
                        name=f"Capture {t['name']}",
                        status="FAIL",
                        observation=f"Screenshot {t['name']} was created but has 0 bytes",
                    )
            except Exception as e:
                self.add_check(
                    check_id=f"screenshot_{t['id']}",
                    category="screenshots",
                    name=f"Capture {t['name']}",
                    status="FAIL",
                    observation=f"Failed capturing {t['name']} on {t['route']}: {e}",
                )

        context.close()


def parse_args(args=None):
    parser = argparse.ArgumentParser(description="Audit Commons Browser Acceptance Test Suite")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8765",
        help="Base URL for target server (default: http://127.0.0.1:8765)",
    )
    parser.add_argument(
        "--screenshots",
        dest="screenshots",
        default=None,
        help="Optional directory to save acceptance screenshots",
    )
    parser.add_argument(
        "--headed",
        dest="headless",
        action="store_false",
        default=True,
        help="Run browser in headed mode (default: headless)",
    )
    return parser.parse_args(args)


def main():
    args = parse_args()
    checker = BrowserAcceptanceChecker(
        base_url=args.base_url,
        screenshots_dir=args.screenshots,
        headless=args.headless,
    )
    exit_code = checker.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
