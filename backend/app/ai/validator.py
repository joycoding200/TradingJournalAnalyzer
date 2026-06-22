"""Output validator: extract key metrics from AI report and verify against input data.

Supports automatic retry when the generated report contains mismatched numbers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """Result of validating an AI-generated report."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)


class ReportValidator:
    """Validate AI-generated trading diagnosis report against input analysis data."""

    @staticmethod
    def validate(report: str, input_data: dict) -> ValidationResult:
        """Check the report's key numbers match the input analysis data.

        Checks performed (when the corresponding key exists in input_data):
            - total_trades count
            - win_rate percentage (with 1% tolerance)
            - each pattern's total_pnl (when the pattern name is found in report)

        Args:
            report: The AI-generated diagnosis report text.
            input_data: Dict containing the original analysis data keys.

        Returns:
            A ValidationResult with is_valid=True if no mismatches found.
        """
        errors: list[str] = []

        total_trades = input_data.get("total_trades")
        if total_trades is not None:
            # Look for number with context like "交易次数"
            found = ReportValidator._extract_number(report, r"交易次数[：:\s]*(\d+)")
            if found is None:
                # Fallback: any number
                found = ReportValidator._extract_number(report, r"(\d+)")
            if found is not None and found != total_trades:
                errors.append(
                    f"交易次数不匹配: 报告={found}, 数据={total_trades}"
                )

        win_rate = input_data.get("win_rate")
        if win_rate is not None:
            # Look for percentage with context like "胜率"
            found = ReportValidator._extract_percentage(
                report, r"胜率[：:\s]*(\d+(?:\.\d+)?)%"
            )
            if found is None:
                # Fallback: any percentage
                found = ReportValidator._extract_percentage(
                    report, r"(\d+(?:\.\d+)?)%"
                )
            if found is not None and abs(found - win_rate) > 1.0:
                errors.append(
                    f"胜率不匹配: 报告≈{found:.0f}%, 数据={win_rate:.0f}%"
                )

        patterns = input_data.get("patterns", [])
        for p in patterns:
            name = p["pattern_name"]
            expected_pnl = p["total_pnl"]
            found_pnl = ReportValidator._find_pnl_for_pattern(report, name)
            if found_pnl is not None and abs(found_pnl - expected_pnl) > 0.01:
                errors.append(
                    f"{name} 总盈亏不匹配: 报告≈{found_pnl:.2f}, 数据={expected_pnl:.2f}"
                )

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_number(text: str, pattern: str) -> int | None:
        """Return the first integer match, or None."""
        m = re.search(pattern, text)
        return int(m.group(1)) if m else None

    @staticmethod
    def _extract_percentage(text: str, pattern: str) -> float | None:
        """Return the first percentage value, or None."""
        m = re.search(pattern, text)
        return float(m.group(1)) if m else None

    @staticmethod
    def _find_pnl_for_pattern(text: str, pattern_name: str) -> float | None:
        """Search for a signed float near the given pattern name."""
        escaped = re.escape(pattern_name)
        # Matches "PATTERN_NAME..." optionally followed by delimiters and a number.
        m = re.search(rf"{escaped}.*?([+-]?\d+\.?\d*)", text, re.DOTALL)
        return float(m.group(1)) if m else None


import asyncio
import logging

logger = logging.getLogger(__name__)


async def generate_with_retry(
    provider,
    system_prompt: str,
    user_prompt: str,
    input_data: dict,
    max_retries: int = 3,
) -> str:
    """Generate a report with automatic retry on validation failure and network errors.

    If the generated report fails validation, a correction instruction is
    appended to the user prompt and the request is retried (up to max_retries).

    Args:
        provider: An LLMProvider instance.
        system_prompt: The system prompt string.
        user_prompt: The user prompt string.
        input_data: The original analysis data dict for validation.
        max_retries: Maximum number of generation attempts (default 3).

    Returns:
        The final report text (last attempt even if still invalid).
    """
    validator = ReportValidator()
    current_prompt = user_prompt

    for attempt in range(max_retries):
        try:
            report = await provider.generate(system_prompt, current_prompt)
        except Exception as e:
            logger.warning(f"LLM generation failed (attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
            continue

        result = validator.validate(report, input_data)
        if result.is_valid:
            return report

        if attempt < max_retries - 1:
            correction = (
                "\n\n【修正】上轮生成的报告数据与输入数据不匹配：\n"
                + "\n".join(result.errors)
                + "\n请修正数据后重新生成。"
            )
            current_prompt = user_prompt + correction

    return report
