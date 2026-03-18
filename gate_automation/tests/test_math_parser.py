from gate_automation.infrastructure.captcha.solvers import MathExpressionParser


def test_subtraction_expression() -> None:
    parser = MathExpressionParser()
    assert parser.parse("8-3=") == "5"


def test_multiplication_expression() -> None:
    parser = MathExpressionParser()
    assert parser.parse("4x7=") == "28"


def test_spaces_and_noise() -> None:
    parser = MathExpressionParser()
    assert parser.parse(" 5 - 5 = ") == "0"
