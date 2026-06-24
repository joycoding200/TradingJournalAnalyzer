"""Tests for prompt templates."""
from app.ai.prompt import SYSTEM_PROMPT, build_user_prompt


class TestSystemPrompt:
    """SYSTEM_PROMPT must be in Chinese and contain required sections."""

    def test_is_chinese_trading_coach(self):
        assert "交易行为诊断书" in SYSTEM_PROMPT

    def test_contains_core_principle(self):
        assert "只分析行为" in SYSTEM_PROMPT or "不预测市场" in SYSTEM_PROMPT

    def test_contains_output_sections(self):
        assert "核心结论" in SYSTEM_PROMPT
        assert "优势清单" in SYSTEM_PROMPT
        assert "风险警示" in SYSTEM_PROMPT
        assert "改善建议" in SYSTEM_PROMPT


class TestBuildUserPrompt:
    """build_user_prompt() must include all provided data."""

    def test_basic_structure(self):
        data = {
            "total_trades": 50,
            "win_rate": 45.0,
            "total_pnl": -2500.0,
            "avg_holding_days": 6.5,
            "patterns": [],
            "what_if": [],
        }
        prompt = build_user_prompt(data)
        assert isinstance(prompt, str)
        assert "50" in prompt
        assert "45" in prompt
        assert "-2500" in prompt
        assert "6.5" in prompt

    def test_with_patterns(self):
        data = {
            "total_trades": 50,
            "win_rate": 45.0,
            "total_pnl": -2500.0,
            "avg_holding_days": 6.5,
            "patterns": [
                {
                    "pattern_name": "SCALP",
                    "count": 30,
                    "win_rate": 0.4,
                    "total_pnl": -5000.0,
                },
                {
                    "pattern_name": "SWING",
                    "count": 20,
                    "win_rate": 0.5,
                    "total_pnl": 2500.0,
                },
            ],
            "what_if": [],
        }
        prompt = build_user_prompt(data)
        assert "SCALP" in prompt
        assert "SWING" in prompt
        assert "-5000.0" in prompt or "-5000" in prompt

    def test_with_what_if(self):
        data = {
            "total_trades": 50,
            "win_rate": 45.0,
            "total_pnl": -2500.0,
            "avg_holding_days": 6.5,
            "patterns": [],
            "what_if": [
                {
                    "removed_pattern": "SCALP",
                    "delta": 0.15,
                    "contribution_pct": 1.0,
                }
            ],
        }
        prompt = build_user_prompt(data)
        assert "SCALP" in prompt
        assert "0.15" in prompt
        assert "1.0" in prompt or "1.00" in prompt

    def test_empty_data(self):
        prompt = build_user_prompt({})
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_pattern_format_contains_percentage(self):
        """Win rate should appear as a percentage in the pattern line."""
        data = {
            "total_trades": 10,
            "win_rate": 50.0,
            "total_pnl": 100.0,
            "avg_holding_days": 5.0,
            "patterns": [
                {
                    "pattern_name": "TEST",
                    "count": 10,
                    "win_rate": 0.5,
                    "total_pnl": 100.0,
                }
            ],
            "what_if": [],
        }
        prompt = build_user_prompt(data)
        # 0.5 formatted as 50.0%
        assert "50.0%" in prompt
        assert "+100.00" in prompt or "100.00" in prompt

    # ---- V4.0: risk metrics and positions summary ----

    def test_risk_metrics_section(self):
        """Prompt should include risk metrics when provided."""
        data = {
            "total_trades": 50,
            "win_rate": 45.0,
            "total_pnl": -2500.0,
            "avg_holding_days": 6.5,
            "patterns": [],
            "what_if": [],
            "profit_factor": 0.85,
            "expectancy": -1.2,
            "max_drawdown": 5000.0,
            "max_drawdown_pct": 0.15,
            "consecutive_losses": 5,
            "avg_mae": -0.08,
            "avg_mfe": 0.12,
            "profit_capture_ratio": 0.35,
            "total_return_pct": -0.05,
        }
        prompt = build_user_prompt(data)
        assert "风险指标" in prompt
        assert "盈亏比" in prompt
        assert "0.85" in prompt
        assert "预期收益" in prompt
        assert "最大回撤" in prompt
        assert "连续亏损" in prompt
        assert "最大不利变动" in prompt
        assert "最大有利变动" in prompt
        assert "止盈效率" in prompt
        assert "总收益率" in prompt

    def test_risk_metrics_pf_infinite(self):
        """PF=None (no losses) should render as ∞."""
        data = {
            "total_trades": 10,
            "win_rate": 100.0,
            "total_pnl": 5000.0,
            "avg_holding_days": 3.0,
            "patterns": [],
            "what_if": [],
            "profit_factor": None,  # no losses → ∞
            "expectancy": 5.0,
            "max_drawdown": 0.0,
            "max_drawdown_pct": 0.0,
            "consecutive_losses": 0,
        }
        prompt = build_user_prompt(data)
        assert "∞" in prompt

    def test_positions_summary_section(self):
        """Prompt should include top winners and losers when provided."""
        data = {
            "total_trades": 10,
            "win_rate": 50.0,
            "total_pnl": 100.0,
            "avg_holding_days": 5.0,
            "patterns": [],
            "what_if": [],
            "positions_summary": {
                "top_winners": [
                    {"symbol": "600519", "pnl": 5000.0, "pnl_pct": 0.15, "holding_days": 10, "entry_date": "2026-01-05", "exit_date": "2026-01-15"},
                ],
                "top_losers": [
                    {"symbol": "000001", "pnl": -3000.0, "pnl_pct": -0.08, "holding_days": 3, "entry_date": "2026-02-01", "exit_date": "2026-02-04"},
                ],
            },
        }
        prompt = build_user_prompt(data)
        assert "关键交易" in prompt
        assert "盈利最多" in prompt
        assert "亏损最多" in prompt
        assert "600519" in prompt
        assert "000001" in prompt
        assert "+5000.00" in prompt
        assert "-3000.00" in prompt

    def test_without_risk_metrics_does_not_show_section(self):
        """When risk metrics are absent, the section should not appear."""
        data = {
            "total_trades": 50,
            "win_rate": 45.0,
            "total_pnl": -2500.0,
            "avg_holding_days": 6.5,
            "patterns": [],
            "what_if": [],
        }
        prompt = build_user_prompt(data)
        assert "风险指标" not in prompt
        assert "关键交易" not in prompt
