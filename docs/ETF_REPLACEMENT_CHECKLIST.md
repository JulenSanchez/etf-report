# ETF 替换 Checklist

**适用场景**: 把 ETF 池中的某只标的整体替换为另一只标的时使用  
**目标**: 避免只改代码或只改文案，造成配置、页面、运行时、校验链不一致

---

## 1. 先确认事实源

优先用 `AKShare` 做替换前核验：

- `fund_name_em()`：确认基金代码、简称、基金类型
- `fund_etf_category_ths()`：确认正式全称
- `fund_portfolio_hold_em(symbol=..., date=...)`：获取最近披露的前十大持仓

至少确认这些字段：

- 新 ETF 代码
- 页面展示简称（项目内短名）
- 正式全称（详情页 / 需求单可用）
- 市场（`sh` / `sz`）
- 默认基准指数
- 最近一期前十大持仓与集中度

> 建议同时写一份最小映射：`old_code -> new_code`、`old_short_name -> new_short_name`、`old_theme -> new_theme`

---

## 2. 替换配置事实源

必改文件：

- `config/config.yaml`
- `config/config.example.yaml`
- `config/holdings.yaml`

检查点：

- `etfs` 列表中的代码、简称、市场已切换
- `system_check.etf_codes` 已同步
- `holdings.yaml` 已替换为新 ETF 最近一期披露持仓
- 前十大持仓集中度已重新计算

---

## 3. 收口校验脚本

优先做成**配置驱动**，避免手工维护多份 ETF 清单：

- `scripts/health_check.py`
- `scripts/verify_html_integrity.py`

检查点：

- ETF 列表优先从 `config` 读取
- 默认兜底列表也与当前配置一致
- 有最小测试覆盖，避免未来回退到旧硬编码

---

## 4. 替换页面结构与语义

核心文件：`index.html`

至少检查这些位置：

- 导航 tab
- 总览卡
- `switchPanel('CODE')`
- `panel-CODE` 及整组 `*-CODE` DOM id
- 详情页标题 / 基金信息 / 持仓摘要
- 研究卡、推荐摘要、宏观页中直接绑定旧主题的语义

建议按三层检查：

1. **标识层**：代码、DOM id、panel 切换
2. **展示层**：简称、全称、主题名
3. **语义层**：研究文案、宏观提示、行业表理由

---

## 5. 重建运行时产物

执行：

```bash
python scripts/update_report.py
```

预期会同步刷新：

- `data/etf_full_kline_data.json`
- `data/etf_realtime_data.json`
- `data/runtime_payload.js`
- `index.html` 中的内联 `klineData` / `realtimeData`

---

## 6. 验证收口

至少执行：

- `python scripts/verify_html_integrity.py`
- `python scripts/health_check.py`
- `pytest`

还要补一轮文本搜索：

- 搜 `old_code`
- 搜旧简称 / 旧全称
- 搜旧主题关键词

通过标准：

- 活跃链路中不再出现旧 ETF 标识
- HTML 完整性验证通过
- 健康检查通过
- 测试通过

---

## 7. 更新需求与导航

建议同步：

- 需求看板：记录替换状态、目标版本（如果你在维护此项目）
- `SKILL.md`：如果这份 checklist 会复用，挂进导航

---

## 最小替换模板

```text
旧代码: 159698
旧简称: 粮食产业ETF
旧主题: 粮食 / 种业 / 转基因

新代码: 159865
新简称: 养殖ETF
新全称: 国泰中证畜牧养殖ETF
新主题: 畜牧养殖 / 生猪 / 饲料
```

---

**经验结论**: ETF 替换不是“换一个代码”，而是“替换一条贯穿配置、页面、运行时和校验的事实链”。先确认事实源，再做批量替换，最后靠主流程和校验脚本收口。