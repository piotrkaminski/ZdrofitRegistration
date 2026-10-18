import os
import sys
import time
import json
import re
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

from .matcher import match_activity, normalize_text
from .date_parser import parse_target_date, parse_weekday

DEFAULT_CLUB = "zerniki-wroclawskie-zasluczanska"
CHROME_MAC_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

class ZdrofitClass:
    def __init__(self, data: Dict[str, Any]):
        self.id = data.get("id", "")
        self.url = data.get("url", "")
        self.day = data.get("day", "")
        self.time = data.get("time", "")
        self.activity_slug = data.get("activity_slug", "")
        self.activity_title = data.get("activity_title", "")
        self.trainer = data.get("trainer", "")
        self.spots = data.get("spots", "")
        self.is_full = data.get("is_full", False)
        self.is_registered = data.get("is_registered", False)
        self.is_early = data.get("is_early", False)
        self.can_book = data.get("can_book", False)
        self.status_text = data.get("status_text", "")

    @property
    def start_datetime(self) -> Optional[datetime.datetime]:
        try:
            return datetime.datetime.strptime(f"{self.day} {self.time}", "%Y-%m-%d %H:%M")
        except Exception:
            return None

    @property
    def registration_opens_at(self) -> Optional[datetime.datetime]:
        dt = self.start_datetime
        if dt:
            # Registration opens exactly 48 hours before class start
            return dt - datetime.timedelta(hours=48)
        return None

    @property
    def is_in_48h_range(self) -> bool:
        """Check if class is currently within the 48-hour registration window."""
        dt = self.start_datetime
        if not dt:
            return False
        now = datetime.datetime.now()
        opens_at = dt - datetime.timedelta(hours=48)
        return opens_at <= now < dt

    @property
    def is_past(self) -> bool:
        """Check if class has already started or ended."""
        dt = self.start_datetime
        if not dt:
            return False
        return datetime.datetime.now() >= dt

    def __repr__(self):
        return f"<ZdrofitClass {self.day} {self.time} '{self.activity_title}' ({self.trainer}) [{self.status_text}] id={self.id}>"


