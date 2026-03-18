import asyncio
from gate_automation.core.services import GateResultService
from gate_automation.infrastructure.browser.playwright_client import PlaywrightPortalClient
from gate_automation.infrastructure.captcha.factory import CaptchaSolverFactory
from gate_automation.infrastructure.csv_loader import CsvCredentialLoader
from gate_automation.infrastructure.sinks import ConsoleResultSink

class OverrideLoader(CsvCredentialLoader):

    def load_credentials(self):
        return [c for c in super().load_credentials() if c.enrollment_id == 'G229J81']
loader = OverrideLoader('data/Data.csv')
captcha_solver = CaptchaSolverFactory.create('ocr')
portal_client = PlaywrightPortalClient(base_url='https://goaps.iitg.ac.in/login', captcha_solver=captcha_solver, headless=True, timeout_ms=30000, max_captcha_attempts=5)
service = GateResultService(loader, portal_client, [ConsoleResultSink()])
service.run()
