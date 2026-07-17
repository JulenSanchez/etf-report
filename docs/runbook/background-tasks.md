# 后台任务管理 SOP

> **读者**: AI Agent。本文件规定在 etf-report 项目中启动/管理后台任务（尤其是多进程长任务，如批量回测/扫参驱动）的纪律。
>
> **核心原则**: harness 的进程管理是约束不是障碍。禁止绕过。

---

## 一、禁用 detached 进程

**禁止**用以下方式起脱离 harness 的后台任务：

- PowerShell `Start-Process`
- `nohup ... &`
- `tmux new-window ...`
- `screen -d -m ...`

**原因**：
1. 任务完成通知丢失——harness 收不到信号，AI 不知道任务结束了
2. 子进程 worker 变孤儿，累积吃内存
3. 用户机器最终累积几百个孤儿进程，被迫喊停

**正确做法**：用 Bash 工具 `run_in_background: true`，等 task-notification。如果 harness 的超时不够用，**报告给用户**，让用户在 shell 里手动起任务，AI 不接管进程管理。

---

## 二、第二次失败必查根因

后台任务**第二次**失败时，禁止第三次盲目重试。必须先执行诊断：

```bash
# 1. 查残留进程
tasklist /FI "IMAGENAME eq python.exe" /FO CSV
tasklist /FI "IMAGENAME eq bash.exe" /FO CSV

# 2. 查系统内存
wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /Value

# 3. 查 Windows Event Viewer 关键事件（最近 1 小时）
# 让用户协助查看：Event Viewer → Windows Logs → Application → Error
```

**根因排查清单**：
- [ ] 有孤儿 worker 进程？（python.exe 父进程已死但子进程还活着）
- [ ] 系统可用内存 < 1GB？
- [ ] 任务在启动阶段就死，还是跑到中途死？
- [ ] 上一次成功跑和这次失败的差异是什么？

查清根因后再决定是否重试。**禁止"换一个参数再试一次"的盲目重试**。

---

## 三、失败模式对比

**首选诊断工具**：成功 vs 失败的差异。

典型场景：批次 1 能跑完，批次 2 五次 killed。差异是什么？

| 维度 | 批次 1（成功） | 批次 2（失败） |
|------|---------------|---------------|
| 启动时是否有孤儿进程 | 无 | 有（批次 1 被中断后留下 7 个孤儿） |
| pool.json 状态 | 干净 | 批次 1 改写过 |
| 系统内存 | 充足 | 被孤儿占满 |

**找到差异 → 针对性修复**（清孤儿），而不是换参数重试。

---

## 四、进程清理钩子

用 `concurrent.futures.ProcessPoolExecutor` 的脚本**必须**注册退出钩子：

```python
import atexit, signal

_active_executors = set()

def _register_executor(ex):
    _active_executors.add(ex)

def _unregister_executor(ex):
    _active_executors.discard(ex)

def _cleanup_workers(signum=None, frame=None):
    """SIGTERM/SIGINT 时强制 shutdown worker，防孤儿。"""
    for ex in list(_active_executors):
        try:
            ex.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
    _active_executors.clear()
    if signum is not None:
        raise SystemExit(128 + signum)

# 注册
atexit.register(_cleanup_workers)
signal.signal(signal.SIGTERM, _cleanup_workers)
signal.signal(signal.SIGINT, _cleanup_workers)

# 使用
ex = ProcessPoolExecutor(max_workers=n)
_register_executor(ex)
try:
    with ex:
        # ... submit tasks ...
finally:
    _unregister_executor(ex)
```

**参考实现**：历史脚本 `iterative_optimizer.py`（REQ-362 已退役）曾采用此模式；新脚本按上方代码骨架实现即可。

---

## 五、任务结束扫孤儿

任何后台任务**结束**（正常完成或异常退出）后，必须扫一遍孤儿 worker 进程：

```bash
# 正常结束后扫（可能有 worker 还在退出中）
tasklist /FI "IMAGENAME eq python.exe" /FO CSV | findstr /v "PID"

# 发现孤儿（无父进程的 python.exe）时清理：
taskkill /F /IM python.exe /FI "MEMUSAGE gt 100000"
```

**注意**：
- `taskkill /F /IM python.exe` 会杀所有 python 进程，包括 Tuner——谨慎
- 先用 `wmic process where "name='python.exe'" get ProcessId,ParentProcessId,CommandLine` 确认哪些是孤儿
- 只 kill 命令行中含本项目回测/扫参脚本字样（如 `quant_backtest`）的进程

---

## 六、不轮询

**禁止**用 `sleep` + 主动查询的方式盯后台任务进度。

**正确做法**：
- Bash 工具 `run_in_background: true` 启动
- 等 task-notification 自动到达
- 收到通知后才取结果

**Monitor 工具**（如可用）：设合理超时（默认 300s，长任务 600s），超时不是任务失败——只是监控窗口结束，需要重设。

---

## 七、与 optimize.md 的关系

`/optimize` 命令的 §4.1（启动后台任务）和 §6（bug 处理）都依赖本文件。

**optimize.md §4.1 启动前必读本文件**，确认：
1. 没有孤儿进程（§五）
2. 用 `run_in_background: true`（§一、§六）
3. 不用 Start-Process 绕过（§一）