class ZdrofitClient:
    def __init__(
        self,
        club_slug: str = DEFAULT_CLUB,
        session_file: str = "session.json",
        user_data_dir: str = "chrome_data",
        headless: bool = True
    ):
        self.club_slug = club_slug
        self.session_file = Path(session_file).resolve()
        self.user_data_dir = Path(user_data_dir).resolve()
        self.headless = headless
        self.base_url = f"https://zdrofit.pl/kluby-fitness/{self.club_slug}/grafik-zajec"

        # Check local Google Chrome executable
        self.executable_path = CHROME_MAC_PATH if os.path.exists(CHROME_MAC_PATH) else None

    def _get_context_options(self) -> Dict[str, Any]:
        options = {
            "viewport": {"width": 1280, "height": 800},
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
        }
        if self.session_file.exists():
            try:
                options["storage_state"] = str(self.session_file)
            except Exception as e:
                print(f"[!] Warning: Could not load {self.session_file}: {e}")
        return options

    def login_interactive(self):
        """
        Launch a headed browser for the user to log in manually.
        Saves session cookies to session.json upon successful login.
        """
        print("\n=======================================================")
        print("  ZDROFIT INTERACTIVE LOGIN")
        print("=======================================================")
        print("Opening Google Chrome window...")
        print("1. Log in to your Zdrofit account in the browser.")
        print("2. Solve any reCAPTCHA if prompted.")
        print("3. Once logged in, the script will automatically detect it and save your session.")
        print("=======================================================\n")

        with sync_playwright() as p:
            browser_args = ["--disable-blink-features=AutomationControlled"]
            browser = p.chromium.launch(
                headless=False,
                executable_path=self.executable_path,
                args=browser_args
            )
            context = browser.new_context(**self._get_context_options())
            page = context.new_page()

            page.goto("https://zdrofit.pl/#logowanie", wait_until="domcontentloaded")

            # Polling loop waiting for user to log in
            logged_in = False
            for _ in range(120): # wait up to 4 minutes
                time.sleep(2)
                try:
                    # Check if user status in dataLayer is 'logged' or moje-konto button exists
                    is_logged = page.evaluate("""() => {
                        if (window.dataLayer) {
                            for (let dl of window.dataLayer) {
                                if (dl && dl.page_core && dl.page_core.user_status === 'logged') return true;
                            }
                        }
                        const myAccount = document.querySelector('a[href*="/moje-konto"]');
                        if (myAccount && myAccount.innerText.includes('Moje konto')) return true;
                        return false;
                    }""")
                    if is_logged:
                        logged_in = True
                        break
                except Exception:
                    pass

            if logged_in:
                print("\n[+] Login detected successfully!")
                context.storage_state(path=str(self.session_file))
                print(f"[+] Session saved to: {self.session_file}")
            else:
                print("\n[-] Login timed out or was not completed. Session not saved.")

            browser.close()

    def check_login(self, page: Page) -> bool:
        """Check whether the active page context is logged in."""
        try:
            return page.evaluate("""() => {
                if (window.dataLayer) {
                    for (let dl of window.dataLayer) {
                        if (dl && dl.page_core && dl.page_core.user_status === 'logged') return true;
                    }
                }
                const myAccount = document.querySelector('a[href*="/moje-konto"]');
                return !!(myAccount && myAccount.innerText.includes('Moje konto'));
            }""")
        except Exception:
            return False

    def fetch_schedule(self, target_day: Optional[str] = None) -> List[ZdrofitClass]:
        """
        Fetch and parse the full schedule from Zdrofit for the club.
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                executable_path=self.executable_path,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(**self._get_context_options())
            page = context.new_page()

            url = self.base_url
            if target_day:
                url = f"{self.base_url}?day={target_day}"

            page.goto(url, wait_until="networkidle", timeout=30000)
            content = page.content()
            browser.close()

        return self._parse_schedule_html(content)

    def _parse_schedule_html(self, html: str) -> List[ZdrofitClass]:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select("li.club-schedule-item")
        results = []

        for item in items:
            item_id = item.get("data-id", "")
            item_url = item.get("data-url", "")
            day = item.get("data-day", "")
            act_slug = item.get("data-activity", "")
            classes = item.get("class", [])

            time_tag = item.select_one("time")
            class_time = time_tag.get_text(strip=True) if time_tag else ""

            act_tag = item.select_one("a.activity")
            act_title = act_tag.get_text(strip=True) if act_tag else act_slug

            trainer_tag = item.select_one(".trainer")
            trainer = trainer_tag.get_text(strip=True) if trainer_tag else ""

            users_tag = item.select_one(".users")
            spots = users_tag.get_text(strip=True) if users_tag else ""

            reg_div = item.select_one(".registration")
            reg_text = reg_div.get_text(strip=True) if reg_div else ""

            is_full = "data-full" in item.attrs and item["data-full"] == "true"
            is_early = "item-registration-early" in classes or "Za wcześnie" in reg_text
            is_registered = "item-member-registered" in classes or "Zapisano" in reg_text
            can_book = "Zapisz się" in reg_text

            results.append(ZdrofitClass({
                "id": item_id,
                "url": item_url,
                "day": day,
                "time": class_time,
                "activity_slug": act_slug,
                "activity_title": act_title,
                "trainer": trainer,
                "spots": spots,
                "is_full": is_full,
                "is_registered": is_registered,
                "is_early": is_early,
                "can_book": can_book,
                "status_text": reg_text or ("Zapisz się" if can_book else "Dostępne")
            }))

        return results

    def find_class(
        self,
        date_str: str,
        time_str: str,
        exercise_query: str,
        schedule: Optional[List[ZdrofitClass]] = None
    ) -> Optional[ZdrofitClass]:
        """
        Find class matching target date, time, and exercise query.
        """
        target_date = parse_target_date(date_str)
        target_day_str = target_date.strftime("%Y-%m-%d")

        # Normalize target time (e.g., '8:30' -> '08:30')
        t_parts = time_str.strip().split(":")
        normalized_time = f"{int(t_parts[0]):02d}:{int(t_parts[1]):02d}"

        if schedule is None:
            schedule = self.fetch_schedule(target_day=target_day_str)

        matched_classes = []
        for cls in schedule:
            if cls.day != target_day_str:
                continue

            # Compare time
            if cls.time != normalized_time:
                continue

            is_match, score = match_activity(exercise_query, cls.activity_slug, cls.activity_title)
            if is_match:
                matched_classes.append((score, cls))

        if not matched_classes:
            return None

        # Sort by highest match confidence
        matched_classes.sort(key=lambda x: x[0], reverse=True)
        return matched_classes[0][1]

    def register_now(self, target_class: ZdrofitClass) -> Dict[str, Any]:
        """
        Perform high-speed registration for target_class using in-page fetch + fallback.
        """
        print(f"\n[>] Attempting registration for class ID {target_class.id} ({target_class.activity_title} on {target_class.day} {target_class.time})...")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                executable_path=self.executable_path,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(**self._get_context_options())
            page = context.new_page()

            # Navigate to the schedule page
            page.goto(f"{self.base_url}?day={target_class.day}", wait_until="networkidle", timeout=30000)

            # Check if user is logged in
            if not self.check_login(page):
                browser.close()
                return {
                    "success": False,
                    "error": "Not logged in! Run with --login first to save your session."
                }

            # High-speed registration via in-page fetch
            class_url = target_class.url or f"/kluby-fitness/{self.club_slug}/grafik-zajec/{target_class.id}"

            reg_result = page.evaluate("""async ({ classId, classUrl }) => {
                // Step 1: Fetch class modal HTML to extract CSRF token
                const getResp = await fetch(classUrl, {
                    headers: { 'Accept': '*/*', 'X-Requested-With': 'XMLHttpRequest' }
                });
                const getHtml = await getResp.text();

                // Check for CSRF token
                const tokenMatch = getHtml.match(/name="schedule_register_form\\[_token\\]"\\s+value="([^"]+)"/i);
                if (!tokenMatch) {
                    // Check if already registered
                    if (getHtml.includes('Wypisz się')) {
                        return { success: true, message: 'Already registered (Wypisz się form present).' };
                    }
                    if (getHtml.includes('Za wcześnie')) {
                        return { success: false, early: true, message: 'Registration not open yet (Za wcześnie).' };
                    }
                    return { success: false, htmlPreview: getHtml.slice(0, 400), message: 'CSRF token not found in class response.' };
                }

                const csrfToken = tokenMatch[1];

                // Step 2: POST form data
                const body = new URLSearchParams();
                body.append('schedule_register_form[id]', classId);
                body.append('schedule_register_form[_redirect]', '');
                body.append('schedule_register_form[_token]', csrfToken);

                const postResp = await fetch(classUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Accept': '*/*'
                    },
                    body: body.toString()
                });

                const postHtml = await postResp.text();

                if (postHtml.includes('Zapisano') || postHtml.includes('tick')) {
                    return { success: true, message: 'Successfully registered (Zapisano)!' };
                }
                if (postHtml.includes('rezerwowa') || postHtml.includes('standby')) {
                    return { success: true, standby: true, message: 'Added to standby/reserve list (Lista rezerwowa).' };
                }

                return { success: false, htmlPreview: postHtml.slice(0, 400), message: 'Registration response did not confirm registration.' };
            }""", {"classId": target_class.id, "classUrl": class_url})

            browser.close()
            return reg_result

    def wait_and_register(
        self,
        date_str: str,
        time_str: str,
        exercise_query: str,
        early_connect_seconds: int = 15
    ):
        """
        Wait until registration opens (48 hours before class start) and execute registration.
        """
        print("\n=======================================================")
        print("  ZDROFIT AUTOMATIC CLASS REGISTRATION")
        print("=======================================================")
        print(f"Club:     {self.club_slug}")
        print(f"Target:   {exercise_query} on {date_str} at {time_str}")
        print("=======================================================\n")

        # Step 1: Find target class in schedule
        target_class = self.find_class(date_str, time_str, exercise_query)
        if not target_class:
            print(f"[-] Could not find class matching '{exercise_query}' on {date_str} at {time_str}.")
            print("    Check available classes with: python register.py --list")
            return False

        print(f"[+] Found class:")
        print(f"    ID:       {target_class.id}")
        print(f"    Activity: {target_class.activity_title}")
        print(f"    Trainer:  {target_class.trainer}")
        print(f"    Date:     {target_class.day} {target_class.time}")
        print(f"    Status:   {target_class.status_text}")

        if target_class.is_registered:
            print("[+] You are ALREADY REGISTERED for this class!")
            return True

        opens_at = target_class.registration_opens_at
        now = datetime.datetime.now()

        if opens_at is None:
            print("[-] Unable to determine registration opening time.")
            return False

        print(f"    Registration opens: {opens_at.strftime('%Y-%m-%d %H:%M:%S')} (48 hours before class)")

        # If registration is already open
        if now >= opens_at:
            print("[+] Registration is already open! Registering immediately...")
            res = self.register_now(target_class)
            print(f"Result: {res}")
            return res.get("success", False)

        # Wait until registration opens
        time_to_wait = (opens_at - now).total_seconds()
        print(f"\n[*] Waiting for registration to open in {datetime.timedelta(seconds=int(time_to_wait))}...")

        # Sleep until early_connect_seconds before opening
        if time_to_wait > early_connect_seconds:
            sleep_duration = time_to_wait - early_connect_seconds
            print(f"[*] Sleeping until {early_connect_seconds}s before opening ({opens_at - datetime.timedelta(seconds=early_connect_seconds)})...")
            time.sleep(sleep_duration)

        print("\n[*] Initializing browser session and preparing high-precision snipe...")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                executable_path=self.executable_path,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(**self._get_context_options())
            page = context.new_page()

            page.goto(f"{self.base_url}?day={target_class.day}", wait_until="networkidle", timeout=30000)

            if not self.check_login(page):
                browser.close()
                print("[-] Error: Not logged in. Please run 'python register.py --login' first.")
                return False

            class_url = target_class.url or f"/kluby-fitness/{self.club_slug}/grafik-zajec/{target_class.id}"

            # High precision countdown to opens_at
            while True:
                diff = (opens_at - datetime.datetime.now()).total_seconds()
                if diff <= 0.05: # reached opening time!
                    break
                if diff > 1.0:
                    time.sleep(0.5)
                else:
                    time.sleep(0.02)

            print(f"[!] {datetime.datetime.now().strftime('%H:%M:%S.%f')}: Registration opened! Submitting registration...")

            # Retry loop for 15 seconds in case server clock is slightly off
            start_snipe = time.time()
            success = False

            while time.time() - start_snipe < 15:
                reg_result = page.evaluate("""async ({ classId, classUrl }) => {
                    const getResp = await fetch(classUrl, {
                        headers: { 'Accept': '*/*', 'X-Requested-With': 'XMLHttpRequest' }
                    });
                    const getHtml = await getResp.text();

                    const tokenMatch = getHtml.match(/name="schedule_register_form\\[_token\\]"\\s+value="([^"]+)"/i);
                    if (!tokenMatch) {
                        if (getHtml.includes('Wypisz się')) {
                            return { success: true, message: 'Already registered.' };
                        }
                        if (getHtml.includes('Za wcześnie')) {
                            return { success: false, early: true, message: 'Server says: Za wcześnie.' };
                        }
                        return { success: false, message: 'Token not found.' };
                    }

                    const csrfToken = tokenMatch[1];
                    const body = new URLSearchParams();
                    body.append('schedule_register_form[id]', classId);
                    body.append('schedule_register_form[_redirect]', '');
                    body.append('schedule_register_form[_token]', csrfToken);

                    const postResp = await fetch(classUrl, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Accept': '*/*' },
                        body: body.toString()
                    });

                    const postHtml = await postResp.text();
                    if (postHtml.includes('Zapisano') || postHtml.includes('tick')) {
                        return { success: true, message: 'Zapisano!' };
                    }
                    if (postHtml.includes('rezerwowa') || postHtml.includes('standby')) {
                        return { success: true, standby: true, message: 'Lista rezerwowa!' };
                    }
                    return { success: false, message: 'Registration response failed.' };
                }""", {"classId": target_class.id, "classUrl": class_url})

                if reg_result.get("success"):
                    print(f"\n[+] SUCCESS at {datetime.datetime.now().strftime('%H:%M:%S.%f')}! {reg_result.get('message')}")
                    success = True
                    break
                elif reg_result.get("early"):
                    print(f"[*] Server reported early at {datetime.datetime.now().strftime('%H:%M:%S.%f')}. Retrying...")
                    time.sleep(0.3)
                else:
                    print(f"[-] Attempt failed: {reg_result.get('message')}. Retrying...")
                    time.sleep(0.5)

            browser.close()
            return success

    def register_classes_batch(self, target_classes: List[ZdrofitClass]) -> Dict[str, Dict[str, Any]]:
        """
        Register for multiple classes in a single browser session.
        Returns a dict mapping class ID to result dict.
        """
        if not target_classes:
            return {}

        results = {}
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                executable_path=self.executable_path,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(**self._get_context_options())
            page = context.new_page()

            # Navigate to the first class's day to ensure cookies and WAF pass
            first_day = target_classes[0].day
            page.goto(f"{self.base_url}?day={first_day}", wait_until="networkidle", timeout=30000)

            if not self.check_login(page):
                browser.close()
                for c in target_classes:
                    results[c.id] = {
                        "success": False,
                        "error": "Not logged in! Run with --login first to save your session."
                    }
                return results

            for target_class in target_classes:
                class_url = target_class.url or f"/kluby-fitness/{self.club_slug}/grafik-zajec/{target_class.id}"
                reg_result = page.evaluate("""async ({ classId, classUrl }) => {
                    const getResp = await fetch(classUrl, {
                        headers: { 'Accept': '*/*', 'X-Requested-With': 'XMLHttpRequest' }
                    });
                    const getHtml = await getResp.text();

                    const tokenMatch = getHtml.match(/name="schedule_register_form\\[_token\\]"\\s+value="([^"]+)"/i);
                    if (!tokenMatch) {
                        if (getHtml.includes('Wypisz się')) {
                            return { success: true, message: 'Already registered.' };
                        }
                        if (getHtml.includes('Za wcześnie')) {
                            return { success: false, early: true, message: 'Registration not open yet (Za wcześnie).' };
                        }
                        return { success: false, htmlPreview: getHtml.slice(0, 400), message: 'CSRF token not found in class response.' };
                    }

                    const csrfToken = tokenMatch[1];
                    const body = new URLSearchParams();
                    body.append('schedule_register_form[id]', classId);
                    body.append('schedule_register_form[_redirect]', '');
                    body.append('schedule_register_form[_token]', csrfToken);

                    const postResp = await fetch(classUrl, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Accept': '*/*' },
                        body: body.toString()
                    });

                    const postHtml = await postResp.text();
                    if (postHtml.includes('Zapisano') || postHtml.includes('tick')) {
                        return { success: true, message: 'Zapisano!' };
                    }
                    if (postHtml.includes('rezerwowa') || postHtml.includes('standby')) {
                        return { success: true, standby: true, message: 'Lista rezerwowa!' };
                    }
                    return { success: false, htmlPreview: postHtml.slice(0, 400), message: 'Registration response failed.' };
                }""", {"classId": target_class.id, "classUrl": class_url})

                results[target_class.id] = reg_result

            browser.close()
        return results

    def sync_configured_classes(
        self,
        config_path: str = "classes.json",
        dry_run: bool = False,
        wait_next: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Scan all configured classes and register for any that are in the 48-hour window.
        """
        config_file = Path(config_path)
        if not config_file.exists():
            print(f"[-] Configuration file not found: {config_path}")
            return []

        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)

        top_club = config.get("club", self.club_slug)
        rules = config.get("classes", [])

        active_rules = [r for r in rules if r.get("enabled", True)]
        if not active_rules:
            print("[*] No active class rules defined in config.")
            return []

        print("\n=======================================================")
        print("  ZDROFIT AUTOMATIC CLASS SYNC")
        print("=======================================================")
        print(f"Config:   {config_path}")
        print(f"Club:     {top_club}")
        print(f"Rules:    {len(active_rules)} active rules")
        print("=======================================================\n")

        # Group rules by club
        club_rules: Dict[str, List[Dict[str, Any]]] = {}
        for r in active_rules:
            c_club = r.get("club", top_club)
            club_rules.setdefault(c_club, []).append(r)

        now = datetime.datetime.now()
        evaluation_results: List[Dict[str, Any]] = []
        classes_to_register: List[tuple[Any, ZdrofitClass, Dict[str, Any]]] = []

        for c_club, c_rules in club_rules.items():
            print(f"[*] Fetching schedule for club: {c_club}...")
            fetch_client = self if c_club == self.club_slug else ZdrofitClient(
                club_slug=c_club,
                session_file=str(self.session_file),
                user_data_dir=str(self.user_data_dir),
                headless=self.headless
            )
            schedule = fetch_client.fetch_schedule()

            for rule in c_rules:
                r_name = rule.get("name") or rule.get("exercise", "Unknown")
                r_exercise = rule.get("exercise", "")
                r_time = rule.get("time", "")
                r_weekday = rule.get("weekday")
                r_date = rule.get("date")

                norm_time = None
                if r_time:
                    parts = r_time.strip().split(":")
                    norm_time = f"{int(parts[0]):02d}:{int(parts[1]):02d}"

                target_wd = parse_weekday(r_weekday) if r_weekday is not None else None
                target_day_str = parse_target_date(r_date).strftime("%Y-%m-%d") if r_date else None

                matched = []
                for c in schedule:
                    if norm_time and c.time != norm_time:
                        continue
                    if target_wd is not None and (c.start_datetime is None or c.start_datetime.weekday() != target_wd):
                        continue
                    if target_day_str is not None and c.day != target_day_str:
                        continue

                    is_match, score = match_activity(r_exercise, c.activity_slug, c.activity_title)
                    if is_match:
                        matched.append((score, c))

                if not matched:
                    evaluation_results.append({
                        "rule": rule,
                        "class": None,
                        "status": "NOT_FOUND",
                        "details": f"No class matching '{r_exercise}' at {r_time} in current schedule"
                    })
                    continue

                matched_classes = [m[1] for m in sorted(matched, key=lambda x: x[1].start_datetime or datetime.datetime.max)]

                for c in matched_classes:
                    if c.is_past:
                        continue  # ignore past occurrences

                    opens_at = c.registration_opens_at
                    in_range = c.is_in_48h_range or c.can_book

                    if c.is_registered:
                        st = "ALREADY_REGISTERED"
                        details = "Already registered (Zapisano)"
                    elif in_range:
                        st = "IN_RANGE"
                        details = "In 48h range - ready to register"
                        classes_to_register.append((fetch_client, c, rule))
                    else:
                        st = "TOO_EARLY"
                        diff = opens_at - now if opens_at else None
                        diff_str = str(diff).split(".")[0] if diff else ""
                        opens_str = opens_at.strftime("%Y-%m-%d %H:%M") if opens_at else ""
                        details = f"Opens in {diff_str} ({opens_str})"

                    evaluation_results.append({
                        "rule": rule,
                        "class": c,
                        "status": st,
                        "details": details
                    })

        # Process registrations for classes in range
        if classes_to_register:
            print(f"\n[>] Found {len(classes_to_register)} class(es) in 48-hour range to register!")
            if dry_run:
                print("[!] Dry-run enabled: skipping actual registration.")
                for _, c, r in classes_to_register:
                    for ev in evaluation_results:
                        if ev["class"] and ev["class"].id == c.id:
                            ev["details"] = "[Dry-run] Would be registered now"
            else:
                by_client: Dict[Any, List[ZdrofitClass]] = {}
                for f_client, c, r in classes_to_register:
                    by_client.setdefault(f_client, []).append(c)

                for f_client, c_list in by_client.items():
                    print(f"[*] Registering {len(c_list)} class(es) in club '{f_client.club_slug}'...")
                    batch_res = f_client.register_classes_batch(c_list)
                    for c in c_list:
                        res = batch_res.get(c.id, {})
                        for ev in evaluation_results:
                            if ev["class"] and ev["class"].id == c.id:
                                if res.get("success"):
                                    ev["status"] = "REGISTERED"
                                    ev["details"] = res.get("message", "Zapisano!")
                                else:
                                    ev["status"] = "FAILED"
                                    ev["details"] = res.get("message", res.get("error", "Failed"))

        # Display Summary Table
        print("\n" + "=" * 90)
        print("  SYNC RESULTS SUMMARY")
        print("=" * 90)
        print(f"{'RULE NAME':<22} | {'EXERCISE':<16} | {'DATE & TIME':<16} | {'STATUS':<15} | {'DETAILS'}")
        print("-" * 90)

        for ev in evaluation_results:
            r = ev["rule"]
            r_name = (r.get("name") or r.get("exercise", ""))[:22]
            c = ev["class"]
            ex = (c.activity_title if c else r.get("exercise", ""))[:16]
            dt_str = f"{c.day} {c.time}" if c else f"{r.get('weekday', '')} {r.get('time', '')}"
            status = ev["status"]
            details = ev["details"]

            status_display = {
                "REGISTERED": "✅ ZAPISANO",
                "ALREADY_REGISTERED": "🎯 ZAPISANO JUŻ",
                "IN_RANGE": "⏳ W ZAKRESIE",
                "TOO_EARLY": "🕒 ZA WCZEŚNIE",
                "NOT_FOUND": "❌ BRAK W GRAFIKU",
                "FAILED": "⚠️ BŁĄD"
            }.get(status, status)

            print(f"{r_name:<22} | {ex:<16} | {dt_str:<16} | {status_display:<15} | {details}")
        print("=" * 90 + "\n")

        # If wait_next is requested OR if a class opens imminently (within 5 minutes):
        too_early = [ev for ev in evaluation_results if ev["status"] == "TOO_EARLY" and ev["class"]]
        if too_early:
            too_early.sort(key=lambda x: x["class"].registration_opens_at or datetime.datetime.max)
            next_class_ev = too_early[0]
            next_c = next_class_ev["class"]
            time_until_open = (next_c.registration_opens_at - datetime.datetime.now()).total_seconds()

            # Trigger wait if explicitly requested (--wait) OR if opening is within 5 minutes (300s)
            should_wait = wait_next or (0 < time_until_open <= 300 and not dry_run)

            if should_wait:
                if not wait_next:
                    print(f"[!] Zapisy na najbliższe zajęcia ({next_c.activity_title}) ruszają za mniej niż 5 minut ({int(time_until_open)}s)!")
                    print(f"[*] Automatycznie przełączam w tryb oczekiwania do godziny {next_c.registration_opens_at.strftime('%H:%M:%S')}...\n")
                else:
                    print(f"[+] Najbliższe otwarcie zapisów: {next_c.activity_title} ({next_c.day} {next_c.time}) -> {next_c.registration_opens_at.strftime('%Y-%m-%d %H:%M:%S')}\n")

                self.wait_and_register(
                    date_str=next_c.day,
                    time_str=next_c.time,
                    exercise_query=next_c.activity_title
                )
            elif not wait_next:
                print("💡 Wskazówka:")
                print(f"   Najbliższe zapisy ({next_c.activity_title}) ruszają: {next_c.registration_opens_at.strftime('%Y-%m-%d %H:%M:%S')}.")
                print("   Aby skrypt czekał w tle i zapisał Cię dokładnie w momencie startu, dodaj flagę --wait:")
                print("   .venv/bin/python3 register.py --sync --wait\n")

        return evaluation_results
