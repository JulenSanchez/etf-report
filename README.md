# ETF 智能报告系统 (etf-report)

自动分析与生成 6 支 ETF 的投资分析报告，包括 K线数据、技术分析、成分股配置、宏观环境分析。

![Version](https://img.shields.io/badge/version-v2.1.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/YOUR_USERNAME/etf-report.git
cd etf-report
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置

```bash
cp config/config.example.yaml config/config.yaml
# 编辑 config.yaml 配置 API 和参数
```

### 4. 执行

```bash
# 开发模式（仅本地预览）
python scripts/update_report.py

# 发布模式（发送通知 + GitHub Pages 部署）
python scripts/update_report.py --publish
```

## 📊 在线报告

[点击查看最新报告](https://julensanchez.github.io/etf-report/)

## 📚 文档导航

| 文档 | 用途 | 优先级 |
|-----|------|-------|
| **[SKILL.md](SKILL.md)** | 工作流快速入门 | 🔴 必读 |
| **[docs/GIT_WORKFLOW.md](docs/GIT_WORKFLOW.md)** | 安全的 Git 发布流程 | 🔴 必读 |
| **[DESIGN.md](DESIGN.md)** | 架构设计与技术细节 | 🟠 重要 |
| **[WORKFLOW.md](WORKFLOW.md)** | 详细执行步骤 | 🟠 参考 |
| **[docs/HEALTH_CHECK_USAGE.md](docs/HEALTH_CHECK_USAGE.md)** | 健康检查工具使用 | 🟡 可选 |
| **[docs/HEALTH_CHECK_KNOWN_ISSUES.md](docs/HEALTH_CHECK_KNOWN_ISSUES.md)** | 已知问题与解决方案 | 🟡 可选 |
| **[references/](references/)** | API 参数、集成指南 | 🟡 可选 |

## ✨ 核心特性

- ✅ **6 支 ETF 自动分析** - 512400, 513120, 512070, 515880, 159566, 159698
- ✅ **K线数据** - 60日日线 + 52周周线（带 MA5/MA20 均线）
- ✅ **实时行情** - ETF 涨跌幅、成分股涨跌幅
- ✅ **技术分析** - 趋势判断、支撑位/阻力位
- ✅ **成分股配置分析** - 按行业分布、权重分析
- ✅ **宏观环境分析** - 风险偏好建议
- ✅ **结构化日志系统** - JSON 格式、多个日志文件
- ✅ **健康检查工具** - 25 项系统检查、HTML/JSON 报告
- ✅ **GitHub Pages 自动部署** - 发布模式自动更新线上报告

## 🔧 项目结构

```
etf-report/
├── README.md                         # 本文件
├── .gitignore                        # Git 忽略配置
│
├── SKILL.md                          # 工作流说明
├── DESIGN.md                         # 架构设计文档
├── WORKFLOW.md                       # 执行步骤详解
│
├── index.html                        # 根目录主报告（GitHub 展示入口 + 本地预览）
│
├── scripts/                          # 核心脚本（8个）
│   ├── update_report.py             # 主控脚本（入口点）
│   ├── config_manager.py            # 配置管理
│   ├── logger.py                    # 日志系统
│   ├── health_check.py              # 健康检查
│   ├── realtime_data_updater.py     # 实时数据获取
│   ├── fix_ma_and_benchmark.py      # K线处理
│   ├── transaction.py               # 事务管理
│   └── verify_html_integrity.py     # HTML 验证
│
├── config/                           # 配置文件
│   ├── config.yaml                  # 主配置（需用户编辑）
│   ├── config.example.yaml          # 配置示例
│   └── holdings.yaml                # 成分股配置
│
├── outputs/                          # 资源输出目录
│   └── [辅助资源]
│
├── docs/                             # 文档
│   ├── HEALTH_CHECK_USAGE.md        # 健康检查使用指南
│   ├── HEALTH_CHECK_KNOWN_ISSUES.md # 已知问题集
│   └── POSTMORTEM_*.md              # 故障分析
│
└── references/                       # 参考文档
    ├── DAILY_UPDATE_PARAMETERS.md  # 每日更新参数说明
    ├── INTEGRATION_GUIDE.md        # 集成指南
    └── ...
```

## 📋 ETF 池

| 代码 | 名称 | 市场 | 基准指数 |
|-----|------|------|---------|
| 512400 | 有色金属ETF | 沪深 | 沪深300 |
| 513120 | 港股创新药ETF | 沪深 | 沪深300 |
| 512070 | 证券保险ETF | 沪深 | 沪深300 |
| 515880 | 通信设备ETF | 沪深 | 沪深300 |
| 159566 | 储能电池ETF | 沪深 | 沪深300 |
| 159698 | 粮食产业ETF | 沪深 | 沪深300 |

## 🔄 工作流程

```
获取K线数据 → 获取实时行情 → 生成分析报告 → 更新HTML报告
                                      ↓ (发布模式)
                         发送企微通知 + GitHub Pages部署
```

## 📦 版本历史

| 版本 | 日期 | 更新内容 |
|-----|-----|---------|
| **v2.1.0** | 2026-04-07 | Phase 1 完成：配置化、日志系统、健康检查 |
| v2.0 | 2026-03-31 | 数据+模板分离架构，100% 样式保证 |
| v1.4 | 2026-03-17 | 区分开发/发布模式，自动化任务规则 |
| v1.3 | 2026-03-17 | GitHub Pages 自动部署 |
| v1.0 | 2026-03-16 | 初始版本 |

## 🛠️ 配置说明

### config.yaml - 主配置文件

```yaml
api:
  sina:
    # K线数据接口
    kline_endpoint: "https://money.finance.sina.com.cn/..."
    # 实时行情接口
    realtime_endpoint: "https://hq.sinajs.cn/list="

etf_list:
  - code: "512400"
    name: "有色金属ETF"
  # ... 其他 ETF

output:
  html_file: "index.html"           # 根目录主报告
  data_path: "data/"

update_frequency_hours: 15  # 更新间隔（小时）

thresholds:
  daily_change: 2.0         # 日涨跌阈值（%）
```

### holdings.yaml - 成分股配置

每支 ETF 的主要成分股配置，用于实时行情更新。需按季度根据 ETF 季报更新。

## 🏥 健康检查

一键验证系统状态：

```bash
# HTML 报告
python scripts/health_check.py

# JSON 报告
python scripts/health_check.py --format json > report.json
```

包含 25 项检查项：配置文件、数据文件、脚本、HTML 完整性等。

## 📝 更新时间

建议在**交易日收盘后（15:00 之后）**执行更新，非交易日无需更新。

## 🔗 相关链接

- **在线报告**: https://julensanchez.github.io/etf-report/
- **Sina 财经 API**: https://quotes.money.sina.com.cn/
- **GitHub**: https://github.com/YOUR_USERNAME/etf-report

## 📞 问题排查

遇到问题？

1. 查看 [已知问题集](docs/HEALTH_CHECK_KNOWN_ISSUES.md)
2. 运行健康检查：`python scripts/health_check.py`
3. 检查日志文件：`logs/daily.log`

## 📄 License

MIT License - 详见 LICENSE 文件

## 👤 作者

Created with ❤️ for ETF investors

---

**最后更新**: 2026-04-07 | **版本**: v2.1.0
