from __future__ import annotations
import ast
import operator
import re
from dataclasses import dataclass
from gate_automation.core.interfaces import CaptchaSolver

class MathExpressionParser:
    _allowed_binary_operators = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv}

    def parse(self, raw_text: str) -> str:
        cleaned = self._normalize(raw_text)
        if not cleaned:
            raise ValueError('No expression detected')
        if not re.fullmatch('^\\d+[\\+\\-\\*/]\\d+$', cleaned):
            raise ValueError(f"'{cleaned}' is not a valid math strict equation structure")
        try:
            parsed_ast = ast.parse(cleaned, mode='eval')
            result = self._evaluate(parsed_ast.body)
            if int(result) == result:
                return str(int(result))
            return str(result)
        except SyntaxError:
            raise ValueError(f'Invalid math expression syntax: {cleaned}')

    @staticmethod
    def _normalize(raw_text: str) -> str:
        text = raw_text.strip().replace('=', '')
        text = text.replace('x', '*').replace('X', '*')
        text = text.replace('÷', '/')
        text = text.replace('t', '+')
        text = re.sub('[^0-9+\\-*/().]', '', text)
        return text

    def _evaluate(self, node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = self._evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            left = self._evaluate(node.left)
            right = self._evaluate(node.right)
            operator_type = type(node.op)
            if operator_type not in self._allowed_binary_operators:
                raise ValueError('Unsupported operator in expression')
            if right == 0 and operator_type in {ast.Div, ast.FloorDiv}:
                raise ValueError('Division by zero')
            return float(self._allowed_binary_operators[operator_type](left, right))
        raise ValueError('Unsafe or unsupported expression')

@dataclass(slots=True)
class ManualCaptchaSolver(CaptchaSolver):

    def solve(self, image_bytes: bytes) -> str:
        del image_bytes
        return input('Enter captcha answer manually: ').strip()

# Global variable to hold singleton ddddocr instance to save loading time and RAM footprint
_LAZY_OCR_INSTANCE = None

@dataclass(slots=True)
class OcrMathCaptchaSolver(CaptchaSolver):
    parser: MathExpressionParser

    def solve(self, image_bytes: bytes) -> str:
        global _LAZY_OCR_INSTANCE
        try:
            import cv2
            import ddddocr
            import numpy as np
        except ImportError as error:
            raise RuntimeError('OCR dependencies missing. Install ddddocr and opencv-python-headless.') from error
        
        # Load the ONNX model only once
        if _LAZY_OCR_INSTANCE is None:
            _LAZY_OCR_INSTANCE = ddddocr.DdddOcr(show_ad=False)
        ocr = _LAZY_OCR_INSTANCE

        image_array = np.frombuffer(image_bytes, dtype=np.uint8)
        source = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if source is None:
            raise ValueError('Could not decode captcha image')
        grayscale = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(grayscale, 120, 255, cv2.THRESH_BINARY)
        kernel = np.ones((2, 2), np.uint8)
        clean_image = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        final_image = cv2.bitwise_not(clean_image)
        cv2.imwrite('output/debug_captcha.png', final_image)
        _, buffer = cv2.imencode('.png', final_image)
        processed_bytes = buffer.tobytes()
        raw_text = ocr.classification(processed_bytes)
        print(f"[DEBUG] OCR detected raw text: '{raw_text}'")
        return self.parser.parse(raw_text)

@dataclass(slots=True)
class FallbackCaptchaSolver(CaptchaSolver):
    primary: CaptchaSolver
    secondary: CaptchaSolver

    def solve(self, image_bytes: bytes) -> str:
        try:
            answer = self.primary.solve(image_bytes)
            if answer:
                return answer
        except Exception:
            pass
        return self.secondary.solve(image_bytes)
