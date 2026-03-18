from __future__ import annotations
import argparse
from gate_automation.core.services import GateResultService
from gate_automation.infrastructure.browser.playwright_client import PlaywrightPortalClient
from gate_automation.infrastructure.captcha.factory import CaptchaSolverFactory
from gate_automation.infrastructure.csv_loader import CsvCredentialLoader
from gate_automation.infrastructure.sinks import ConsoleResultSink, CsvResultSink

def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Automate GATE portal login and fetch candidate results')
    parser.add_argument('--base-url', default='https://goaps.iitg.ac.in/login', help='GATE portal login URL')
    parser.add_argument('--credentials-csv', default='data/credentials.csv', help='Path to CSV with headers: enrollment_id,password')
    parser.add_argument('--output-csv', default='output/results.csv', help='Path where extracted results are appended')
    parser.add_argument('--captcha-mode', default='hybrid', choices=['manual', 'ocr', 'hybrid'], help='Captcha solving mode')
    parser.add_argument('--headful', action='store_true', help='Run browser in visible mode (useful for debugging)')
    parser.add_argument('--timeout-ms', type=int, default=20000, help='Playwright timeout in milliseconds')
    parser.add_argument('--max-captcha-attempts', type=int, default=10, help='Retry attempts for captcha/login errors')
    return parser

def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()
    loader = CsvCredentialLoader(args.credentials_csv)
    captcha_solver = CaptchaSolverFactory.create(args.captcha_mode)
    portal_client = PlaywrightPortalClient(base_url=args.base_url, captcha_solver=captcha_solver, headless=not args.headful, timeout_ms=args.timeout_ms, max_captcha_attempts=args.max_captcha_attempts)
    sinks = [ConsoleResultSink(), CsvResultSink(args.output_csv)]
    service = GateResultService(credential_loader=loader, portal_client=portal_client, result_sinks=sinks)
    service.run()
if __name__ == '__main__':
    main()
