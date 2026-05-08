# 外部链接自动路由

当用户发送链接时，按域名选择处理方式，**不要先试 WebFetch 再失败回退**。

| 域名 | 处理方式 | 具体操作 |
|------|---------|---------|
| `tapd.woa.com` | **TAPD MCP 直查** | 从 URL 提取 workspace_id 和 story/bug ID，curl JSON-RPC 调用 `proxy_execute_tool` |
| `iwiki.woa.com` | **iWiki MCP 直查** | 从 URL 提取 docid，调用 iWiki MCP `getDocument` |
| `km.woa.com` | **KM mcporter 直查** | 需 `export TAI_IT_TOKEN`。K 吧 URL（含 `/group/`）必须传完整 URL，不能只传末尾数字 |
| `miro.com` | 存链接，标记待补充 | 动态渲染看板，无法抓取 |
| 其他 `*.woa.com` | 存链接，标记待补充 | 大部分需认证 |
| 外网 | **WebFetch 抓取** | 正常抓取内容摘要 |

缺工具/技能时主动提醒用户：[Knot 技能市场](https://knot.woa.com/skills/market)
