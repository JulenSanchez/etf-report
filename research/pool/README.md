# pool/ — ETF 池研究证据

> 本目录记录 ETF 池候选、换池实验和历史证据，不维护当前 universe 副本。当前生效池子以 `../../config/quant_universe.yaml` 为准。

## 工作流

| 场景 | Owner 文档 |
|---|---|
| ETF 候选筛选 | `../../docs/runbook/v2-quant/screening.md` |
| ETF 池变更 | `../../docs/runbook/v2-quant/pool-change.md` |
| 研究结论投产 | 更新 `../../research/params/README.md` 时间线 + 对应 REQ 状态 |

## 字段参考

新增 ETF 到 `quant_universe.yaml` 时需填写的字段：

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `code` | 是 | string | 6 位交易代码 |
| `name` | 是 | string | 显示短名，去公司后缀，与池内风格一致 |
| `market` | 是 | string | `sh` / `sz` |
| `sector` | 是 | string | 扇区归属，用于展示和归因 |
| `qdii` | 条件必填 | bool | 跨境 QDII 品种必须标 true |
| `marginable` | 条件必填 | bool | 两融/杠杆研究需要显式标注 |
| `bias` | 否 | bool | 扇区内偏好加成 |

## 当前索引

| 记录 | 内容 | 状态 |
|---|---|---|
| `rounds/2026-06-16.md` | R15：+9/-4，油气→石油，池子 49→54 | 历史证据，当前池子仍以 config 为准 |

## Open Questions

| 问题 | 状态 |
|---|---|
| 34→40 的 6 支 ETF 来源 | 待追溯 |
| 巴西 520870 vs 159100 | 待判 |
| 粮食 159698 是否存在更好替代 | 待判 |

## 规则

1. 不在本文件复制完整当前池子表。
2. Applied 日志只写变更摘要和证据链接。
3. 当前 universe 永远以 `../../config/quant_universe.yaml` 为准。
