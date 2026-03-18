from __future__ import annotations
import re
from dataclasses import dataclass
from gate_automation.core.interfaces import CaptchaSolver, PortalClient
from gate_automation.core.models import CandidateCredential, CandidateResult

@dataclass(slots=True)
class PlaywrightPortalClient(PortalClient):
    base_url: str
    captcha_solver: CaptchaSolver
    headless: bool = True
    timeout_ms: int = 20000
    max_captcha_attempts: int = 10

    def __post_init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._context = None

    def _ensure_started(self) -> None:
        if self._context is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise RuntimeError('Playwright is not installed. Run: pip install playwright') from error
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context()

    def fetch_candidate_result(self, credential: CandidateCredential) -> CandidateResult:
        self._ensure_started()
        assert self._context is not None
        self._context.clear_cookies()
        page = self._context.new_page()
        
        # Optimization: Block unnecessary heavy network resources
        page.route("**/*", lambda route: route.abort() 
            if route.request.resource_type in ["stylesheet", "font", "media"] 
            else route.continue_()
        )
        
        page.set_default_timeout(self.timeout_ms)
        try:
            for attempt in range(1, self.max_captcha_attempts + 1):
                page.goto(self.base_url, wait_until='domcontentloaded')
                self._fill_login_fields(page, credential)
                captcha_image = self._capture_captcha_image(page)
                try:
                    captcha_answer = self.captcha_solver.solve(captcha_image)
                except Exception as solve_error:
                    print(f'[DEBUG] Captcha internal solve error: {solve_error}. Retrying...')
                    if attempt < self.max_captcha_attempts:
                        self._refresh_captcha(page)
                        continue
                    else:
                        raise solve_error
                self._fill_captcha_answer(page, captcha_answer)
                self._submit_login(page)
                page.wait_for_timeout(2500)
                if self._is_login_success(page):
                    extracted = self._extract_result_data(page)
                    return CandidateResult(enrollment_id=credential.enrollment_id, status='success', message='Login success and result page parsed', extracted=extracted)
                error_message = self._read_login_error(page)
                if attempt < self.max_captcha_attempts:
                    print(f'[DEBUG] Attempt {attempt} failed with: {error_message}. Retrying...')
                    self._refresh_captcha(page)
                    continue
                return CandidateResult(enrollment_id=credential.enrollment_id, status='failed', message=error_message or 'Login failed')
            return CandidateResult(enrollment_id=credential.enrollment_id, status='failed', message='Max captcha attempts reached')
        except Exception as error:
            return CandidateResult(enrollment_id=credential.enrollment_id, status='failed', message=f'Automation error: {error}')
        finally:
            page.close()

    def _fill_login_fields(self, page, credential: CandidateCredential) -> None:
        enrollment_filled = False
        try:
            page.get_by_label(re.compile('Enrollment ID|Email', re.I)).fill(credential.enrollment_id)
            enrollment_filled = True
        except Exception:
            pass
        if not enrollment_filled:
            text_inputs = page.locator("input[type='text'], input[type='email'], input:not([type])")
            if text_inputs.count() == 0:
                raise RuntimeError('Enrollment input not found')
            text_inputs.first.fill(credential.enrollment_id)
        password_input = page.locator("input[type='password']")
        if password_input.count() == 0:
            raise RuntimeError('Password input not found')
        password_input.first.fill(credential.password)

    def _capture_captcha_image(self, page) -> bytes:
        images = page.locator('img')
        image_count = images.count()
        if image_count == 0:
            raise RuntimeError('No image elements found for captcha')
        best_index = -1
        best_area = 0.0
        for index in range(image_count):
            image = images.nth(index)
            box = image.bounding_box()
            if not box:
                continue
            width = box.get('width', 0)
            height = box.get('height', 0)
            y = box.get('y', 0)
            if 50 <= width <= 220 and 18 <= height <= 90 and (y > 200):
                area = width * height
                if area > best_area:
                    best_area = area
                    best_index = index
        if best_index == -1:
            raise RuntimeError('Captcha image not detected')
        return images.nth(best_index).screenshot()

    def _fill_captcha_answer(self, page, answer: str) -> None:
        text_inputs = page.locator("input[type='text'], input[type='email'], input:not([type])")
        count = text_inputs.count()
        if count < 2:
            raise RuntimeError('Captcha answer input not found')
        text_inputs.nth(count - 1).fill(str(answer).strip())

    def _submit_login(self, page) -> None:
        login_button = page.get_by_role('button', name=re.compile('login', re.I))
        if login_button.count() > 0:
            login_button.first.click()
            return
        fallback_button = page.locator("button:has-text('LOGIN'), input[type='submit']")
        if fallback_button.count() == 0:
            raise RuntimeError('Login button not found')
        fallback_button.first.click()

    @staticmethod
    def _is_login_success(page) -> bool:
        if '/login' not in page.url.lower():
            return True
        body_text = page.inner_text('body').lower()
        success_tokens = ['logout', 'dashboard', 'result', 'candidate', 'score']
        return any((token in body_text for token in success_tokens))

    @staticmethod
    def _read_login_error(page) -> str:
        priority_selectors = ['.invalid-feedback', '.text-danger', '.error', '.alert-danger', '.help-block']
        messages: list[str] = []
        for selector in priority_selectors:
            locator = page.locator(selector)
            count = locator.count()
            for index in range(count):
                text = locator.nth(index).inner_text().strip()
                if text:
                    messages.append(text)
        if messages:
            return ' | '.join(dict.fromkeys(messages))
        body = page.inner_text('body')
        for pattern in ['invalid[^\\n]{0,80}', 'captcha[^\\n]{0,120}', 'incorrect[^\\n]{0,80}', 'enter a valid[^\\n]{0,80}']:
            found = re.search(pattern, body, flags=re.IGNORECASE)
            if found:
                return found.group(0).strip()
        return 'Login attempt failed'

    @staticmethod
    def _is_captcha_error(error_message: str) -> bool:
        lowered = error_message.lower()
        return 'captcha' in lowered or 'arithmetic' in lowered

    @staticmethod
    def _refresh_captcha(page) -> None:
        selectors = ["[aria-label*='refresh' i]", "[title*='refresh' i]", '.fa-refresh', '.fa-repeat', '.bi-arrow-repeat', 'text=↻']
        for selector in selectors:
            locator = page.locator(selector)
            if locator.count() > 0:
                locator.first.click()
                page.wait_for_timeout(300)
                return

    @staticmethod
    def _extract_result_data(page) -> dict[str, str]:
        body_text = page.inner_text('body')
        extracted: dict[str, str] = {'final_url': page.url}
        patterns = {'name': '(?:Candidate Name|Name)\\s*[:\\-]\\s*([^\\n]+)', 'registration': '(?:Enrollment ID|Registration No\\.?|Application No\\.?)\\s*[:\\-]\\s*([^\\n]+)', 'marks': '(?:Marks|Score)\\s*[:\\-]\\s*([^\\n]+)', 'rank': '(?:AIR|Rank)\\s*[:\\-]\\s*([^\\n]+)', 'gate_score': '(?:GATE Score)\\s*[:\\-]\\s*([^\\n]+)'}
        for key, pattern in patterns.items():
            match = re.search(pattern, body_text, flags=re.IGNORECASE)
            if match:
                extracted[key] = match.group(1).strip()
        if len(extracted) == 1:
            first_lines = [line.strip() for line in body_text.splitlines() if line.strip()][:10]
            extracted['snapshot'] = ' | '.join(first_lines)
        return extracted

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
