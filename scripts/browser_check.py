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

                    # 4. No-JS verification
                    self.run_no_js_checks(browser)

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
            if route == "/404.html":
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

            # Internal navigation check on header nav
            nav_links = page.locator("nav.site-nav a, header nav a")
            link_hrefs = [nav_links.nth(i).get_attribute("href") or "" for i in range(nav_links.count())]
            expected_destinations = ["latest", "features", "learn", "resources", "about"]
            missing_links = []
            for dest in expected_destinations:
                matched = any(dest in href for href in link_hrefs)
                if not matched:
                    missing_links.append(dest)

            if not missing_links:
                self.add_check(
                    check_id=f"nav_links_{route}",
                    category="navigation",
                    name=f"Primary nav links on {route}",
                    status="PASS",
                    observation=f"Found internal navigation links: {link_hrefs}",
                    details={"hrefs": link_hrefs},
                )
            else:
                self.add_check(
                    check_id=f"nav_links_{route}",
                    category="navigation",
                    name=f"Primary nav links on {route}",
                    status="FAIL",
                    observation=f"Nav missing required destination links {missing_links} in {link_hrefs}",
                    details={"missing": missing_links, "hrefs": link_hrefs},
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
        page.wait_for_timeout(100)

        reset_eval = page.evaluate("""(totalExpected) => {
            const cards = Array.from(document.querySelectorAll('.resource-card'));
            const visibleCards = cards.filter(c => (c.offsetParent !== null) && !c.hidden && window.getComputedStyle(c).display !== 'none');
            const noResultsEl = document.getElementById('no-results');
            const noResultsVisible = noResultsEl && (noResultsEl.offsetParent !== null) && !noResultsEl.hidden && window.getComputedStyle(noResultsEl).display !== 'none';
            const allBtn = document.querySelector("button[data-filter='All']");
            const allPressed = allBtn ? allBtn.getAttribute('aria-pressed') : null;
            const countEl = document.getElementById('resource-count');
            const countText = countEl ? countEl.innerText.trim() : '';
            return {
                visibleCount: visibleCards.length,
                noResultsVisible: !!noResultsVisible,
                allPressed: allPressed,
                countText: countText
            };
        }""", total_cards)

        if (
            reset_eval["visibleCount"] == total_cards
            and not reset_eval["noResultsVisible"]
            and reset_eval["allPressed"] == "true"
        ):
            self.add_check(
                check_id="resources_reset_all",
                category="resources",
                name="Reset 'All' and clearing search",
                status="PASS",
                observation=f"Reset restored all {total_cards} cards, #no-results hidden, 'All' aria-pressed='true'",
                details=reset_eval,
            )
        else:
            self.add_check(
                check_id="resources_reset_all",
                category="resources",
                name="Reset 'All' and clearing search",
                status="FAIL",
                observation=f"Reset failed: visibleCount={reset_eval['visibleCount']}/{total_cards}, allPressed={reset_eval['allPressed']}, noResultsVisible={reset_eval['noResultsVisible']}",
                details=reset_eval,
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
