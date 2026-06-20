这是我基于你当前项目架构（Parser → Trade → Position → Pattern → Insight → WhatIf）以及你产品定位（交易行为分析 + 反事实回测）整理出来的 **Golden Dataset Specification v1**。

目标不是覆盖代码行数，而是覆盖：
    1. 用户真实上传交割单
    2. 系统实际分析结果
    3. 用户最关心的结论
    4. 回归测试稳定性

* * *

TradeLens Golden Dataset Specification v1
=========================================

测试目标
----

验证以下模块：
    SmartParser
    PositionBuilder
    PatternEngine
    StatsEngine
    InsightEngine
    WhatIfEngine
    ReportGenerator

验证以下属性：
    正确性 Correctness
    稳定性 Stability
    边界条件 Edge Cases
    回归检测 Regression
    商业价值 Business Value

* * *

数据集目录
=====

    golden/
    
    ├── parser/
    ├── position/
    ├── pattern/
    ├── stats/
    ├── insight/
    ├── whatif/
    ├── account/
    └── fixtures/

* * *

Dataset Metadata
================

每个 Case 必须包含：
    {
      "id": "P001",
      "name": "single_profitable_trade",
      "description": "单次盈利交易",

      "input": {
        "csv": "P001.csv"
      },

      "expect": {

      }
    }

* * *

Parser Specification
====================

目录：
    golden/parser/

* * *

Parser 输出验证字段
-------------

    {
      "trade_count": 0,
    
      "buy_count": 0,
      "sell_count": 0,
    
      "symbols": [],
    
      "first_trade": {},
      "last_trade": {}
    }

* * *

必测场景
----

### GP001

东方财富导出

* * *

### GP002

同花顺导出

* * *

### GP003

华泰导出

* * *

### GP004

银河证券导出

* * *

### GP005

国泰君安导出

* * *

### GP006

中信证券导出

* * *

### GP007

GBK编码

* * *

### GP008

UTF8-BOM

* * *

### GP009

列顺序打乱

* * *

### GP010

缺失列

预期：
    {
      "parse_success": false
    }

* * *

Position Specification
======================

目录：
    golden/position/

* * *

Position Expected Schema
------------------------

    {
      "position_count": 1,
    
      "positions": [
        {
          "symbol": "600000",
    
          "entry_date": "2025-01-01",
          "exit_date": "2025-01-10",
    
          "holding_days": 9,
    
          "avg_entry_price": 10.0,
          "avg_exit_price": 12.0,
    
          "total_quantity": 100,
    
          "pnl": 200.0,
          "pnl_pct": 0.20,
    
          "cost_known": true,
    
          "entry_count": 1
        }
      ]
    }

* * *

必测场景
----

### P001

单买单卖

* * *

### P002

盈利加仓

* * *

### P003

亏损补仓

* * *

### P004

部分卖出

* * *

### P005

多股票交叉

* * *

### P006

未平仓

* * *

### P007

孤儿卖单

重点：
    {
      "cost_known": false
    }

* * *

### P008

手续费

验证：
    {
      "gross_pnl": 200,
      "net_pnl": 190
    }

* * *

### P009

build_grouped模式

* * *

### P010

A股做T

* * *

Pattern Specification
=====================

目录：
    golden/pattern/

* * *

Pattern Expected Schema
-----------------------

    {
      "position_id": "xxx",
    
      "patterns": [
        "CHASE",
        "SWING"
      ],
    
      "primary_patterns": {
        "behavior": "CHASE",
        "market_env": "BULL_TREND"
      }
    }

* * *

行为类 Pattern
===========

必须覆盖：
    CHASE
    BOTTOM
    BREAKOUT
    PYRAMID
    AVERAGE_DOWN
    TURN
    SCALP
    SWING
    POSITION
    FOMO

* * *

心理类 Pattern
===========

必须覆盖：
    POSSIBLE_REVENGE

    OVERTRADING

    HOLD_LOSER

    CUT_WINNER

    PSY_FOMO

* * *

结果类 Pattern
===========

必须覆盖：
    TIGHT_STOP

    TRAILING_STOP

    TIME_EXIT

    LARGE_LOSS_EXIT

* * *

市场环境类
=====

必须覆盖：
    BULL_TREND

    BEAR_TREND

    BREAKDOWN

* * *

Pattern 边界测试
============

必须增加：

### PT001

CHASE边界
    14.9%

false

* * *

### PT002

15.0%

true

* * *

### PT003

BREAKOUT与CHASE同时满足

验证：
    {
      "primary_behavior": "BREAKOUT"
    }

或源码实际结果

* * *

Stats Specification
===================

目录：
    golden/stats/

* * *

Stats Expected Schema
---------------------

建议严格校验：
    {
      "total_trades": 0,

      "winning_trades": 0,

      "losing_trades": 0,

      "win_rate": 0.0,

      "profit_factor": 0.0,

      "expectancy": 0.0,

      "total_return_pct": 0.0,

      "max_drawdown_pct": 0.0,

      "avg_holding_days": 0,

      "max_consecutive_losses": 0
    }

* * *

必测场景
----

### S001

全盈利

* * *

### S002

全亏损

* * *

### S003

50%胜率

* * *

### S004

高胜率低收益

* * *

### S005

低胜率高收益

验证：
    趋势交易者模型

* * *

Insight Specification
=====================

目录：
    golden/insight/

* * *

Expected Schema
---------------

    {
      "best_pattern": "",
    
      "worst_pattern": "",
    
      "best_expectancy": 0,
    
      "worst_expectancy": 0
    }

* * *

必测
--

### I001

CHASE亏钱

TREND赚钱

* * *

预期：
    {
      "best_pattern": "TREND",
      "worst_pattern": "CHASE"
    }

* * *

### I002

样本数不足

验证：
    是否过滤

* * *

WhatIf Specification
====================

目录：
    golden/whatif/

* * *

Expected Schema
---------------

    {
      "pattern": "CHASE",
    
      "removed_positions": 0,
    
      "original_return": 0,
    
      "new_return": 0,
    
      "delta_return": 0
    }

* * *

必测场景
====

### W001

删除CHASE

* * *

### W002

删除AVERAGE_DOWN

* * *

### W003

删除最佳策略

验证：
    不能当成worst

* * *

### W004

cost_known=false仓位

验证：
    是否被过滤

* * *

End-to-End Account Specification
================================

目录：
    golden/account/

这是最重要的数据集。

* * *

A001
----

追涨型散户

预期：
    {
      "worst_pattern": "CHASE"
    }

* * *

A002
----

补仓死扛型

预期：
    {
      "worst_pattern": "AVERAGE_DOWN"
    }

* * *

A003
----

趋势交易者

预期：
    {
      "best_pattern": "BREAKOUT"
    }

* * *

A004
----

过度交易者

预期：
    {
      "worst_pattern": "OVERTRADING"
    }

* * *

A005
----

成长型交易者

前期：
    CHASE
    AVERAGE_DOWN

后期：
    BREAKOUT
    TREND

预期：
    {
      "improvement_detected": true
    }

（如果源码支持）

* * *

Golden Dataset V1 规模
====================

建议首版：

| 类型       | 数量  |
| -------- | --- |
| Parser   | 10  |
| Position | 10  |
| Pattern  | 20  |
| Stats    | 5   |
| Insight  | 5   |
| WhatIf   | 5   |
| Account  | 5   |
| 总计       | 60  |

* * *


