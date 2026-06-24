/* ============================================================
 * report-main.js — ETF 报告主业务（9 个 ECharts + 消费 runtime_payload）
 * 源出处：index.html 原第 837-13031 行（REQ-146 抽离）
 * 依赖：
 *   - window.__ETF_REPORT_RUNTIME__（由 assets/js/runtime_payload.js 注入）
 *   - window.__etfChartLifecycle（由 chart-lifecycle.js 注入）
 * 规则：业务逻辑与运行时数据分离，运行时数据只从 runtime_payload.js 读取
 * ============================================================ */

        // K线数据（包含日线、周线、基准指数）
        const externalRuntimePayload = window.__ETF_REPORT_RUNTIME__ || {};
        const klineData = externalRuntimePayload.klineData || {};
        // 实时行情数据（由 update_report.py 注入）
        const realtimeData = externalRuntimePayload.realtimeData || {};

        function showRuntimeDataError(message) {
            const panel = document.getElementById('panel-overview');
            if (!panel) return;
            const warning = document.createElement('section');
            warning.className = 'panel-section';
            warning.style.borderColor = 'rgba(239,68,68,0.35)';
            warning.innerHTML = '<h2 style="font-size:15px;color:#e0e0e0;margin:0 0 8px;">报告运行时数据不可用</h2>'
                + '<p style="font-size:13px;color:#94a3b8;margin:0;">' + message + '</p>';
            panel.insertBefore(warning, panel.firstChild);
        }

        if (!externalRuntimePayload.klineData || !Object.keys(externalRuntimePayload.klineData).length) {
            showRuntimeDataError('runtime_payload.js 缺失或未生成有效 K 线数据，请重新运行 update_report.py。');
        }

        const ETF_CODES = Object.keys(klineData);


        function toNumber(value) {
            const numeric = Number(value);
            return Number.isFinite(numeric) ? numeric : null;
        }

        function clampScore(value) {
            return Math.max(1, Math.min(5, value));
        }

        function roundValue(value, digits = 2) {
            if (!Number.isFinite(value)) return null;
            return Number(value.toFixed(digits));
        }

        function getAverage(values) {
            const valid = (values || []).map(toNumber).filter(value => value !== null);
            if (!valid.length) return null;
            return valid.reduce((sum, value) => sum + value, 0) / valid.length;
        }

        function getKlineEntry(code) {
            return klineData[code] || {};
        }

        function getRealtimeEntry(code) {
            return realtimeData[code] || {};
        }

        function getCloseSeries(klineList) {
            return (klineList || [])
                .map(item => Array.isArray(item) ? toNumber(item[1]) : null)
                .filter(value => value !== null);
        }

        function getDailyCloseSeries(code) {
            const series = getCloseSeries(getKlineEntry(code).daily && getKlineEntry(code).daily.kline);
            const livePrice = toNumber(getRealtimeEntry(code).etf_price);
            if (series.length && livePrice !== null && livePrice > 0) {
                series[series.length - 1] = livePrice;
            }
            return series;
        }

        function getWeeklyCloseSeries(code) {
            return getCloseSeries(getKlineEntry(code).weekly && getKlineEntry(code).weekly.kline);
        }

        function getBenchmarkCloses(code) {
            return (getKlineEntry(code).benchmark && getKlineEntry(code).benchmark.closes) || [];
        }

        function getReturnFromSeries(series, lookbackPoints) {
            if (!Array.isArray(series) || series.length < 2) return null;
            const endValue = toNumber(series[series.length - 1]);
            if (endValue === null) return null;
            const safeLookback = Math.max(1, Math.min(lookbackPoints, series.length - 1));
            const startValue = toNumber(series[series.length - 1 - safeLookback]);
            if (startValue === null || startValue === 0) return null;
            return ((endValue - startValue) / startValue) * 100;
        }

        function getPerformanceMetrics(code) {
            const dailyCloses = getDailyCloseSeries(code);
            const weeklyCloses = getWeeklyCloseSeries(code);
            return {
                oneMonth: getReturnFromSeries(dailyCloses, 20),
                threeMonth: getReturnFromSeries(dailyCloses, 59),
                sixMonth: getReturnFromSeries(weeklyCloses, 26),
                oneYear: getReturnFromSeries(weeklyCloses, 51)
            };
        }

        function formatPercent(value, withSign = true) {
            const numeric = toNumber(value);
            if (numeric === null) return '--';
            if (numeric > 0) return `${withSign ? '+' : ''}${numeric.toFixed(2)}%`;
            if (numeric < 0) return `${numeric.toFixed(2)}%`;
            return '0.00%';
        }

        function formatPrice(value) {
            const numeric = toNumber(value);
            if (numeric === null) return '--';
            const digits = numeric >= 100 ? 2 : 4;
            return `${numeric.toFixed(digits)}元`;
        }

        function getTrendClass(value) {
            const numeric = toNumber(value);
            if (numeric === null) return 'text-amber';
            if (numeric > 0) return 'text-green';
            if (numeric < 0) return 'text-red';
            return 'text-amber';
        }

        function parseStarScore(text) {
            const filled = ((text || '').match(/★/g) || []).length;
            return filled || 3;
        }

        function scoreToTextStars(score) {
            const rounded = Math.max(1, Math.min(5, Math.round(score)));
            return '★'.repeat(rounded) + '☆'.repeat(5 - rounded);
        }

        function scoreToOverviewStars(score) {
            const rounded = Math.max(1, Math.min(5, Math.round(score)));
            const empty = 5 - rounded;
            return `<span class="filled">${'★'.repeat(rounded)}</span>${empty > 0 ? `<span class="empty">${'★'.repeat(empty)}</span>` : ''}`;
        }

        function getCurrentDisplayPrice(code) {
            const dailyEntry = getKlineEntry(code).daily || {};
            const latestClose = toNumber(dailyEntry.latest_close);
            if (latestClose !== null) return latestClose;
            const dailyCloses = getDailyCloseSeries(code);
            return dailyCloses.length ? dailyCloses[dailyCloses.length - 1] : null;
        }

        function getDailyChange(code) {
            const dailyEntry = getKlineEntry(code).daily || {};
            const latestChange = toNumber(dailyEntry.latest_change);
            if (latestChange !== null) return latestChange;
            return getReturnFromSeries(getDailyCloseSeries(code), 1);
        }


        function getHoldingConcentration(code) {
            const ratio = toNumber(getRealtimeEntry(code).total_ratio);
            if (ratio !== null && ratio > 0) return ratio;
            const holdings = (getRealtimeEntry(code).holdings || [])
                .map(item => toNumber(item.ratio))
                .filter(value => value !== null);
            if (holdings.length) {
                return roundValue(holdings.reduce((sum, value) => sum + value, 0), 2);
            }
            const existing = document.getElementById('holdings-concentration-value-' + code);
            const match = existing && existing.textContent ? existing.textContent.match(/-?\d+(\.\d+)?/) : null;
            return match ? Number(match[0]) : null;
        }


        function getFundSizeValue(code) {
            const node = document.getElementById('fund-size-value-' + code);
            const match = node && node.textContent ? node.textContent.match(/-?\d+(\.\d+)?/) : null;
            return match ? Number(match[0]) : 0;
        }

        function calculateRSI(closes, period = 14) {
            if (!Array.isArray(closes) || closes.length <= period) return null;
            let gains = 0;
            let losses = 0;
            for (let i = closes.length - period; i < closes.length; i++) {
                const delta = closes[i] - closes[i - 1];
                if (delta > 0) {
                    gains += delta;
                } else {
                    losses -= delta;
                }
            }
            if (losses === 0) return 100;
            const rs = (gains / period) / (losses / period);
            return 100 - (100 / (1 + rs));
        }

        function buildMovingAverageSignal(weeklyCloses) {
            const latest = weeklyCloses.length ? weeklyCloses[weeklyCloses.length - 1] : null;
            const ma5 = getAverage(weeklyCloses.slice(-5));
            const ma20 = getAverage(weeklyCloses.slice(-20));
            if (latest === null || ma5 === null || ma20 === null || ma20 === 0) {
                return { tone: 'neutral', text: '数据不足', desc: '周线样本不足，暂时沿用静态分析。', score: 3 };
            }
            const spread = ((ma5 - ma20) / ma20) * 100;
            if (latest > ma5 && ma5 > ma20 && spread >= 1.5) {
                return {
                    tone: 'bullish',
                    text: spread >= 4 ? '强势上行' : '震荡上行',
                    desc: '周线收盘价位于 MA5 与 MA20 上方，趋势保持偏强。',
                    score: spread >= 4 ? 5 : 4.2
                };
            }
            if (latest < ma5 && ma5 < ma20 && spread <= -1.5) {
                return {
                    tone: 'bearish',
                    text: Math.abs(spread) >= 4 ? '弱势下跌' : '高位回落',
                    desc: '周线位于 MA5 与 MA20 下方，趋势结构偏弱。',
                    score: Math.abs(spread) >= 4 ? 1.4 : 2.0
                };
            }
            if (latest >= ma20) {
                return {
                    tone: 'neutral',
                    text: '区间震荡',
                    desc: '周线仍在中期均线之上，但短线方向尚未重新加速。',
                    score: 3.4
                };
            }
            return {
                tone: 'neutral',
                text: '震荡整理',
                desc: '周线围绕中期均线拉锯，趋势信号尚不明确。',
                score: 2.8
            };
        }

        function buildRSISignal(dailyCloses) {
            const rsi = calculateRSI(dailyCloses, 14);
            if (rsi === null) {
                return { tone: 'neutral', text: '数据不足', desc: 'RSI 样本不足，暂不生成结论。', score: 3 };
            }
            const rounded = Math.round(rsi);
            if (rsi >= 70) {
                return { tone: 'bearish', text: `超买（${rounded}）`, desc: '短线动能偏热，需注意波动回撤。', score: 2.0 };
            }
            if (rsi >= 60) {
                return { tone: 'bullish', text: `强势（${rounded}）`, desc: '动能维持在强势区间，趋势延续概率较高。', score: 4.5 };
            }
            if (rsi <= 30) {
                return { tone: 'neutral', text: `超卖（${rounded}）`, desc: '短线进入超卖区，波动放大但存在修复机会。', score: 2.4 };
            }
            if (rsi <= 40) {
                return { tone: 'bearish', text: `偏弱（${rounded}）`, desc: '动能仍偏弱，需等待情绪与量能修复。', score: 2.6 };
            }
            return { tone: 'neutral', text: `中性（${rounded}）`, desc: 'RSI 位于中性区间，市场等待新的方向选择。', score: 3.2 };
        }

        function buildVolumeSignal(code) {
            const dailyData = getKlineEntry(code).daily || {};
            const klineList = dailyData.kline || [];
            const volumes = (dailyData.volumes || []).map(toNumber).filter(value => value !== null);
            if (!klineList.length || !volumes.length) {
                return { tone: 'neutral', text: '数据不足', desc: '量价样本不足，暂不生成结论。', score: 3 };
            }
            const latestKline = klineList[klineList.length - 1];
            const latestVolume = volumes[volumes.length - 1];
            const avgVolume = getAverage(volumes.slice(-5));
            const dayChange = toNumber(latestKline[1]) - toNumber(latestKline[0]);
            const volumeRatio = avgVolume ? latestVolume / avgVolume : 1;
            if (dayChange >= 0 && volumeRatio >= 1.15) {
                return { tone: 'bullish', text: '放量上涨', desc: '价格上涨并伴随明显放量，短线资金参与度提升。', score: 4.6 };
            }
            if (dayChange >= 0 && volumeRatio <= 0.85) {
                return { tone: 'bullish', text: '缩量上涨', desc: '价格延续走强，但增量资金尚未明显放大。', score: 3.8 };
            }
            if (dayChange < 0 && volumeRatio >= 1.15) {
                return { tone: 'bearish', text: '放量下跌', desc: '价格回落且成交放大，短线抛压偏重。', score: 1.8 };
            }
            if (dayChange < 0 && volumeRatio <= 0.85) {
                return { tone: 'neutral', text: '缩量回调', desc: '回调过程中量能收缩，更多体现为阶段性整理。', score: 2.8 };
            }
            if (dayChange >= 0) {
                return { tone: 'bullish', text: '温和放量', desc: '价格与成交量同步改善，但尚未形成强突破。', score: 3.9 };
            }
            return { tone: 'bearish', text: '震荡回落', desc: '价格小幅走弱，量能未见明显放大，仍需观察。', score: 2.4 };
        }

        function buildBenchmarkSignal(code, performance) {
            const benchmarkThreeMonth = getReturnFromSeries(getBenchmarkCloses(code), 59);
            const etfThreeMonth = performance.threeMonth;
            if (benchmarkThreeMonth === null || etfThreeMonth === null) {
                return { tone: 'neutral', text: '暂无对比', desc: '缺少足够基准样本，暂不输出相对强弱。', score: 3 };
            }
            const diff = etfThreeMonth - benchmarkThreeMonth;
            if (diff >= 10) {
                return { tone: 'bullish', text: '显著跑赢大盘', desc: `近3月相对基准领先 ${diff.toFixed(2)}pct，强势明显。`, score: 5 };
            }
            if (diff >= 3) {
                return { tone: 'bullish', text: '跑赢大盘', desc: `近3月相对基准领先 ${diff.toFixed(2)}pct，强于市场平均。`, score: 4.1 };
            }
            if (diff <= -10) {
                return { tone: 'bearish', text: '显著落后基准', desc: `近3月落后基准 ${Math.abs(diff).toFixed(2)}pct，配置性价比偏弱。`, score: 1.5 };
            }
            if (diff <= -3) {
                return { tone: 'bearish', text: '跑输大盘', desc: `近3月落后基准 ${Math.abs(diff).toFixed(2)}pct，需等待修复信号。`, score: 2.2 };
            }
            return { tone: 'neutral', text: '基本同步', desc: `近3月与基准差值 ${diff.toFixed(2)}pct，整体维持同步。`, score: 3.1 };
        }

        function getHoldingSentimentScore(code) {
            const holdings = getRealtimeEntry(code).holdings || [];
            if (!holdings.length) return 3;
            let totalWeight = 0;
            let weightedNet = 0;
            holdings.forEach(item => {
                const ratio = toNumber(item.ratio) || 0;
                const change = toNumber(item.change) || 0;
                totalWeight += ratio;
                weightedNet += ratio * Math.sign(change);
            });
            if (!totalWeight) return 3;
            return clampScore(3 + (weightedNet / totalWeight) * 2);
        }

        function getRatingLevel(score) {
            if (score >= 4.2) return 'high';
            if (score >= 3.2) return 'medium';
            return 'low';
        }

        function getRecommendationMeta(score, threeMonthReturn) {
            if (score >= 4.2) {
                return {
                    level: 'high',
                    text: '强烈推荐',
                    badgeClass: 'strong-buy',
                    badgeText: threeMonthReturn !== null && threeMonthReturn >= 10 ? '🚀 强烈推荐 - 核心配置' : '🚀 强烈推荐 - 积极配置'
                };
            }
            if (score >= 3.4) {
                return {
                    level: 'medium',
                    text: '推荐',
                    badgeClass: 'buy',
                    badgeText: '📈 推荐 - 适当配置'
                };
            }
            return {
                level: 'medium',
                text: '观望',
                badgeClass: 'hold',
                badgeText: '⏸️ 观望 - 等待趋势明朗'
            };
        }

        function buildRuntimeSnapshot(code) {
            const performance = getPerformanceMetrics(code);
            const dailyCloses = getDailyCloseSeries(code);
            const weeklyCloses = getWeeklyCloseSeries(code);
            const movingAverage = buildMovingAverageSignal(weeklyCloses);
            const rsi = buildRSISignal(dailyCloses);
            const volumePrice = buildVolumeSignal(code);
            const benchmarkComparison = buildBenchmarkSignal(code, performance);
            const techScore = clampScore(getAverage([movingAverage.score, rsi.score, volumePrice.score, benchmarkComparison.score]) || 3);
            const fundamentalText = document.getElementById('fundamental-rating-value-' + code);
            const fundamentalScore = clampScore(parseStarScore(fundamentalText ? fundamentalText.textContent : '★★★☆☆'));
            const recommendationScore = clampScore(techScore * 0.6 + fundamentalScore * 0.4);
            const recommendation = getRecommendationMeta(recommendationScore, performance.threeMonth);
            return {
                code,
                label: (() => {
                    const node = document.getElementById('fund-type-value-' + code);
                    return node && node.textContent.trim() ? node.textContent.trim() : ((getKlineEntry(code) && getKlineEntry(code).name) || code);
                })(),
                displayPrice: getCurrentDisplayPrice(code),
                priceLabel: toNumber(getRealtimeEntry(code).etf_price) !== null ? '最新价格' : '最新收盘价',
                dailyChange: getDailyChange(code),
                performance,
                scale: getFundSizeValue(code),
                holdingConcentration: getHoldingConcentration(code),
                holdings: (getRealtimeEntry(code).holdings || []).slice(),
                technical: {
                    movingAverage,
                    rsi,
                    volumePrice,
                    benchmarkComparison,
                    score: techScore,
                    level: getRatingLevel(techScore),
                    text: techScore >= 4.2 ? '看好' : techScore >= 3.2 ? '中性' : '谨慎'
                },
                fundamentalScore,
                recommendationScore,
                recommendation,
                radarValues: [
                    roundValue(techScore, 1) || 3,
                    roundValue(fundamentalScore, 1) || 3,
                    roundValue(movingAverage.score, 1) || 3,
                    roundValue(getHoldingSentimentScore(code), 1) || 3,
                    roundValue(benchmarkComparison.score, 1) || 3
                ]
            };
        }

        function buildSnapshots() {
            return ETF_CODES.map(buildRuntimeSnapshot);
        }

        function setNodeText(id, text) {
            const node = document.getElementById(id);
            if (node) node.textContent = text;
        }

        function syncNodeStateClass(node, baseClasses, stateClasses, nextStateClass) {
            if (!node) return;
            const baseList = Array.isArray(baseClasses) ? baseClasses : [baseClasses];
            const stateList = Array.isArray(stateClasses) ? stateClasses : [stateClasses];
            stateList.filter(Boolean).forEach(className => node.classList.remove(className));
            baseList.filter(Boolean).forEach(className => node.classList.add(className));
            if (nextStateClass) {
                node.classList.add(nextStateClass);
            }
        }

        function applyTechSignal(code, prefix, signal) {
            const statusNode = document.getElementById(prefix + '-status-' + code);
            const descNode = document.getElementById(prefix + '-desc-' + code);
            if (statusNode) {
                statusNode.textContent = signal.text;
                syncNodeStateClass(statusNode, 'tech-status', ['bullish', 'neutral', 'bearish'], signal.tone);
            }

            if (descNode) {
                descNode.textContent = signal.desc;
            }
        }


        function renderOverviewCard(snapshot) {
            const card = document.getElementById('overview-card-' + snapshot.code);
            if (!card) return;
            const changeNode = card.querySelector('.etf-change');
            const starsNode = card.querySelector('.rating-stars');
            const badgeNode = card.querySelector('.recommendation-badge');
            const tone = snapshot.recommendationScore >= 4.2 ? 'bullish' : snapshot.recommendationScore >= 3.2 ? 'neutral' : 'bearish';
            card.classList.remove('bullish', 'neutral', 'bearish');
            card.classList.add(tone);
            if (changeNode) {
                changeNode.textContent = formatPercent(snapshot.performance.threeMonth);
                changeNode.classList.remove('positive', 'negative');
                if ((snapshot.performance.threeMonth || 0) > 0) {
                    changeNode.classList.add('positive');
                } else if ((snapshot.performance.threeMonth || 0) < 0) {
                    changeNode.classList.add('negative');
                }
            }
            if (starsNode) {
                starsNode.innerHTML = scoreToOverviewStars(snapshot.recommendationScore);
            }
            if (badgeNode) {
                syncNodeStateClass(badgeNode, ['recommendation-badge', 'badge-sm'], ['strong-buy', 'buy', 'hold'], snapshot.recommendation.badgeClass);
                badgeNode.textContent = snapshot.recommendation.badgeText;
            }

        }

        function compareSnapshotPriority(left, right) {
            const scoreDelta = (right.recommendationScore || 0) - (left.recommendationScore || 0);
            if (scoreDelta !== 0) return scoreDelta;
            const annualDelta = (right.performance.oneYear || 0) - (left.performance.oneYear || 0);
            if (annualDelta !== 0) return annualDelta;
            return (right.performance.threeMonth || 0) - (left.performance.threeMonth || 0);
        }

        function renderOverviewHighlightList(listPrefix, snapshots, highlightClass, emptyText) {
            for (let index = 1; index <= 3; index += 1) {
                const item = document.getElementById(listPrefix + '-item-' + index);
                if (!item) continue;
                const snapshot = snapshots[index - 1];
                if (!snapshot) {
                    item.textContent = emptyText;
                    continue;
                }
                const displayName = `${snapshot.code} ${snapshot.displayName}`;
                const oneYearText = formatPercent(snapshot.performance.oneYear);
                item.innerHTML = `<span class="${highlightClass}">${displayName}</span>：${snapshot.recommendation.text}，近1年涨幅${oneYearText}，技术面${snapshot.technical.text}`;
            }
        }

        function buildCoreThemeEntries(snapshots) {
            const snapshotMap = new Map(snapshots.map(snapshot => [snapshot.code, snapshot]));
            const themeDefinitions = [
                { label: '科技成长', description: 'AI算力、光模块、新能源电池', codes: ['515880', '159755'] },
                { label: '资源周期', description: '有色金属、贵金属', codes: ['512400'] },
                { label: '创新医药', description: '港股创新药、创新平台', codes: ['513120'] },
                { label: '金融修复', description: '券商、保险、风险偏好修复', codes: ['512070'] },
                { label: '周期修复', description: '生猪养殖、饲料龙头', codes: ['159865'] }
            ];

            return themeDefinitions
                .map(theme => {
                    const members = theme.codes
                        .map(code => snapshotMap.get(code))
                        .filter(Boolean)
                        .sort(compareSnapshotPriority);
                    if (!members.length) return null;
                    const leader = members[0];
                    return {
                        ...theme,
                        leader,
                        score: leader.recommendationScore || 0,
                        oneYear: leader.performance.oneYear || 0,
                        threeMonth: leader.performance.threeMonth || 0
                    };
                })
                .filter(Boolean)
                .sort((left, right) => compareSnapshotPriority(left.leader, right.leader))
                .slice(0, 3);
        }

        function renderCoreThemeHighlights(snapshots) {
            const themeEntries = buildCoreThemeEntries(snapshots);
            for (let index = 1; index <= 3; index += 1) {
                const item = document.getElementById('core-themes-card-overview-item-' + index);
                if (!item) continue;
                const entry = themeEntries[index - 1];
                if (!entry) {
                    item.textContent = '暂无核心主线';
                    continue;
                }
                const leader = entry.leader;
                const leaderName = `${leader.code} ${leader.displayName}`;
                const oneYearText = formatPercent(leader.performance.oneYear);
                item.innerHTML = `<span class="highlight-blue">${entry.label}</span>：${entry.description}，当前由 ${leaderName} 领跑，近1年涨幅${oneYearText}`;
            }
        }

        function renderOverviewHighlights(snapshots) {
            const rankedSnapshots = snapshots.slice().sort(compareSnapshotPriority);
            const strongBuySnapshots = rankedSnapshots.filter(snapshot => snapshot.recommendation.level === 'high').slice(0, 3);
            const watchlistSnapshots = rankedSnapshots.filter(snapshot => snapshot.recommendation.level !== 'high').slice(0, 3);
            renderOverviewHighlightList('strong-buy-card-overview', strongBuySnapshots, 'highlight-green', '暂无强烈推荐标的');
            renderOverviewHighlightList('watchlist-card-overview', watchlistSnapshots, 'highlight', '暂无推荐/观望标的');
            renderCoreThemeHighlights(rankedSnapshots);
        }


        function renderDetailPanel(snapshot) {

            setNodeText('latest-nav-label-' + snapshot.code, snapshot.priceLabel);
            setNodeText('latest-nav-value-' + snapshot.code, formatPrice(snapshot.displayPrice));
            const dailyChangeNode = document.getElementById('daily-change-value-' + snapshot.code);
            if (dailyChangeNode) {
                dailyChangeNode.textContent = formatPercent(snapshot.dailyChange);
                syncNodeStateClass(dailyChangeNode, 'info-value', ['text-green', 'text-red', 'text-amber'], getTrendClass(snapshot.dailyChange));
            }

            const performanceTable = document.getElementById('performance-table-' + snapshot.code);
            if (performanceTable) {
                const columns = [
                    { key: '1m', label: '近1月', value: snapshot.performance.oneMonth },
                    { key: '3m', label: '近3月', value: snapshot.performance.threeMonth },
                    { key: '6m', label: '近6月', value: snapshot.performance.sixMonth },
                    { key: '1y', label: '近1年', value: snapshot.performance.oneYear }
                ];
                const hasAllCells = columns.every(column => document.getElementById(`performance-return-${column.key}-${snapshot.code}`));
                if (!hasAllCells) {
                    const rowHtml = columns.map(column => {
                        const className = column.value === null ? '' : (column.value >= 0 ? 'positive' : 'negative');
                        return `<td id="performance-return-${column.key}-${snapshot.code}" class="${className}">${formatPercent(column.value)}</td>`;
                    }).join('');
                    performanceTable.innerHTML = `<tr>${columns.map(column => `<th>${column.label}</th>`).join('')}</tr><tr>${rowHtml}</tr>`;
                }
                columns.forEach(column => {
                    const cell = document.getElementById(`performance-return-${column.key}-${snapshot.code}`);
                    if (!cell) {
                        return;
                    }
                    cell.textContent = formatPercent(column.value);
                    const trendClass = column.value === null ? null : (column.value >= 0 ? 'positive' : 'negative');
                    syncNodeStateClass(cell, null, ['positive', 'negative'], trendClass);
                });
            }

            applyTechSignal(snapshot.code, 'moving-average', snapshot.technical.movingAverage);
            applyTechSignal(snapshot.code, 'rsi', snapshot.technical.rsi);
            applyTechSignal(snapshot.code, 'volume-price', snapshot.technical.volumePrice);
            applyTechSignal(snapshot.code, 'benchmark-comparison', snapshot.technical.benchmarkComparison);
            setNodeText('tech-rating-value-' + snapshot.code, scoreToTextStars(snapshot.technical.score));
            setNodeText('tech-rating-text-' + snapshot.code, snapshot.technical.text);
            const techRatingValue = document.getElementById('tech-rating-value-' + snapshot.code);
            if (techRatingValue) {
                syncNodeStateClass(techRatingValue, 'rating-value', ['high', 'medium', 'low'], snapshot.technical.level);
            }

            setNodeText('recommendation-rating-value-' + snapshot.code, scoreToTextStars(snapshot.recommendationScore));
            setNodeText('recommendation-rating-text-' + snapshot.code, snapshot.recommendation.text);
            const recommendationNode = document.getElementById('recommendation-rating-value-' + snapshot.code);
            if (recommendationNode) {
                syncNodeStateClass(recommendationNode, 'rating-value', ['high', 'medium', 'low'], snapshot.recommendation.level);
            }

            if (snapshot.holdingConcentration !== null) {
                setNodeText('holdings-concentration-value-' + snapshot.code, `${snapshot.holdingConcentration.toFixed(2)}%`);
            }
        }

        function renderHoldingsChart(snapshot) {
            if (typeof echarts === 'undefined') return;
            const chart = getOrInitChart('holdings-chart-' + snapshot.code);
            if (!chart) return;
            const holdingsData = (snapshot.holdings || [])

                .map(item => {
                    const ratio = roundValue(toNumber(item.ratio) || 0, 2);
                    const change = toNumber(item.change);
                    if (!item.name || ratio === null || ratio <= 0) return null;
                    return {
                        name: item.name,
                        value: ratio,
                        change: formatPercent(change),
                        changeColor: change > 0 ? '#10b981' : change < 0 ? '#ef4444' : '#9ca3af'
                    };
                })
                .filter(Boolean);
            const concentration = snapshot.holdingConcentration !== null
                ? snapshot.holdingConcentration
                : roundValue(holdingsData.reduce((sum, item) => sum + item.value, 0), 2);
            const otherRatio = concentration !== null ? roundValue(Math.max(0, 100 - concentration), 2) : null;
            const data = holdingsData.slice();
            if (otherRatio !== null && otherRatio > 0) {
                data.push({ name: '其他', value: otherRatio, change: '--', changeColor: '#9ca3af' });
            }
            if (!data.length) {
                chart.clear();
                chart.setOption({
                    backgroundColor: 'transparent',
                    title: {
                        text: '暂无持仓数据',
                        left: 'center',
                        top: 'center',
                        textStyle: { color: '#94a3b8', fontSize: 16, fontWeight: 'normal' }
                    }
                }, true);
                return;
            }
            chart.setOption({
                backgroundColor: 'transparent',
                tooltip: {
                    trigger: 'item',
                    backgroundColor: 'rgba(30, 41, 59, 0.95)',
                    borderColor: '#475569',
                    borderWidth: 1,
                    textStyle: { color: '#e2e8f0' },
                    formatter: function(params) {
                        const item = data.find(entry => entry.name === params.name) || { change: '--', changeColor: '#9ca3af' };
                        return `<div>${params.name}</div><div>持仓占比: <span>${params.value}%</span></div><div>当日涨跌: <span style="color:${item.changeColor}">${item.change}</span></div>`;
                    }
                },
                legend: {
                    type: 'plain',
                    orient: 'vertical',
                    right: 10,
                    top: 20,
                    bottom: 20,
                    textStyle: { color: '#9ca3af', fontSize: 12 },
                    pageTextStyle: { color: '#9ca3af' }
                },
                series: [{
                    name: '持仓占比',
                    type: 'pie',
                    radius: ['40%', '70%'],
                    center: ['35%', '50%'],
                    avoidLabelOverlap: true,
                    itemStyle: { borderRadius: 4, borderColor: '#1e293b', borderWidth: 2 },
                    label: { show: true, position: 'outside', color: '#9ca3af', fontSize: 11, formatter: '{b}: {d}%' },
                    labelLine: { show: true, lineStyle: { color: '#475569' } },
                    emphasis: {
                        label: { show: true, fontSize: 14, fontWeight: 'bold', color: '#f1f5f9' },
                        itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0, 0, 0, 0.5)' }
                    },
                    data: data.map((item, index) => ({
                        name: item.name,
                        value: item.value,
                        itemStyle: {
                            color: item.name === '其他' ? '#475569' : [
                                '#60a5fa', '#34d399', '#fbbf24', '#f87171', '#a78bfa',
                                '#38bdf8', '#4ade80', '#facc15', '#fb923c', '#e879f9'
                            ][index % 10]
                        }
                    }))
                }]
            }, true);
        }



        function getOrInitChart(elementId) {
            if (typeof echarts === 'undefined') return null;
            const dom = document.getElementById(elementId);
            if (!dom) return null;
            const chart = echarts.getInstanceByDom(dom) || echarts.init(dom);
            const lifecycle = window.__etfChartLifecycle;
            return lifecycle ? lifecycle.bindChart(dom, chart) : chart;
        }


        function initCharts() {
            // REQ-148: 保留兼容入口，按需一次性 init 所有概览图（IO 不支持时降级走这里）
            initPerformanceChart();
            initRadarChart();
            initScaleChart();
            initAnnualChart();
        }

        function initPerformanceChart() {
            const snapshots = buildSnapshots();
            const labels = snapshots.map(item => item.label);

            const perfChart = getOrInitChart('performance-chart');
            if (perfChart) {
                perfChart.setOption({
                    backgroundColor: 'transparent',
                    tooltip: { trigger: 'axis' },
                    legend: { data: ['近1月', '近3月', '近1年'], textStyle: { color: '#9ca3af' }, bottom: 0 },
                    xAxis: {
                        type: 'category',
                        data: labels,
                        axisLabel: { color: '#9ca3af', rotate: 15 },
                        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } }
                    },
                    yAxis: {
                        type: 'value',
                        axisLabel: { color: '#9ca3af', formatter: '{value}%' },
                        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } }
                    },
                    series: [
                        { name: '近1月', type: 'bar', data: snapshots.map(item => roundValue(item.performance.oneMonth, 2) || 0), itemStyle: { color: '#3b82f6' } },
                        { name: '近3月', type: 'bar', data: snapshots.map(item => roundValue(item.performance.threeMonth, 2) || 0), itemStyle: { color: '#10b981' } },
                        { name: '近1年', type: 'bar', data: snapshots.map(item => roundValue(item.performance.oneYear, 2) || 0), itemStyle: { color: '#f59e0b' } }
                    ]
                }, true);
            }
        }

        function initRadarChart() {
            const snapshots = buildSnapshots();
            const radarChart = getOrInitChart('radar-chart');
            if (radarChart) {
                const topSnapshots = snapshots.slice().sort((left, right) => right.recommendationScore - left.recommendationScore).slice(0, 3);
                radarChart.setOption({
                    backgroundColor: 'transparent',
                    radar: {
                        indicator: [
                            { name: '技术面', max: 5 },
                            { name: '基本面', max: 5 },
                            { name: '趋势强度', max: 5 },
                            { name: '资金流向', max: 5 },
                            { name: '相对强弱', max: 5 }
                        ],
                        axisName: { color: '#9ca3af' },
                        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
                        splitArea: { areaStyle: { color: ['rgba(59,130,246,0.1)', 'rgba(59,130,246,0.05)'] } }
                    },
                    legend: { data: topSnapshots.map(item => item.label), textStyle: { color: '#9ca3af' }, bottom: 0 },
                    series: [{
                        type: 'radar',
                        data: topSnapshots.map((item, index) => ({
                            value: item.radarValues,
                            name: item.label,
                            lineStyle: { color: ['#10b981', '#3b82f6', '#f59e0b'][index % 3] },
                            areaStyle: { color: ['rgba(16,185,129,0.3)', 'rgba(59,130,246,0.3)', 'rgba(245,158,11,0.3)'][index % 3] }
                        }))
                    }]
                }, true);
            }
        }

        function initScaleChart() {
            const snapshots = buildSnapshots();
            const scaleChart = getOrInitChart('scale-chart');
            if (scaleChart) {
                scaleChart.setOption({
                    backgroundColor: 'transparent',
                    tooltip: { trigger: 'item', formatter: '{b}: {c}亿元' },
                    series: [{
                        type: 'pie',
                        radius: ['40%', '70%'],
                        center: ['50%', '50%'],
                        avoidLabelOverlap: false,
                        itemStyle: { borderRadius: 10, borderColor: '#0a192f', borderWidth: 2 },
                        label: { show: true, color: '#9ca3af', formatter: '{b}\n{c}亿' },
                        data: snapshots.map((item, index) => ({
                            value: roundValue(item.scale, 2) || 0,
                            name: item.label,
                            itemStyle: { color: ['#ec4899', '#f59e0b', '#3b82f6', '#10b981', '#8b5cf6', '#6b7280'][index % 6] }
                        }))
                    }]
                }, true);
            }
        }

        function initAnnualChart() {
            const snapshots = buildSnapshots();
            const annualChart = getOrInitChart('annual-chart');
            if (annualChart) {
                const sorted = snapshots.slice().sort((left, right) => (left.performance.oneYear || 0) - (right.performance.oneYear || 0));
                annualChart.setOption({
                    backgroundColor: 'transparent',
                    tooltip: { trigger: 'axis', formatter: '{b}: {c}%' },
                    xAxis: {
                        type: 'value',
                        axisLabel: { color: '#9ca3af', formatter: '{value}%' },
                        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } }
                    },
                    yAxis: {
                        type: 'category',
                        data: sorted.map(item => item.label),
                        axisLabel: { color: '#9ca3af' },
                        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } }
                    },
                    series: [{
                        type: 'bar',
                        data: sorted.map(item => ({
                            value: roundValue(item.performance.oneYear, 2) || 0,
                            itemStyle: { color: (item.performance.oneYear || 0) >= 50 ? '#10b981' : (item.performance.oneYear || 0) >= 20 ? '#3b82f6' : '#6b7280' }
                        })),
                        barWidth: 20,
                        itemStyle: { borderRadius: [0, 8, 8, 0] }
                    }]
                }, true);
            }
        }

        // REQ-148: 概览页图表懒加载调度器
        // performance-chart 首屏可见 → 立刻 init
        // radar/scale/annual 通常在首屏以下 → IntersectionObserver 入视口时再 init
        const LAZY_OVERVIEW_CHARTS = [
            { id: 'radar-chart', initFn: initRadarChart },
            { id: 'scale-chart', initFn: initScaleChart },
            { id: 'annual-chart', initFn: initAnnualChart }
        ];

        function initOverviewChartsLazy() {
            // performance-chart 立即 init（视口内首图）
            initPerformanceChart();

            // 老浏览器不支持 IntersectionObserver → 降级：全部立即 init
            if (typeof IntersectionObserver === 'undefined') {
                LAZY_OVERVIEW_CHARTS.forEach(c => c.initFn());
                return;
            }

            const observer = new IntersectionObserver(function(entries) {
                entries.forEach(function(entry) {
                    if (entry.isIntersecting) {
                        const target = entry.target;
                        const matched = LAZY_OVERVIEW_CHARTS.find(c => c.id === target.id);
                        if (matched) {
                            matched.initFn();
                        }
                        observer.unobserve(target);
                    }
                });
            }, { rootMargin: '200px 0px' }); // 提前 200px 触发，用户感知不到延迟

            LAZY_OVERVIEW_CHARTS.forEach(function(c) {
                const dom = document.getElementById(c.id);
                if (dom) {
                    observer.observe(dom);
                }
            });
        }

        function hydrateAllPanels() {
            buildSnapshots().forEach(snapshot => {
                renderOverviewCard(snapshot);
                renderDetailPanel(snapshot);
            });
        }

        function requestDebugHotspotRefresh(frameCount) {
            const debugTools = window.__ETF_DEBUG_TOOLS__;
            if (!debugTools || typeof debugTools.refreshHotTargets !== 'function') {
                return;
            }
            let remaining = Math.max(frameCount || 1, 1);
            function step() {
                remaining -= 1;
                if (remaining <= 0) {
                    debugTools.refreshHotTargets();
                    return;
                }
                window.requestAnimationFrame(step);
            }
            window.requestAnimationFrame(step);
        }

        function renderETFPanel(code) {
            const panel = document.getElementById('panel-' + code);
            if (!panel) return;
            const render = () => {
                const snapshot = buildRuntimeSnapshot(code);
                renderDetailPanel(snapshot);
                renderHoldingsChart(snapshot);
                renderKlineChart(code);
                requestDebugHotspotRefresh(2);
            };
            const lifecycle = window.__etfChartLifecycle;
            if (lifecycle) {
                lifecycle.whenVisible(panel, render);
                return;
            }
            render();
        }



        // 渲染日线K线图（主图含ETF vs 基准指数对比，右侧百分比轴）
        function renderDailyChart(code) {
            const chartDom = document.getElementById('kline-daily-' + code);
            if (!chartDom || !klineData[code] || !klineData[code].daily) return;

            const chart = getOrInitChart('kline-daily-' + code);
            if (!chart) return;

            const data = klineData[code].daily;

            const benchmarkData = klineData[code].benchmark;
            const etfNormalized = klineData[code].etf_normalized;
            const benchmarkName = klineData[code].benchmark_name || '基准指数';
            const etfName = klineData[code].name || 'ETF';
            
            // 计算MA均线
            function calculateMA(dayCount, klineData) {
                var result = [];
                for (var i = 0; i < klineData.length; i++) {
                    if (i < dayCount - 1) {
                        result.push('-');
                        continue;
                    }
                    var sum = 0;
                    for (var j = 0; j < dayCount; j++) {
                        sum += klineData[i - j][1];
                    }
                    result.push((sum / dayCount).toFixed(3));
                }
                return result;
            }
            
            // 路径 B 归一化：以可见窗口最左根开盘价为 base（0%），K 线 / MA 归一化为相对涨跌幅（%）
            // REQ-164: base 不再固定为 kline[0][0]，而是跟随 dataZoom 变化的"当前可见最左根"
            const originalKline = data.kline;  // 保留原值供 tooltip 显示
            const ma5Raw = data.ma5 || calculateMA(5, data.kline);
            const ma20Raw = data.ma20 || calculateMA(20, data.kline);
            const benchmarkRawCloses = (benchmarkData && benchmarkData.closes) ? benchmarkData.closes : null;

            // 当前 base 索引 / base 开盘价（随 dataZoom 变化）
            let currentBaseIdx = 0;
            let baseOpen = (data.kline && data.kline.length > 0) ? data.kline[0][0] : null;

            const normalizeRatioAgainst = function(v, base) {
                if (v === '-' || v === null || v === undefined || base === null || base === 0) return v;
                const n = typeof v === 'number' ? v : parseFloat(v);
                if (Number.isNaN(n)) return v;
                return Number(((n / base - 1) * 100).toFixed(2));
            };

            // 给定 base，计算 K线 / MA5 / MA20 / benchmark 的归一化 series data
            const buildNormalizedSeriesData = function(baseIdx) {
                const base = originalKline[baseIdx] ? originalKline[baseIdx][0] : null;
                const kArr = originalKline.map(function(k) {
                    return [
                        normalizeRatioAgainst(k[0], base),
                        normalizeRatioAgainst(k[1], base),
                        normalizeRatioAgainst(k[2], base),
                        normalizeRatioAgainst(k[3], base)
                    ];
                });
                const ma5Arr = ma5Raw.map(function(v) { return normalizeRatioAgainst(v, base); });
                const ma20Arr = ma20Raw.map(function(v) { return normalizeRatioAgainst(v, base); });
                // benchmark rebase：用同一索引处的 benchmark close 作为 base（ETF 和 benchmark 在同一根归零）
                let benchArr = null;
                if (benchmarkRawCloses && benchmarkRawCloses[baseIdx]) {
                    const bBase = benchmarkRawCloses[baseIdx];
                    benchArr = benchmarkRawCloses.map(function(c) {
                        if (c === null || c === undefined || bBase === 0) return '-';
                        return Number(((c / bBase - 1) * 100).toFixed(2));
                    });
                }
                return { kArr: kArr, ma5Arr: ma5Arr, ma20Arr: ma20Arr, benchArr: benchArr, base: base };
            };

            const initialNorm = buildNormalizedSeriesData(0);
            const normalizedKline = initialNorm.kArr;
            const normalizedMa5 = initialNorm.ma5Arr;
            const normalizedMa20 = initialNorm.ma20Arr;

            // 基础系列：K线 + 均线（已归一化为 %）
            const series = [{
                name: 'K线',
                type: 'candlestick',
                data: normalizedKline,
                itemStyle: {
                    color: '#10b981',
                    color0: '#ef4444',
                    borderColor: '#10b981',
                    borderColor0: '#ef4444'
                }
            }, {
                name: 'MA5',
                type: 'line',
                data: normalizedMa5,
                smooth: true,
                lineStyle: { color: '#f59e0b', width: 1 },
                symbol: 'none'
            }, {
                name: 'MA20',
                type: 'line',
                data: normalizedMa20,
                smooth: true,
                lineStyle: { color: '#06b6d4', width: 1 },
                symbol: 'none'
            }, {
                name: '成交额',
                type: 'bar',
                xAxisIndex: 1,
                yAxisIndex: 1,
                data: data.amounts || data.volumes,
                itemStyle: {
                    color: function(params) {
                        const k = data.kline[params.dataIndex];
                        return k[1] >= k[0] ? 'rgba(16, 185, 129, 0.5)' : 'rgba(239, 68, 68, 0.5)';
                    }
                }
            }];

            // 图例数据
            const legendData = ['K线', 'MA5', 'MA20'];
            
            // Y轴配置（主图左轴改为 % 涨跌幅刻度；右轴移除，benchmark 共用主轴）
            const yAxisConfig = [{
                scale: true,
                position: 'left',
                axisLine: { lineStyle: { color: '#4b5563' } },
                axisLabel: {
                    color: '#9ca3af',
                    fontSize: 10,
                    formatter: function(v) { return (typeof v === 'number' ? Math.round(v) : v) + '%'; }
                },
                splitLine: { lineStyle: { color: 'rgba(75, 85, 99, 0.2)' } }
            }, {
                scale: true,
                gridIndex: 1,
                splitNumber: 2,
                axisLine: { show: false },
                axisLabel: { show: false },
                splitLine: { show: false },
                axisPointer: {
                    label: {
                        formatter: function(params) {
                            const v = typeof params.value === 'number' ? params.value : parseFloat(params.value);
                            if (Number.isNaN(v)) return params.value;
                            return (v / 1e8).toFixed(2);
                        }
                    }
                }
            }];

            // benchmark 数据跟随 ETF 的 base 索引重新归一化（共用主轴，同一根上 0%）
            if (benchmarkData && etfNormalized && initialNorm.benchArr) {
                series.push({
                    name: benchmarkName,
                    type: 'line',
                    yAxisIndex: 0,
                    data: initialNorm.benchArr,
                    smooth: true,
                    lineStyle: { color: '#f59e0b', width: 2, type: 'dashed' },
                    symbol: 'none'
                });

                legendData.push(benchmarkName);
            }
            
            const option = {
                backgroundColor: 'transparent',
                tooltip: {
                    trigger: 'axis',
                    axisPointer: { type: 'cross' },
                    backgroundColor: 'rgba(10, 25, 47, 0.95)',
                    borderColor: '#3b82f6',
                    textStyle: { color: '#e0e0e0', fontSize: 11 },
                    formatter: function(params) {
                        if (!params || params.length === 0) return '';

                        let html = '<div >' + params[0].name + '</div>';

                        // 查找K线数据（从原始 OHLC 中取价格，避免 tooltip 显示归一化后的 %）
                        const klineParam = params.find(p => p.seriesName === 'K线');
                        if (klineParam && originalKline[klineParam.dataIndex]) {
                            const k = originalKline[klineParam.dataIndex];
                            const changeColor = k[1] >= k[0] ? '#10b981' : '#ef4444';
                            html += '<div >开: <span >' + k[0] + '</span> 收: <span style="color:' + changeColor + '">' + k[1] + '</span></div>';
                            html += '<div >高: <span >' + k[3] + '</span> 低: <span >' + k[2] + '</span></div>';
                            // 相对昨日（上一根柱子收盘 → 今日收盘）
                            const prev = originalKline[klineParam.dataIndex - 1];
                            if (prev && prev[1]) {
                                const dayPct = ((k[1] / prev[1] - 1) * 100).toFixed(2);
                                const dayColor = k[1] >= prev[1] ? '#10b981' : '#ef4444';
                                html += '<div >相对昨日: <span style="color:' + dayColor + '">' + (dayPct >= 0 ? '+' : '') + dayPct + '%</span></div>';
                            }
                        }

                        // 查找百分比数据（benchmark 对比线）
                        params.forEach(p => {
                            if (p.seriesName && (p.seriesName.includes('相对') || p.seriesName.includes('指数') || p.seriesName.includes('300'))) {
                                if (typeof p.data === 'number') {
                                    const color = p.color || '#9ca3af';
                                    html += '<div >' + p.seriesName + ': <span style="color:' + color + '">' + p.data.toFixed(2) + '%</span></div>';
                                }
                            }
                        });

                        // 成交额
                        const amountParam = params.find(p => p.seriesName === '成交额');
                        if (amountParam && typeof amountParam.data === 'number') {
                            html += '<div >成交额: <span >' + (amountParam.data / 1e8).toFixed(2) + ' 亿</span></div>';
                        }

                        return html;
                    }
                },
                legend: {
                    data: legendData,
                    selected: { '沪深300': false },
                    top: 0,
                    textStyle: { color: '#9ca3af', fontSize: 10 },
                    itemWidth: 12,
                    itemHeight: 8
                },
                grid: [
                    { left: '8%', right: '8%', top: 30, height: '60%' },
                    { left: '8%', right: '8%', top: '78%', height: '15%' }
                ],
                xAxis: [{
                    type: 'category',
                    data: data.dates,
                    boundaryGap: true,
                    axisLine: { onZero: false, lineStyle: { color: '#4b5563' } },
                    axisLabel: { color: '#9ca3af', fontSize: 9, rotate: 0, interval: 9, formatter: function(value) { return (value || '').length >= 10 ? value.substring(5) : value; } },
                    splitLine: { show: false }
                }, {
                    type: 'category',
                    gridIndex: 1,
                    data: data.dates,
                    boundaryGap: true,
                    axisLine: { onZero: false, lineStyle: { color: '#4b5563' } },
                    axisLabel: { show: false },
                    splitLine: { show: false }
                }],
                yAxis: yAxisConfig,
                dataZoom: [{
                    type: 'inside',
                    xAxisIndex: [0, 1],
                    start: 0,
                    end: 100
                }],
                series: series
            };

            chart.setOption(option, true);

            // REQ-164: dataZoom 触发 rebase —— 让 Y 轴始终以"当前可见窗口最左根"为 0%
            let rebaseTimer = null;
            chart.off('datazoom');
            chart.on('datazoom', function() {
                if (rebaseTimer) clearTimeout(rebaseTimer);
                rebaseTimer = setTimeout(function() {
                    const opt = chart.getOption();
                    const dz = opt.dataZoom && opt.dataZoom[0];
                    if (!dz) return;
                    const startPct = typeof dz.start === 'number' ? dz.start : 0;
                    const total = originalKline.length;
                    const newBaseIdx = Math.max(0, Math.min(total - 1, Math.floor(startPct / 100 * total)));
                    if (newBaseIdx === currentBaseIdx) return;
                    currentBaseIdx = newBaseIdx;
                    baseOpen = originalKline[newBaseIdx] ? originalKline[newBaseIdx][0] : baseOpen;
                    const norm = buildNormalizedSeriesData(newBaseIdx);
                    const seriesUpdate = [
                        { name: 'K线', data: norm.kArr },
                        { name: 'MA5', data: norm.ma5Arr },
                        { name: 'MA20', data: norm.ma20Arr }
                    ];
                    if (norm.benchArr && benchmarkData) {
                        seriesUpdate.push({ name: benchmarkName, data: norm.benchArr });
                    }
                    chart.setOption({ series: seriesUpdate });
                }, 80);
            });
        }

        function renderWeeklyChart(code) {
            const chartDom = document.getElementById('kline-weekly-' + code);
            if (!chartDom || !klineData[code] || !klineData[code].weekly) return;
            
            const chart = getOrInitChart('kline-weekly-' + code);
            if (!chart) return;
            const data = klineData[code].weekly;

            
            // 计算MA均线
            function calculateMA(dayCount, klineData) {
                var result = [];
                for (var i = 0; i < klineData.length; i++) {
                    if (i < dayCount - 1) {
                        result.push('-');
                        continue;
                    }
                    var sum = 0;
                    for (var j = 0; j < dayCount; j++) {
                        sum += klineData[i - j][1];
                    }
                    result.push((sum / dayCount).toFixed(3));
                }
                return result;
            }
            
            // 路径 B 归一化 + REQ-164 动态 rebase（周 K）
            const originalKlineW = data.kline;
            const ma5RawW = data.ma5 || calculateMA(5, data.kline);
            const ma20RawW = data.ma20 || calculateMA(20, data.kline);

            let currentBaseIdxW = 0;
            let baseOpenW = (data.kline && data.kline.length > 0) ? data.kline[0][0] : null;

            const normalizeRatioAgainstW = function(v, base) {
                if (v === '-' || v === null || v === undefined || base === null || base === 0) return v;
                const n = typeof v === 'number' ? v : parseFloat(v);
                if (Number.isNaN(n)) return v;
                return Number(((n / base - 1) * 100).toFixed(2));
            };

            const buildNormalizedSeriesDataW = function(baseIdx) {
                const base = originalKlineW[baseIdx] ? originalKlineW[baseIdx][0] : null;
                const kArr = originalKlineW.map(function(k) {
                    return [
                        normalizeRatioAgainstW(k[0], base),
                        normalizeRatioAgainstW(k[1], base),
                        normalizeRatioAgainstW(k[2], base),
                        normalizeRatioAgainstW(k[3], base)
                    ];
                });
                const ma5Arr = ma5RawW.map(function(v) { return normalizeRatioAgainstW(v, base); });
                const ma20Arr = ma20RawW.map(function(v) { return normalizeRatioAgainstW(v, base); });
                return { kArr: kArr, ma5Arr: ma5Arr, ma20Arr: ma20Arr, base: base };
            };

            const initialNormW = buildNormalizedSeriesDataW(0);
            const normalizedKlineW = initialNormW.kArr;
            const normalizedMa5W = initialNormW.ma5Arr;
            const normalizedMa20W = initialNormW.ma20Arr;

            const option = {
                backgroundColor: 'transparent',
                tooltip: {
                    trigger: 'axis',
                    axisPointer: { type: 'cross' },
                    backgroundColor: 'rgba(10, 25, 47, 0.95)',
                    borderColor: '#3b82f6',
                    textStyle: { color: '#e0e0e0', fontSize: 11 },
                    formatter: function(params) {
                        if (!params || params.length === 0) return '';
                        let html = '<div >' + params[0].name + '</div>';
                        const klineParam = params.find(p => p.seriesName === 'K线');
                        if (klineParam && originalKlineW[klineParam.dataIndex]) {
                            const k = originalKlineW[klineParam.dataIndex];
                            const changeColor = k[1] >= k[0] ? '#10b981' : '#ef4444';
                            html += '<div >开: <span >' + k[0] + '</span> 收: <span style="color:' + changeColor + '">' + k[1] + '</span></div>';
                            html += '<div >高: <span >' + k[3] + '</span> 低: <span >' + k[2] + '</span></div>';
                            // 相对上周（上一根周 K 收盘 → 本周收盘）
                            const prev = originalKlineW[klineParam.dataIndex - 1];
                            if (prev && prev[1]) {
                                const weekPct = ((k[1] / prev[1] - 1) * 100).toFixed(2);
                                const weekColor = k[1] >= prev[1] ? '#10b981' : '#ef4444';
                                html += '<div >相对上周: <span style="color:' + weekColor + '">' + (weekPct >= 0 ? '+' : '') + weekPct + '%</span></div>';
                            }
                        }
                        const amountParam = params.find(p => p.seriesName === '成交额');
                        if (amountParam && typeof amountParam.data === 'number') {
                            html += '<div >成交额: <span >' + (amountParam.data / 1e8).toFixed(2) + ' 亿</span></div>';
                        }
                        return html;
                    }
                },
                legend: {
                    data: ['K线', 'MA5', 'MA20'],
                    top: 0,
                    textStyle: { color: '#9ca3af', fontSize: 10 },
                    itemWidth: 12,
                    itemHeight: 8
                },
                grid: [
                    { left: '10%', right: '3%', top: 30, height: '55%' },
                    { left: '10%', right: '3%', top: '75%', height: '18%' }
                ],
                xAxis: [{
                    type: 'category',
                    data: data.dates,
                    boundaryGap: true,
                    axisLine: { onZero: false, lineStyle: { color: '#4b5563' } },
                    axisLabel: { color: '#9ca3af', fontSize: 9, rotate: 0, interval: 7, formatter: function(value) { return (value || '').length >= 10 ? value.substring(5) : value; } },
                    splitLine: { show: false }
                }, {
                    type: 'category',
                    gridIndex: 1,
                    data: data.dates,
                    boundaryGap: true,
                    axisLine: { onZero: false, lineStyle: { color: '#4b5563' } },
                    axisLabel: { show: false },
                    splitLine: { show: false }
                }],
                yAxis: [{
                    scale: true,
                    axisLine: { lineStyle: { color: '#4b5563' } },
                    axisLabel: {
                        color: '#9ca3af',
                        fontSize: 10,
                        formatter: function(v) { return (typeof v === 'number' ? Math.round(v) : v) + '%'; }
                    },
                    splitLine: { lineStyle: { color: 'rgba(75, 85, 99, 0.2)' } }
                }, {
                    scale: true,
                    gridIndex: 1,
                    splitNumber: 2,
                    axisLine: { show: false },
                    axisLabel: { show: false },
                    splitLine: { show: false },
                    axisPointer: {
                        label: {
                            formatter: function(params) {
                                const v = typeof params.value === 'number' ? params.value : parseFloat(params.value);
                                if (Number.isNaN(v)) return params.value;
                                return (v / 1e8).toFixed(2);
                            }
                        }
                    }
                }],
                dataZoom: [{
                    type: 'inside',
                    xAxisIndex: [0, 1],
                    start: 30,
                    end: 100
                }],
                series: [{
                    name: 'K线',
                    type: 'candlestick',
                    data: normalizedKlineW,
                    itemStyle: {
                        color: '#10b981',
                        color0: '#ef4444',
                        borderColor: '#10b981',
                        borderColor0: '#ef4444'
                    }
                }, {
                    name: 'MA5',
                    type: 'line',
                    data: normalizedMa5W,
                    smooth: true,
                    lineStyle: { color: '#f59e0b', width: 1 },
                    symbol: 'none'
                }, {
                    name: 'MA20',
                    type: 'line',
                    data: normalizedMa20W,
                    smooth: true,
                    lineStyle: { color: '#06b6d4', width: 1 },
                    symbol: 'none'
                }, {
                    name: '成交额',
                    type: 'bar',
                    xAxisIndex: 1,
                    yAxisIndex: 1,
                    data: data.amounts || data.volumes,
                    itemStyle: {
                        color: function(params) {
                            const k = data.kline[params.dataIndex];
                            return k[1] >= k[0] ? 'rgba(16, 185, 129, 0.5)' : 'rgba(239, 68, 68, 0.5)';
                        }
                    }
                }]
            };

            chart.setOption(option, true);

            // REQ-164: dataZoom 触发 rebase（周 K）
            let rebaseTimerW = null;
            chart.off('datazoom');
            chart.on('datazoom', function() {
                if (rebaseTimerW) clearTimeout(rebaseTimerW);
                rebaseTimerW = setTimeout(function() {
                    const opt = chart.getOption();
                    const dz = opt.dataZoom && opt.dataZoom[0];
                    if (!dz) return;
                    const startPct = typeof dz.start === 'number' ? dz.start : 0;
                    const total = originalKlineW.length;
                    const newBaseIdx = Math.max(0, Math.min(total - 1, Math.floor(startPct / 100 * total)));
                    if (newBaseIdx === currentBaseIdxW) return;
                    currentBaseIdxW = newBaseIdx;
                    baseOpenW = originalKlineW[newBaseIdx] ? originalKlineW[newBaseIdx][0] : baseOpenW;
                    const norm = buildNormalizedSeriesDataW(newBaseIdx);
                    chart.setOption({
                        series: [
                            { name: 'K线', data: norm.kArr },
                            { name: 'MA5', data: norm.ma5Arr },
                            { name: 'MA20', data: norm.ma20Arr }
                        ]
                    });
                }, 80);
            });
        }

        // 渲染K线图（同时渲染日线和周线）

        function renderKlineChart(code) {
            renderDailyChart(code);
            renderWeeklyChart(code);
        }

        function switchPanel(panelId) {
            document.querySelectorAll('.etf-panel').forEach(panel => panel.classList.remove('active'));
            document.querySelectorAll('.nav-tab').forEach(tab => tab.classList.remove('active'));
            const nextPanel = document.getElementById('panel-' + panelId);
            if (!nextPanel) return;
            nextPanel.classList.add('active');
            const matchedTab = Array.from(document.querySelectorAll('.nav-tab')).find(tab => tab.getAttribute('onclick') === `switchPanel('${panelId}')`);
            if (matchedTab) {
                matchedTab.classList.add('active');
            }
            if (panelId === 'overview') {
                initChartsWhenReady();
                return;
            }
            if (klineData[panelId]) {
                setTimeout(() => renderETFPanel(panelId), 100);
            }
            if (panelId === 'quant' && typeof window.__initQuantPanel === 'function') {
                setTimeout(() => window.__initQuantPanel(), 100);
            }
        }

        // 初始化图表 - 确保 ECharts 库已加载
        let initAttempts = 0;
        function initChartsWhenReady() {
            if (typeof echarts !== 'undefined') {
                console.log('[初始化] ECharts库已加载，开始初始化图表（懒加载模式）');
                initOverviewChartsLazy();
                const activePanel = document.querySelector('.etf-panel.active');
                const activeCode = activePanel ? activePanel.id.replace('panel-', '') : 'overview';
                if (activeCode !== 'overview' && activeCode !== 'macro' && klineData[activeCode]) {
                    renderETFPanel(activeCode);
                }
                return;
            }
            initAttempts += 1;
            if (initAttempts > 50) {
                console.error('[初始化] ECharts库加载超时！');
                return;
            }
            setTimeout(initChartsWhenReady, 100);
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function() {
                console.log('[初始化] DOMContentLoaded事件触发');
                hydrateAllPanels();
                setTimeout(initChartsWhenReady, 50);
            });
        } else {
            console.log('[初始化] 页面已加载，直接初始化');
            hydrateAllPanels();
            initChartsWhenReady();
        }

        window.addEventListener('load', function() {
            console.log('[初始化] window.load事件触发');
            hydrateAllPanels();
            initChartsWhenReady();
        });




