/* ============================================================
 * debug-toolbar.js — 调试工具栏（显形 / 热区 / 聚焦三模式）
 * 源出处：index.html 原第 13032-13997 行（REQ-146 抽离）
 * 依赖：
 *   - URL 参数 ?debug=1 / ?debugHeat=1
 *   - localStorage：etf-debug-mode-enabled / etf-debug-hotspots-enabled / etf-debug-focus-query
 * 无跨段闭包共享，独立 IIFE
 * 规则：1:1 剪切，不做压缩 / 重写 / 合并
 * ============================================================ */

        (function() {
            const STORAGE_KEY = 'etf-debug-mode-enabled';
            const HOTSPOT_STORAGE_KEY = 'etf-debug-hotspots-enabled';
            const FOCUS_QUERY_STORAGE_KEY = 'etf-debug-focus-query';
            const searchParams = new URLSearchParams(window.location.search);

            const queryDebugEnabled = searchParams.get('debug') === '1';
            const queryHotspotsEnabled = searchParams.get('debugHeat') === '1';
            const marketTickerModules = [
                {
                    label: '全球股指',
                    items: [
                        { symbol: 'S&P 500', value: '5218.6', change: '+0.64%', direction: 'up' },
                        { symbol: 'NASDAQ', value: '18342', change: '+0.91%', direction: 'up' },
                        { symbol: '道琼斯', value: '38984', change: '+0.31%', direction: 'up' }
                    ]
                },
                {
                    label: '利率汇率',
                    items: [
                        { symbol: 'US10Y', value: '4.21%', change: '-0.05%', direction: 'down' },
                        { symbol: 'DXY', value: '104.3', change: '-0.22%', direction: 'down' },
                        { symbol: 'USD/CNH', value: '7.246', change: '+0.08%', direction: 'up' }
                    ]
                },
                {
                    label: '中国市场',
                    items: [
                        { symbol: '上证', value: '3128.4', change: '+0.52%', direction: 'up' },
                        { symbol: '深成指', value: '9686', change: '+0.77%', direction: 'up' },
                        { symbol: '恒生', value: '17366', change: '+0.47%', direction: 'up' }
                    ]
                },
                {
                    label: '大宗商品',
                    items: [
                        { symbol: 'WTI', value: '81.24', change: '-0.38%', direction: 'down' },
                        { symbol: '黄金', value: '2368', change: '+0.44%', direction: 'up' },
                        { symbol: '铜', value: '4.36', change: '+0.58%', direction: 'up' }
                    ]
                },
                {
                    label: '风格追踪',
                    items: [
                        { symbol: '北向资金', value: '+42.6亿', change: '净流入', direction: 'up' },
                        { symbol: '成长风格', value: '偏强', change: '+1.2σ', direction: 'up' },
                        { symbol: '波动率', value: '17.8', change: '-0.6', direction: 'down' }
                    ]
                }
            ];
            const hotTargetSelectorGroups = [
                {
                    kind: 'metric',
                    selectors: [
                        '#report-date-value',
                        '#report-cutoff-value',
                        '[id^="overview-card-"][id$="-change"]',
                        '[id^="overview-card-"][id$="-rating"]',
                        '[id^="overview-card-"][id$="-recommendation"]',
                        '#fund-flow-updated-value',
                        '#market-rotation-stat-leader-name',
                        '#market-rotation-stat-leader-value',
                        '#market-rotation-stat-laggard-name',
                        '#market-rotation-stat-laggard-value',
                        '#market-rotation-stat-average-name',
                        '#market-rotation-stat-average-value',
                        '#market-rotation-stat-breadth-value',
                        '[id^="leaders-top5-table-name-"]',
                        '[id^="leaders-top5-table-weight-"]',
                        '[id^="leaders-top5-table-change-"]',
                        '[id^="laggards-top5-table-name-"]',
                        '[id^="laggards-top5-table-weight-"]',
                        '[id^="laggards-top5-table-change-"]',
                        '[id^="latest-nav-value-"]',
                        '[id^="daily-change-value-"]',
                        '[id^="performance-return-"]',
                        '[id^="moving-average-status-"]',
                        '[id^="rsi-status-"]',
                        '[id^="volume-price-status-"]',
                        '[id^="benchmark-comparison-status-"]',
                        '[id^="tech-rating-value-"]',
                        '[id^="tech-rating-text-"]',
                        '[id^="holdings-concentration-value-"]',
                        '[id^="fundamental-rating-value-"]',
                        '[id^="fundamental-rating-text-"]',
                        '[id^="recommendation-rating-value-"]',
                        '[id^="recommendation-rating-text-"]'
                    ]
                },
                {
                    kind: 'chart',
                    selectors: [
                        '#performance-chart',
                        '#radar-chart',
                        '#scale-chart',
                        '#annual-chart',
                        '.kline-container-small[id^="kline-daily-"]',
                        '.kline-container-small[id^="kline-weekly-"]',
                        '[id^="holdings-chart-"]'
                    ]
                },
                {
                    kind: 'text',
                    selectors: [
                        '[id^="moving-average-desc-"]',
                        '[id^="rsi-desc-"]',
                        '[id^="volume-price-desc-"]',
                        '[id^="benchmark-comparison-desc-"]',
                        '[id^="strong-buy-card-overview-item-"]',
                        '[id^="watchlist-card-overview-item-"]',
                        '[id^="core-themes-card-overview-item-"]',
                        '[id^="report-card-text-"]',
                        '[id^="research-date-"]',
                        '.macro-item-content[id]',
                        '[id^="editorial-date-"]',
                        { selector: '[id^="aggressive-allocation-card-item-"]', allowChildren: true },
                        { selector: '[id^="moderate-allocation-card-item-"]', allowChildren: true },
                        { selector: '[id^="conservative-allocation-card-item-"]', allowChildren: true },
                        '#aggressive-allocation-card-strategy',
                        '#moderate-allocation-card-strategy',
                        '#conservative-allocation-card-strategy'
                    ]

                }

            ];

            let debugEnabled = queryDebugEnabled || window.localStorage.getItem(STORAGE_KEY) === '1';
            let hotspotsEnabled = queryHotspotsEnabled || window.localStorage.getItem(HOTSPOT_STORAGE_KEY) === '1';
            let focusPanelOpen = false;
            let currentTarget = null;
            let pinnedTarget = null;
            let toastTimer = null;
            let hotTargets = [];


            function makeDebugKey(value, fallback) {
                const normalized = String(value || '')
                    .toLowerCase()
                    .trim()
                    .replace(/[^a-z0-9]+/g, '-')
                    .replace(/^-+|-+$/g, '');
                return normalized || fallback;
            }

            const overlay = document.createElement('div');
            overlay.id = 'debug-highlight-overlay';
            overlay.className = 'debug-highlight-overlay';
            overlay.dataset.debugUi = 'true';

            const toolbar = document.createElement('div');
            toolbar.id = 'debug-toolbar';
            toolbar.className = 'debug-toolbar';
            toolbar.dataset.debugUi = 'true';

            const marketStrip = document.createElement('div');
            marketStrip.id = 'debug-market-strip';
            marketStrip.className = 'debug-market-strip';
            marketStrip.dataset.debugUi = 'true';

            marketTickerModules.forEach(function(module, moduleIndex) {
                const moduleKey = makeDebugKey(module.key || module.label, 'module-' + (moduleIndex + 1));
                const moduleElement = document.createElement('div');
                moduleElement.id = 'debug-market-module-' + moduleKey;
                moduleElement.className = 'debug-market-module';
                moduleElement.dataset.debugUi = 'true';

                const moduleLabel = document.createElement('span');
                moduleLabel.id = 'debug-market-module-label-' + moduleKey;
                moduleLabel.className = 'debug-market-module-label';
                moduleLabel.dataset.debugUi = 'true';
                moduleLabel.textContent = module.label;
                moduleElement.appendChild(moduleLabel);

                module.items.forEach(function(item, itemIndex) {
                    const itemKey = makeDebugKey(item.key || item.symbol, 'item-' + (itemIndex + 1));
                    const marketItem = document.createElement('div');
                    marketItem.id = 'debug-market-item-' + moduleKey + '-' + itemKey;
                    marketItem.className = 'debug-market-item';
                    marketItem.dataset.debugUi = 'true';

                    const symbol = document.createElement('span');
                    symbol.id = 'debug-market-symbol-' + moduleKey + '-' + itemKey;
                    symbol.className = 'debug-market-symbol';
                    symbol.dataset.debugUi = 'true';
                    symbol.textContent = item.symbol;

                    const value = document.createElement('span');
                    value.id = 'debug-market-value-' + moduleKey + '-' + itemKey;
                    value.className = 'debug-market-value';
                    value.dataset.debugUi = 'true';
                    value.textContent = item.value;

                    const change = document.createElement('span');
                    change.id = 'debug-market-change-' + moduleKey + '-' + itemKey;
                    change.className = 'debug-market-change ' + (item.direction === 'up' ? 'is-up' : 'is-down');
                    change.dataset.debugUi = 'true';
                    change.textContent = item.change;

                    marketItem.appendChild(symbol);
                    marketItem.appendChild(value);
                    marketItem.appendChild(change);
                    moduleElement.appendChild(marketItem);
                });

                marketStrip.appendChild(moduleElement);
            });

            function createToolButton(id, iconText) {
                const button = document.createElement('button');
                button.id = id;
                button.type = 'button';
                button.className = 'debug-tool-button';
                button.dataset.debugUi = 'true';

                const icon = document.createElement('span');
                icon.className = 'debug-tool-icon';
                icon.dataset.debugUi = 'true';
                icon.setAttribute('aria-hidden', 'true');
                icon.textContent = iconText;

                const tooltip = document.createElement('div');
                tooltip.className = 'debug-tool-tooltip';
                tooltip.dataset.debugUi = 'true';

                const tooltipTitle = document.createElement('div');
                tooltipTitle.className = 'debug-tool-tooltip-title';
                tooltipTitle.dataset.debugUi = 'true';

                const tooltipDesc = document.createElement('div');
                tooltipDesc.className = 'debug-tool-tooltip-desc';
                tooltipDesc.dataset.debugUi = 'true';

                tooltip.appendChild(tooltipTitle);
                tooltip.appendChild(tooltipDesc);
                button.appendChild(icon);
                button.appendChild(tooltip);
                return {
                    button: button,
                    icon: icon,
                    tooltipTitle: tooltipTitle,
                    tooltipDesc: tooltipDesc
                };
            }

            const toolbarButtons = document.createElement('div');

            toolbarButtons.id = 'debug-toolbar-buttons';
            toolbarButtons.className = 'debug-toolbar-buttons';
            toolbarButtons.dataset.debugUi = 'true';

            const visibilityTool = createToolButton('debug-visibility-toggle', '🔦');
            const hotspotTool = createToolButton('debug-hotspot-toggle', '🔥');
            const focusTool = createToolButton('debug-focus-toggle', '🔍');

            toolbarButtons.appendChild(visibilityTool.button);
            toolbarButtons.appendChild(hotspotTool.button);
            toolbarButtons.appendChild(focusTool.button);

            toolbar.appendChild(marketStrip);
            toolbar.appendChild(toolbarButtons);

            const focusPanel = document.createElement('div');
            focusPanel.id = 'debug-focus-panel';
            focusPanel.className = 'debug-focus-panel';
            focusPanel.dataset.debugUi = 'true';

            const focusPanelTitle = document.createElement('div');
            focusPanelTitle.className = 'debug-focus-panel-title';
            focusPanelTitle.dataset.debugUi = 'true';
            focusPanelTitle.textContent = '按 id 聚焦元素';

            const focusPanelHint = document.createElement('div');
            focusPanelHint.className = 'debug-focus-panel-hint';
            focusPanelHint.dataset.debugUi = 'true';
            focusPanelHint.textContent = '支持完整 id、前缀或片段搜索；定位后可用上一条 / 下一条逐个切换结果。';

            const focusForm = document.createElement('form');
            focusForm.id = 'debug-focus-form';
            focusForm.className = 'debug-focus-form';
            focusForm.dataset.debugUi = 'true';

            const focusInput = document.createElement('input');
            focusInput.id = 'debug-focus-input';
            focusInput.className = 'debug-focus-input';
            focusInput.dataset.debugUi = 'true';
            focusInput.type = 'text';
            focusInput.autocomplete = 'off';
            focusInput.spellcheck = false;
            focusInput.placeholder = '例如：strong-buy-card-overview-item-';
            focusInput.value = window.localStorage.getItem(FOCUS_QUERY_STORAGE_KEY) || '';

            const focusStatus = document.createElement('div');
            focusStatus.className = 'debug-focus-status';
            focusStatus.dataset.debugUi = 'true';

            const focusStatusSummary = document.createElement('div');
            focusStatusSummary.className = 'debug-focus-status-summary';
            focusStatusSummary.dataset.debugUi = 'true';

            const focusStatusCurrent = document.createElement('div');
            focusStatusCurrent.className = 'debug-focus-status-current';
            focusStatusCurrent.dataset.debugUi = 'true';

            const focusActions = document.createElement('div');
            focusActions.className = 'debug-focus-actions';
            focusActions.dataset.debugUi = 'true';

            const focusLocateButton = document.createElement('button');
            focusLocateButton.type = 'submit';
            focusLocateButton.className = 'debug-focus-action locate';
            focusLocateButton.dataset.debugUi = 'true';
            focusLocateButton.textContent = '搜索';

            const focusPrevButton = document.createElement('button');
            focusPrevButton.type = 'button';
            focusPrevButton.className = 'debug-focus-action nav';
            focusPrevButton.dataset.debugUi = 'true';
            focusPrevButton.textContent = '上一个';

            const focusNextButton = document.createElement('button');
            focusNextButton.type = 'button';
            focusNextButton.className = 'debug-focus-action nav';
            focusNextButton.dataset.debugUi = 'true';
            focusNextButton.textContent = '下一个';

            focusStatus.appendChild(focusStatusSummary);
            focusStatus.appendChild(focusStatusCurrent);
            focusActions.appendChild(focusLocateButton);
            focusActions.appendChild(focusPrevButton);
            focusActions.appendChild(focusNextButton);
            focusForm.appendChild(focusInput);
            focusForm.appendChild(focusStatus);
            focusForm.appendChild(focusActions);
            focusPanel.appendChild(focusPanelTitle);
            focusPanel.appendChild(focusPanelHint);
            focusPanel.appendChild(focusForm);


            const toast = document.createElement('div');
            toast.id = 'debug-toast';
            toast.className = 'debug-toast';
            toast.dataset.debugUi = 'true';


            function showToast(message) {
                toast.textContent = message;
                toast.classList.add('active');
                if (toastTimer) {
                    window.clearTimeout(toastTimer);
                }
                toastTimer = window.setTimeout(function() {
                    toast.classList.remove('active');
                }, 1800);
            }

            function normalizeFocusId(rawValue) {
                return String(rawValue || '').trim().replace(/^#/, '');
            }

            function setStoredFocusId(idValue) {
                const normalized = normalizeFocusId(idValue);
                if (normalized) {
                    window.localStorage.setItem(FOCUS_QUERY_STORAGE_KEY, normalized);
                } else {
                    window.localStorage.removeItem(FOCUS_QUERY_STORAGE_KEY);
                }
            }

            function getFocusMatchScore(idValue, normalizedQuery) {
                if (!normalizedQuery) {
                    return -1;
                }
                if (idValue === normalizedQuery) {
                    return 0;
                }
                if (idValue.indexOf(normalizedQuery) === 0) {
                    return 1;
                }
                if (idValue.indexOf(normalizedQuery) >= 0) {
                    return 2;
                }
                return -1;
            }

            function collectFocusMatches(rawQuery) {
                const normalizedQuery = normalizeFocusId(rawQuery);
                if (!normalizedQuery) {
                    return [];
                }
                return Array.from(document.querySelectorAll('[id]'))
                    .filter(function(element) {
                        return element
                            && element.id
                            && (!element.closest || !element.closest('[data-debug-ui="true"]'));
                    })
                    .map(function(element, index) {
                        return {
                            element: element,
                            score: getFocusMatchScore(element.id, normalizedQuery),
                            index: index
                        };
                    })
                    .filter(function(entry) {
                        return entry.score >= 0;
                    })
                    .sort(function(left, right) {
                        if (left.score !== right.score) {
                            return left.score - right.score;
                        }
                        return left.index - right.index;
                    })
                    .map(function(entry) {
                        return entry.element;
                    });
            }

            function syncFocusMatches(rawQuery, preferredTarget) {
                const normalizedQuery = normalizeFocusId(rawQuery);
                focusMatches = collectFocusMatches(normalizedQuery);
                if (!normalizedQuery || focusMatches.length === 0) {
                    focusMatchIndex = -1;
                    return normalizedQuery;
                }
                if (preferredTarget) {
                    const preferredIndex = focusMatches.indexOf(preferredTarget);
                    focusMatchIndex = preferredIndex >= 0 ? preferredIndex : 0;
                    return normalizedQuery;
                }
                if (focusMatchIndex < 0 || focusMatchIndex >= focusMatches.length) {
                    focusMatchIndex = 0;
                }
                return normalizedQuery;
            }

            function renderFocusStatus(rawQuery) {
                const normalizedQuery = normalizeFocusId(rawQuery);
                if (!normalizedQuery) {
                    focusStatusSummary.textContent = '尚未搜索';
                    focusStatusCurrent.textContent = '输入完整 id、前缀或片段后，会常驻显示匹配结果。';
                    focusLocateButton.disabled = false;
                    focusPrevButton.disabled = true;
                    focusNextButton.disabled = true;
                    return;
                }

                if (focusMatches.length === 0 || focusMatchIndex < 0) {
                    focusStatusSummary.textContent = '共匹配 0 条';
                    focusStatusCurrent.textContent = '未找到包含 “' + normalizedQuery + '” 的 id。';
                    focusLocateButton.disabled = false;
                    focusPrevButton.disabled = true;
                    focusNextButton.disabled = true;
                    return;
                }

                const currentMatch = focusMatches[focusMatchIndex];
                focusStatusSummary.textContent = '共匹配 ' + focusMatches.length + ' 条 · 当前 ' + (focusMatchIndex + 1) + '/' + focusMatches.length;
                focusStatusCurrent.textContent = currentMatch ? currentMatch.id : '结果不可用';
                focusLocateButton.disabled = false;
                focusPrevButton.disabled = focusMatchIndex <= 0;
                focusNextButton.disabled = focusMatchIndex >= focusMatches.length - 1;
            }

            function setFocusPanelOpen(nextValue, silent) {
                focusPanelOpen = !!nextValue;
                focusPanel.classList.toggle('active', focusPanelOpen);
                if (focusPanelOpen) {
                    renderToolbar();
                    renderFocusStatus(focusInput.value);
                    window.setTimeout(function() {
                        focusInput.focus();
                        focusInput.select();
                    }, 0);
                } else {
                    focusInput.blur();
                    clearFocusedTarget(true);
                }
                if (!silent) {
                    showToast(focusPanelOpen ? '按 id 聚焦已开启' : '按 id 聚焦已收起');
                }
            }

            function clearFocusedTarget(silent) {
                if (pinnedTarget) {
                    pinnedTarget.classList.remove('debug-focused-target');
                    pinnedTarget = null;
                }
                currentTarget = null;
                overlay.classList.remove('active');
                renderToolbar();
                renderFocusStatus(focusInput.value);
                if (!silent) {
                    showToast('已清除聚焦高亮');
                }
            }


            function setFocusedTarget(target) {
                if (pinnedTarget && pinnedTarget !== target) {
                    pinnedTarget.classList.remove('debug-focused-target');
                }
                pinnedTarget = target || null;
                if (pinnedTarget) {
                    pinnedTarget.classList.add('debug-focused-target');
                    updateHighlight(pinnedTarget);
                } else if (debugEnabled && currentTarget) {
                    updateHighlight(currentTarget);
                } else {
                    currentTarget = null;
                    overlay.classList.remove('active');
                }
                renderToolbar();
                renderFocusStatus(focusInput.value);
            }

            function getPanelIdForElement(element) {
                const panel = element && element.closest ? element.closest('.etf-panel') : null;
                if (!panel || !panel.id) {
                    return null;
                }
                return panel.id.replace(/^panel-/, '');
            }

            function waitForAnimationFrames(frameCount) {
                return new Promise(function(resolve) {
                    let remaining = Math.max(frameCount || 1, 1);
                    function step() {
                        remaining -= 1;
                        if (remaining <= 0) {
                            resolve();
                            return;
                        }
                        window.requestAnimationFrame(step);
                    }
                    window.requestAnimationFrame(step);
                });
            }

            function centerTargetInViewport(target) {
                const rect = target.getBoundingClientRect();
                const desiredTop = rect.top + window.scrollY - Math.max((window.innerHeight - rect.height) / 2, 24);
                const maxTop = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
                window.scrollTo({
                    top: Math.min(Math.max(desiredTop, 0), maxTop),
                    behavior: 'smooth'
                });
            }

            async function focusElementByQuery(rawQuery, requestedIndex) {
                const normalizedQuery = syncFocusMatches(rawQuery);
                setFocusPanelOpen(true, true);
                setStoredFocusId(normalizedQuery);
                focusInput.value = normalizedQuery;

                if (!normalizedQuery) {
                    clearFocusedTarget(true);
                    focusInput.focus();
                    renderFocusStatus('');
                    return;
                }

                if (focusMatches.length === 0) {
                    clearFocusedTarget(true);
                    focusInput.focus();
                    focusInput.select();
                    renderFocusStatus(normalizedQuery);
                    return;
                }

                focusMatchIndex = Math.min(Math.max(requestedIndex || 0, 0), focusMatches.length - 1);
                const target = focusMatches[focusMatchIndex];
                const targetPanelId = getPanelIdForElement(target);
                if (targetPanelId) {
                    switchPanel(targetPanelId);
                    await waitForAnimationFrames(2);
                } else {
                    await waitForAnimationFrames(1);
                }

                setFocusedTarget(target);
                centerTargetInViewport(target);
                renderFocusStatus(normalizedQuery);
            }


            function hideHighlight() {
                if (pinnedTarget) {
                    updateHighlight(pinnedTarget);
                    return;
                }
                currentTarget = null;
                overlay.classList.remove('active');
            }


            function clearHotTargets() {
                hotTargets.forEach(function(entry) {
                    entry.element.classList.remove('debug-hotspot-target');
                    entry.element.removeAttribute('data-debug-heat-kind');
                });
            }

            function collectHotTargets() {
                const found = [];
                const seen = new Set();

                hotTargetSelectorGroups.forEach(function(group) {
                    group.selectors.forEach(function(selectorEntry) {
                        const selector = typeof selectorEntry === 'string' ? selectorEntry : selectorEntry.selector;
                        const allowChildren = !!(selectorEntry && typeof selectorEntry === 'object' && selectorEntry.allowChildren);
                        if (!selector) {
                            return;
                        }
                        document.querySelectorAll(selector).forEach(function(element) {

                            if (!element || !element.id || seen.has(element.id)) {
                                return;
                            }
                            if (element.closest('[data-debug-ui="true"]')) {
                                return;
                            }
                            if (!allowChildren && element.querySelector('[id]')) {
                                return;
                            }

                            seen.add(element.id);
                            found.push({ element: element, kind: group.kind });
                        });
                    });
                });

                return found.filter(function(target, index, list) {
                    return !list.some(function(other, otherIndex) {
                        return otherIndex !== index && target.element.contains(other.element);
                    });
                });
            }

            function applyHotspotState() {
                clearHotTargets();
                if (!hotspotsEnabled) {
                    return;
                }
                hotTargets.forEach(function(entry) {
                    entry.element.classList.add('debug-hotspot-target');
                    entry.element.setAttribute('data-debug-heat-kind', entry.kind);
                });
            }

            function refreshHotTargets() {
                clearHotTargets();
                hotTargets = collectHotTargets();
                applyHotspotState();
            }

            function updateToolButton(tool, config) {
                tool.button.disabled = false;
                tool.icon.textContent = config.icon;
                tool.button.classList.toggle('is-on', !!config.isOn);
                tool.button.classList.toggle('is-hot-on', !!config.isHot);
                tool.button.classList.toggle('is-focus-on', !!config.isFocus);
                tool.button.classList.toggle('is-off', !!config.isOff);
                tool.button.classList.toggle('is-unavailable', !!config.isUnavailable);
                tool.button.setAttribute('aria-pressed', config.pressed ? 'true' : 'false');
                tool.button.setAttribute('aria-disabled', config.isUnavailable ? 'true' : 'false');
                tool.button.setAttribute('aria-label', config.ariaLabel);
                tool.tooltipTitle.textContent = config.tooltipTitle;
                if (config.tooltipDescHtml) {
                    tool.tooltipDesc.innerHTML = config.tooltipDescHtml;
                } else {
                    tool.tooltipDesc.textContent = config.tooltipDesc;
                }
            }


            function renderToolbar() {
                updateToolButton(visibilityTool, {
                    icon: '🔦',
                    isOn: debugEnabled,
                    isHot: false,
                    isFocus: false,
                    isOff: !debugEnabled,
                    isUnavailable: false,
                    pressed: debugEnabled,
                    ariaLabel: debugEnabled ? '显形模式已开启' : '显形模式已关闭',
                    tooltipTitle: debugEnabled ? '显形模式：开启' : '显形模式：关闭',
                    tooltipDescHtml: debugEnabled
                        ? 'Alt 点击页面元素即可复制 id；<span class="debug-tooltip-legend focus">蓝色</span>框表示当前定位框。'
                        : '点击开启后，Alt 点击页面元素即可复制 id；<span class="debug-tooltip-legend focus">蓝色</span>框会跟随当前定位。'
                });

                const hasHotTargets = hotTargets.length > 0;
                updateToolButton(hotspotTool, {
                    icon: '🔥',
                    isOn: false,
                    isHot: hasHotTargets && hotspotsEnabled,
                    isFocus: false,
                    isOff: hasHotTargets && !hotspotsEnabled,
                    isUnavailable: !hasHotTargets,
                    pressed: hasHotTargets && hotspotsEnabled,
                    ariaLabel: !hasHotTargets ? '热区雷达当前不可用' : (hotspotsEnabled ? '热区雷达已开启' : '热区雷达已关闭'),
                    tooltipTitle: !hasHotTargets ? '热区雷达：暂无' : (hotspotsEnabled ? '热区雷达：开启' : '热区雷达：关闭'),
                    tooltipDescHtml: !hasHotTargets
                        ? '当前页还没有可加框的热区节点。<br><span class="debug-tooltip-legend metric">黄色</span>=指标　<span class="debug-tooltip-legend chart">橙色</span>=图表　<span class="debug-tooltip-legend text">粉色</span>=文本'
                        : ((hotspotsEnabled ? ('正在高亮 ' + hotTargets.length + ' 个热区节点。') : ('点击后高亮当前页 ' + hotTargets.length + ' 个热区节点。')) + '<br><span class="debug-tooltip-legend metric">黄色</span>=指标　<span class="debug-tooltip-legend chart">橙色</span>=图表　<span class="debug-tooltip-legend text">粉色</span>=文本')
                });

                const focusActive = focusPanelOpen || !!pinnedTarget;
                const focusLocked = !!pinnedTarget && !focusPanelOpen;
                updateToolButton(focusTool, {
                    icon: '🔍',
                    isOn: false,
                    isHot: false,
                    isFocus: focusActive,
                    isOff: !focusActive,
                    isUnavailable: false,
                    pressed: focusActive,
                    ariaLabel: focusLocked ? '寻址器已锁定结果' : (focusPanelOpen ? '寻址器已打开' : '寻址器已关闭'),
                    tooltipTitle: focusLocked ? '寻址器：已锁定' : (focusPanelOpen ? '寻址器：打开' : '寻址器：关闭'),
                    tooltipDesc: focusLocked ? '已有目标被高亮锁定，再点一次可回到搜索面板。' : (focusPanelOpen ? '输入 id、前缀或片段，逐条定位结果。' : '点击打开搜索面板，按 id 寻找页面元素。')
                });
            }



            function setDebugEnabled(nextValue, silent) {
                debugEnabled = !!nextValue;
                if (debugEnabled) {
                    window.localStorage.setItem(STORAGE_KEY, '1');
                } else {
                    window.localStorage.removeItem(STORAGE_KEY);
                    hideHighlight();
                }
                renderToolbar();
                if (!silent) {
                    showToast(debugEnabled ? '定位调试已开启' : '定位调试已关闭');
                }
            }

            function setHotspotsEnabled(nextValue, silent) {
                if (nextValue && hotTargets.length === 0) {
                    hotspotsEnabled = false;
                    window.localStorage.removeItem(HOTSPOT_STORAGE_KEY);
                    renderToolbar();
                    if (!silent) {
                        showToast('当前页没有可用的热区节点');
                    }
                    return;
                }

                hotspotsEnabled = !!nextValue;
                if (hotspotsEnabled) {
                    window.localStorage.setItem(HOTSPOT_STORAGE_KEY, '1');
                } else {
                    window.localStorage.removeItem(HOTSPOT_STORAGE_KEY);
                }
                applyHotspotState();
                renderToolbar();
                if (!silent) {
                    showToast(hotspotsEnabled ? ('日更热区已开启（' + hotTargets.length + ' 个节点）') : '日更热区已关闭');
                }
            }

            function findNearestIdElement(startElement) {
                let current = startElement;
                while (current && current !== document.body) {
                    if (current.dataset && current.dataset.debugUi === 'true') {
                        return null;
                    }
                    if (current.id) {
                        return current;
                    }
                    current = current.parentElement;
                }
                return null;
            }

            function updateHighlight(target) {
                const canShow = !!target && (debugEnabled || target === pinnedTarget);
                if (!canShow) {
                    currentTarget = null;
                    overlay.classList.remove('active');
                    return;
                }

                const rect = target.getBoundingClientRect();
                currentTarget = target;
                overlay.style.left = rect.left + 'px';
                overlay.style.top = rect.top + 'px';
                overlay.style.width = rect.width + 'px';
                overlay.style.height = rect.height + 'px';
                overlay.classList.add('active');
            }


            async function copyText(text) {
                const normalizedText = String(text || '');
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    try {
                        await navigator.clipboard.writeText(normalizedText);
                        return;
                    } catch (error) {
                        console.warn('[debug-mode] clipboard api rejected, fallback to execCommand', error);
                    }
                }

                const temp = document.createElement('textarea');
                temp.value = normalizedText;
                temp.setAttribute('readonly', 'readonly');
                temp.style.position = 'absolute';
                temp.style.left = '-9999px';
                document.body.appendChild(temp);
                temp.focus();
                temp.select();
                temp.setSelectionRange(0, temp.value.length);
                const copied = document.execCommand('copy');
                document.body.removeChild(temp);
                if (!copied) {
                    throw new Error('Copy command was rejected');
                }
            }


            document.addEventListener('DOMContentLoaded', function() {
                document.body.appendChild(overlay);
                document.body.appendChild(toolbar);
                document.body.appendChild(focusPanel);
                document.body.appendChild(toast);
                refreshHotTargets();
                setDebugEnabled(debugEnabled, true);
                setHotspotsEnabled(hotspotsEnabled, true);
                syncFocusMatches(focusInput.value);
                renderToolbar();
                renderFocusStatus(focusInput.value);
            });

            visibilityTool.button.addEventListener('click', function(event) {
                event.preventDefault();
                event.stopPropagation();
                setDebugEnabled(!debugEnabled, false);
            });

            hotspotTool.button.addEventListener('click', function(event) {
                event.preventDefault();
                event.stopPropagation();
                setHotspotsEnabled(!hotspotsEnabled, false);
            });

            focusTool.button.addEventListener('click', function(event) {
                event.preventDefault();
                event.stopPropagation();
                setFocusPanelOpen(!focusPanelOpen, false);
            });

            focusInput.addEventListener('input', function() {
                syncFocusMatches(focusInput.value);
                renderFocusStatus(focusInput.value);
            });

            focusForm.addEventListener('submit', async function(event) {
                event.preventDefault();
                await focusElementByQuery(focusInput.value, 0);
            });

            focusPrevButton.addEventListener('click', async function(event) {
                event.preventDefault();
                if (focusMatchIndex <= 0) {
                    return;
                }
                await focusElementByQuery(focusInput.value, focusMatchIndex - 1);
            });

            focusNextButton.addEventListener('click', async function(event) {
                event.preventDefault();
                if (focusMatchIndex < 0 || focusMatchIndex >= focusMatches.length - 1) {
                    return;
                }
                await focusElementByQuery(focusInput.value, focusMatchIndex + 1);
            });



            document.addEventListener('keydown', function(event) {
                if (event.key === 'Escape' && focusPanelOpen) {
                    event.preventDefault();
                    setFocusPanelOpen(false, false);
                    return;
                }
                if (event.ctrlKey && event.altKey && (event.key === 'd' || event.key === 'D')) {
                    event.preventDefault();
                    setDebugEnabled(!debugEnabled, false);
                    return;
                }
                if (event.ctrlKey && event.altKey && (event.key === 'h' || event.key === 'H')) {
                    event.preventDefault();
                    setHotspotsEnabled(!hotspotsEnabled, false);
                    return;
                }
                if (event.ctrlKey && event.altKey && (event.key === 'f' || event.key === 'F')) {
                    event.preventDefault();
                    setFocusPanelOpen(!focusPanelOpen, false);
                }
            });


            document.addEventListener('mousemove', function(event) {
                if (!debugEnabled || pinnedTarget) {
                    return;
                }
                const target = findNearestIdElement(event.target);
                if (!target) {
                    hideHighlight();
                    return;
                }
                if (currentTarget !== target) {
                    updateHighlight(target);
                }
            });

            window.addEventListener('scroll', function() {
                const trackedTarget = pinnedTarget || (debugEnabled ? currentTarget : null);
                if (trackedTarget) {
                    updateHighlight(trackedTarget);
                }
            }, true);

            window.addEventListener('resize', function() {
                const trackedTarget = pinnedTarget || (debugEnabled ? currentTarget : null);
                if (trackedTarget) {
                    updateHighlight(trackedTarget);
                }
            });

            document.addEventListener('click', async function(event) {
                if (!debugEnabled || !event.altKey) {
                    return;
                }

                if (event.target && event.target.closest && event.target.closest('[data-debug-ui="true"]')) {
                    return;
                }

                const target = findNearestIdElement(event.target);
                if (!target) {
                    showToast('当前区域附近没有可复制的 id');
                    return;
                }

                event.preventDefault();
                event.stopPropagation();

                try {
                    await copyText(target.id);
                    // BUG-016：复制成功后只持久化最近 id 到 localStorage（供下次打开放大镜时预填），
                    // 不再直接写 focusInput.value / setFocusedTarget —— 那是放大镜自己的事，
                    // 手电筒 Alt+click 复制应保持"复制完毕、不干预其他 UI"的纯粹语义。
                    setStoredFocusId(target.id);
                    showToast('已复制 id：' + target.id);
                } catch (error) {
                    showToast('复制失败，请重试');
                    console.error('[debug-mode] copy failed', error);
                }
            }, true);

        })();
