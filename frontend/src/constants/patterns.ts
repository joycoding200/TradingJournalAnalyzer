/**
 * Pattern label mappings and dimension system.
 * V1.1: 4-dimension system (market_env / behavior / outcome / psychology).
 */

// V1.1 — 4 dimensions
export const DIMENSION_LABELS: Record<string, string> = {
  market_env: "市场环境",
  behavior: "交易行为",
  outcome: "交易结果",
  psychology: "心理推测",
};

export const DIMENSION_ORDER = ["market_env", "behavior", "outcome", "psychology"];

export const PATTERN_LABELS: Record<string, string> = {
  // 市场环境
  BULL_TREND: "牛市环境",
  BEAR_TREND: "熊市环境",
  SIDEWAYS: "震荡市",
  BREAKOUT: "向上突破",
  BREAKDOWN: "向下破位",
  // 交易行为
  CHASE: "追涨",
  BOTTOM: "抄底",
  PYRAMID: "加仓",
  AVERAGE_DOWN: "补仓",
  TURN: "做T",
  SCALP: "短线",
  SWING: "波段",
  POSITION: "长持",
  FOMO: "害怕错过",
  // 交易结果
  TIGHT_STOP: "小亏离场",
  TRAILING_STOP: "小赚离场",
  TIME_EXIT: "时间离场",
  LARGE_LOSS_EXIT: "大亏离场",
  // 心理推测 (AI推测)
  POSSIBLE_REVENGE: "可能报复",
  OVERTRADING: "高频交易日",
  HOLD_LOSER: "死扛亏损",
  CUT_WINNER: "过早止盈",
  PSY_FOMO: "害怕错过(心理)",
};

export const PATTERN_MODULES: Record<string, string> = {
  // market_env
  BULL_TREND: "market_env", BEAR_TREND: "market_env", SIDEWAYS: "market_env", BREAKDOWN: "market_env",
  // behavior
  CHASE: "behavior", BOTTOM: "behavior", BREAKOUT: "behavior",
  PYRAMID: "behavior", AVERAGE_DOWN: "behavior", TURN: "behavior",
  SCALP: "behavior", SWING: "behavior", POSITION: "behavior", FOMO: "behavior",
  // outcome
  TIGHT_STOP: "outcome", TRAILING_STOP: "outcome", TIME_EXIT: "outcome", LARGE_LOSS_EXIT: "outcome",
  // psychology
  POSSIBLE_REVENGE: "psychology", OVERTRADING: "psychology",
  HOLD_LOSER: "psychology", CUT_WINNER: "psychology", PSY_FOMO: "psychology",
};

export function patternLabel(name: string): string {
  return PATTERN_LABELS[name] || name;
}

export function dimensionLabel(dim: string): string {
  return DIMENSION_LABELS[dim] || dim;
}
