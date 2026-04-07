# Bug 复盘：导航点击失效 & 图表空白 (2026-04-07)

**状态**：✅ 已修复 | **影响范围**：前端导航+图表渲染 | **严重级别**：High

---

## 问题症状

**症状1**：有色金属等子栏目（如 `512400` ETF）点击后不跳转  
**症状2**：近期涨跌幅对比、雷达图、基金规模、年收益排名四个模块内容为空

---

## 根本原因

修复前的 `switchPanel()` 函数（etf_report.html 第 13096-13107 行）存在三个 critical 级别的防御性检查缺失：

```javascript
// ❌ 原始代码 - 三处隐患
function switchPanel(panelId) {
    document.querySelectorAll('.etf-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    
    // 隐患1：element可能为null
    document.getElementById('panel-' + panelId).classList.add('active');
    
    // 隐患2：event可能为null
    event.target.classList.add('active');
    
    if (panelId === 'overview') {
        initCharts();
    // 隐患3：klineData可能不存在
    } else if (klineData[panelId]) {
        setTimeout(() => renderKlineChart(panelId), 100);
    }
}
```

### 为什么会导致两个症状

1. 当用户点击某个 panelId（如 `512400`）对应的 DOM 元素不存在时
2. `document.getElementById('panel-512400')` 返回 `null`
3. 紧接着执行 `.classList.add('active')` → **异常中断**
4. 整个函数**立即崩溃**，**后续代码永不执行**
5. `initCharts()` 无法被调用 → 图表无法初始化 → 四个模块为空

**级联故障链**：
```
点击导航 → switchPanel() → 
  ├─ getElementById 返回 null ❌
  └─ 异常中断 → 
      └─ initCharts() 永不被调用 ❌
          └─ 图表数据无法渲染 ❌
```

---

## 修复方案

```javascript
// ✅ 修复后的版本
function switchPanel(panelId) {
    // 1️⃣ 防御性检查：panel元素是否存在
    const panel = document.getElementById('panel-' + panelId);
    if (!panel) {
        console.error('Panel not found: panel-' + panelId);
        return;  // 优雅返回，不中断函数流程
    }
    
    // 隐藏其他面板、移除标签活跃状态
    document.querySelectorAll('.etf-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    panel.classList.add('active');
    
    // 2️⃣ 防御性检查：event对象是否存在
    if (event && event.target) {
        event.target.classList.add('active');
    }
    
    // 3️⃣ 防御性检查：klineData对象是否存在
    if (panelId === 'overview') {
        initCharts();
    } else if (klineData && klineData[panelId]) {
        setTimeout(() => renderKlineChart(panelId), 100);
    }
}
```

**修改位置**：`etf_report.html` 第 13096-13117 行  
**修改影响**：+8 行防御性代码，无破坏性改动

---

## 为什么这个问题重复出现

### 1. 缺少防御编程规范

在 JavaScript 前端开发中，常见的"假设式编程"：
- ❌ 假设所有 DOM 元素都存在
- ❌ 假设全局对象总是可用
- ❌ 假设 event 对象永远存在

一旦假设破裂，整个函数崩溃。

### 2. 测试覆盖不足

通常只测试"happy path"（正常流程）：
- ✓ 点击存在的栏目 → 成功切换
- ✗ 点击不存在的栏目 → 优雅降级
- ✗ event 为 null 的场景 → 不崩溃
- ✗ klineData 不存在 → 不崩溃

### 3. 缺少结构化错误日志

没有实时监控机制，问题隐性存在数天/数周后才被用户发现。

---

## 预防策略

### 1. 防御编程规范

**所有 DOM 查询都要前置检查**：
```javascript
// ❌ 危险
const el = document.getElementById(id);
el.classList.add('active');

// ✅ 安全
const el = document.getElementById(id);
if (!el) return;
el.classList.add('active');
```

**依赖对象的存在性检查**：
```javascript
// ❌ 危险
if (klineData[panelId]) { ... }  // 如果 klineData 为 undefined 会报错

// ✅ 安全
if (klineData && klineData[panelId]) { ... }
```

**Event 对象安全处理**：
```javascript
// ❌ 危险
event.target.classList.add('active');

// ✅ 安全
if (event && event.target) {
    event.target.classList.add('active');
}

// ✅ 更好的做法：显式注入，避免依赖全局 event
function switchPanel(panelId, targetElement) {
    if (targetElement) {
        targetElement.classList.add('active');
    }
}
```

### 2. 结构化错误日志

```javascript
function switchPanel(panelId) {
    try {
        const panel = document.getElementById('panel-' + panelId);
        if (!panel) {
            console.error(`[switchPanel] Panel not found`, {
                timestamp: new Date().toISOString(),
                panelId,
                availablePanels: Array.from(document.querySelectorAll('.etf-panel'))
                    .map(p => p.id)
            });
            return;
        }
        // ... 后续代码
    } catch (error) {
        console.error(`[switchPanel] Fatal error:`, error, { panelId });
    }
}
```

### 3. 代码审查检查表

每次 code review 都检查以下项：

```checklist
□ 所有 document.getElementById/querySelector 都有 null 检查？
□ 所有对象属性访问都用 && 链式检查？（如 obj && obj.prop）
□ Event 对象访问都有防护？
□ 是否有 try-catch 覆盖可能的异常？
□ 错误日志是否包含足够的上下文信息？
```

### 4. 单元测试覆盖

```javascript
// 应覆盖的测试场景
describe('switchPanel()', () => {
    it('✅ 点击存在的panelId时正常切换', () => { ... });
    it('✅ 点击不存在的panelId时优雅返回', () => { ... });
    it('✅ event为null时不崩溃', () => { ... });
    it('✅ klineData为undefined时不崩溃', () => { ... });
    it('✅ 确保initCharts在panelId=overview时被调用', () => { ... });
    it('✅ 确保renderKlineChart在有数据时被调用', () => { ... });
});
```

### 5. 浏览器 DevTools 监控

修复后，可以在浏览器控制台看到清晰的错误日志：
```
[switchPanel] Panel not found {
  timestamp: "2026-04-07T15:00:00.000Z",
  panelId: "512400",
  availablePanels: ["overview", "512400", "513120", ...]
}
```

这样下次出问题时，用户可以直接截图错误日志，快速定位问题。

---

## 总结

| 项目 | 内容 |
|------|------|
| **Bug 根源** | JavaScript 缺少防御性编程（null/undefined 检查不足） |
| **传播机制** | 一处异常导致级联故障（函数中断 → 后续代码不执行） |
| **为何重复** | 没有统一的错误处理规范、测试覆盖不足、缺少 error logging |
| **长期方案** | 建立防御编程标准、完善测试覆盖、实现结构化日志 |
| **立即行动** | 为所有前端函数补充 null/undefined 检查 |

---

## 相关文档

- 📖 本技能的标准工作流：`SKILL.md`
- 🏗️ 完整技术文档：`ETF投资报告工作流SDD.md`
- 🗺️ 未来规划：`FUTURE_ROADMAP.md`

