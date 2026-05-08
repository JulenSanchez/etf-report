# Quant Research 归档

> 按 REQ ID 组织的量化调研产出。每个子目录对应一个已完成的调研需求，内含报告 + 实验数据。

## 索引

| REQ | 标题 | 日期 | 核心发现 | 文件 |
|-----|------|------|---------|------|
| REQ-189 | 后视镜最优收益 | 2026-05-07 | 信息效率6.5%；周收益负自相关(-0.144)；反转(8.5%)>动量(3.4%)<<因子打分(25.4%) | `REQ-189/hindsight_research_report.md` `REQ-189/hindsight_full_results.json` `REQ-189/hindsight_results.json` `REQ-189/hindsight_weekly_top6_log.json` |
| MA-TREND-OPT | MA Trend仓位参数优化 | 2026-05-08 | MA26/B100/B30/DirON Calmar 0.92→1.55, MDD -24%→-16%; Dir=ON是最大单因子; Bear 30%替代40%减回撤不牺牲收益 | `MA-TREND-OPT/report.md` `MA-TREND-OPT/coarse_checkpoint_440of490.json` |

## 目录结构

```
research/
├── README.md          ← 本文件（索引）
├── REQ-189/           ← 后视镜最优收益调研
│   ├── hindsight_research_report.md   ← 完整报告
│   ├── hindsight_full_results.json    ← 全变体×3时段数值
│   ├── hindsight_results.json         ← 汇总结果
│   └── hindsight_weekly_top6_log.json ← 周频Top6组合日志
├── MA-TREND-OPT/       ← MA Trend仓位参数优化
│   ├── report.md                      ← 完整报告
│   ├── coarse_checkpoint_440of490.json ← 440个粗扫结果+checkpoint
│   ├── v1_run_log.txt                 ← v1运行日志
│   ├── v1_nohup_output.txt            ← v1 nohup日志
│   └── v2_nohup_output.txt            ← v2 nohup日志
└── REQ-XXX/           ← 未来调研（按此模式扩展）
    ├── report.md
    └── data.json
```

## 约定

- 每个调研需求一个 `REQ-XXX/` 子目录
- 报告文件以可读 markdown 为主，实验数据以 JSON 为主
- 新增调研时更新本文件索引表
- 对应的 `plans/REQ-XXX.md` 记录需求动机与结论摘要，`research/REQ-XXX/` 存放完整产出
