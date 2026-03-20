# 待核实数据（core 无直接条目）

| 项 | 说明 |
|----|------|
| **办公用水** 0.168 kgCO2e/m³ | `core` 无自来水 m³ 因子；见 `cpcd_scene_factors.json` → `office_water_m3` |
| **碳价（元/吨 CO2e）** | `core` 为产品碳足迹库，不含碳市场交易价 |

其余场景因子（差旅、通勤、物流金额兜底、废弃物、国内住宿等）见 **`data/cpcd_scene_factors.json`**，与 **`data/core.csv`** 快照一致。**国内住宿**：有发票金额时按支出（2.036 tCO2e/万元）；无金额时按间夜 × 66.52 kgCO2e/晚。
