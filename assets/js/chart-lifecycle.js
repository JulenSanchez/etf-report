/* ============================================================
 * chart-lifecycle.js — ECharts 生命周期管理（ResizeObserver + resize 钩子）
 * 源出处：index.html 原第 9-85 行（REQ-146 抽离）
 * 公共出口：window.__etfChartLifecycle = { bindChart, observeChartDom, whenVisible, resizeAllCharts }
 * 加载顺序：必须先于 report-main.js（report-main 在 13574 / 13723 处消费 lifecycle）
 * 规则：1:1 剪切，不做压缩 / 重写 / 合并
 * ============================================================ */

        // 全局 ECharts 图表生命周期管理
        (function() {
            const observedDoms = new WeakSet();
            const chartSelector = '[id^="holdings-chart-"], [id^="kline-daily-"], [id^="kline-weekly-"], #performance-chart, #radar-chart, #scale-chart, #annual-chart';

            function resizeChartDom(dom) {
                if (typeof echarts === 'undefined' || !dom) return;
                const chart = echarts.getInstanceByDom(dom);
                if (chart) {
                    chart.resize();
                }
            }

            function resizeAllCharts() {
                document.querySelectorAll(chartSelector).forEach(resizeChartDom);
            }

            const observer = typeof ResizeObserver !== 'undefined'
                ? new ResizeObserver(entries => {
                    entries.forEach(entry => {
                        if (entry.target && entry.contentRect.width > 0 && entry.contentRect.height > 0) {
                            resizeChartDom(entry.target);
                        }
                    });
                })
                : null;

            function observeChartDom(dom) {
                if (!dom || observedDoms.has(dom)) return dom;
                observedDoms.add(dom);
                if (observer) {
                    observer.observe(dom);
                }
                return dom;
            }

            function bindChart(dom, chart) {
                observeChartDom(dom);
                return chart;
            }

            function whenVisible(dom, renderFn, retryCount = 0) {
                if (!dom) return;
                if ((dom.offsetWidth === 0 || dom.offsetHeight === 0) && retryCount < 12) {
                    setTimeout(() => whenVisible(dom, renderFn, retryCount + 1), 50);
                    return;
                }
                observeChartDom(dom);
                renderFn();
                setTimeout(() => resizeChartDom(dom), 0);
            }

            window.__etfChartLifecycle = {
                bindChart,
                observeChartDom,
                whenVisible,
                resizeAllCharts,
            };

            window.addEventListener('load', function() {
                requestAnimationFrame(function() {
                    requestAnimationFrame(function() {
                        resizeAllCharts();
                        setTimeout(resizeAllCharts, 100);
                        setTimeout(resizeAllCharts, 300);
                    });
                });
            });

            window.addEventListener('resize', resizeAllCharts);

            if (document.fonts && document.fonts.ready) {
                document.fonts.ready.then(resizeAllCharts);
            }
        })();
