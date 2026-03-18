from __future__ import annotations
from gate_automation.core.interfaces import CaptchaSolver
from gate_automation.infrastructure.captcha.solvers import FallbackCaptchaSolver, ManualCaptchaSolver, MathExpressionParser, OcrMathCaptchaSolver

class CaptchaSolverFactory:

    @staticmethod
    def create(mode: str) -> CaptchaSolver:
        normalized_mode = mode.strip().lower()
        parser = MathExpressionParser()
        if normalized_mode == 'manual':
            return ManualCaptchaSolver()
        if normalized_mode == 'ocr':
            return OcrMathCaptchaSolver(parser=parser)
        if normalized_mode == 'hybrid':
            return FallbackCaptchaSolver(primary=OcrMathCaptchaSolver(parser=parser), secondary=ManualCaptchaSolver())
        raise ValueError('Invalid captcha mode. Use one of: manual, ocr, hybrid')
