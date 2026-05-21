/**
 * quant-main.js v4 — Tuner UI port
 * Two-column layout: left (perf + kline replay), right (snapshot)
 *
 * Data: window.__QUANT_RUNTIME__ = {
 *   templateMeta, templates, config, etfNameMap,
 *   klineReplay: { code: { dates, close, volume, rsi } }
 * }
 */
(function () {
  "use strict";

  var Q = window.__QUANT_RUNTIME__;
  if (!Q || !Q.templates || Object.keys(Q.templates).length === 0) return;

  var LC = window.__etfChartLifecycle || { bindChart: function(){}, resizeAllCharts: function(){} };

  var C = {
    green: "#10b981", red: "#ef4444", blue: "#3b82f6",
    orange: "#f59e0b", cyan: "#06b6d4", purple: "#8b5cf6",
    gray: "#64748b", text: "#e0e0e0", muted: "#94a3b8",
    gridLine: "rgba(255,255,255,0.06)",
  };

  function baseAxis() {
    return { axisLine:{lineStyle:{color:C.gridLine}}, axisTick:{show:false}, axisLabel:{color:C.muted,fontSize:11}, splitLine:{lineStyle:{color:C.gridLine}} };
  }
  function baseTooltip() {
    return { backgroundColor:"rgba(10,25,47,0.92)", borderColor:"rgba(59,130,246,0.2)", textStyle:{color:C.text,fontSize:12} };
  }

  // ── State ─────────────────────────────────────────────────
  var activeTemplate = "yr1";
  var navChart = null, ddChart = null;
  var klineFreq = "daily";
  var klineReplayChart = null;
  var currentKlineCode = null;
  var initialized = false;
  var currentSigIdx = -1;

  // ── Public API ────────────────────────────────────────────
  window.__initQuantPanel = function () {
    if (!initialized) { initialized = true; renderAll(); }
    else { setTimeout(function(){ LC.resizeAllCharts(); }, 200); }
  };

  window.switchQuantPeriod = function (tid) {
    if (!Q.templates[tid]) return;
    activeTemplate = tid;
    currentKlineCode = null;
    document.getElementById("seg-yr1").classList.toggle("active", tid === "yr1");
    document.getElementById("seg-yr3").classList.toggle("active", tid === "yr3");
    renderAll();
  };

  window.switchQuantKlineFreq = function (freq) {
    klineFreq = freq;
    document.getElementById("quant-kline-freq-daily").classList.toggle("active", freq === "daily");
    document.getElementById("quant-kline-freq-weekly").classList.toggle("active", freq === "weekly");
    var tpl = Q.templates[activeTemplate];
    if (tpl) renderNavChart(tpl);
  };

  // ── Master render ─────────────────────────────────────────
  function renderAll() {
    var tpl = Q.templates[activeTemplate];
    if (!tpl) return;
    renderParamTags();
    renderMetrics(tpl);
    renderNavChart(tpl);
    renderDrawdownChart(tpl);
    // Show snapshot section
    var snapSec = document.getElementById("quant-snapshot-section");
    if (snapSec) snapSec.style.display = "block";
    // Render latest snapshot
    var lastIdx = tpl.weeklySnapshots ? tpl.weeklySnapshots.length - 1 : -1;
    renderSnapshot(tpl, lastIdx);
    setTimeout(function(){ LC.resizeAllCharts(); }, 300);
  }

  // ── Parameter Tags ────────────────────────────────────────
  function renderParamTags() {
    var container = document.getElementById("quant-param-tags");
    if (!container) return;
    var cfg = (Q.config || {})[activeTemplate];
    if (!cfg) { container.innerHTML = ''; return; }

    var conf = cfg.confidence || {};
    var pos = cfg.position || {};
    var weights = (cfg.scoring || {}).weights || {};

    var tags = [];
    var w1 = Math.round((weights.ema_deviation || 0) * 100);
    var w3 = Math.round((weights.volume_ratio || 0) * 100);
    tags.push({l:"F1", v:w1+"%", c:w1>0?C.blue:C.gray});
    tags.push({l:"F3", v:w3+"%", c:w3>0?C.green:C.gray});
    tags.push({l:"MA", v:(conf.ma_trend_period||20)+"", c:C.cyan});
    tags.push({l:"Bull", v:((conf.ma_bull_pos||1)*100).toFixed(0)+"%", c:C.green});
    tags.push({l:"Bear", v:((conf.ma_bear_pos||0.4)*100).toFixed(0)+"%", c:C.orange});
    if (conf.ma_direction_confirm) tags.push({l:"方向确认", v:"ON", c:C.purple});
    tags.push({l:"调仓", v:pos.rebalance_freq==="daily"?"日频":"周频", c:C.muted});
    tags.push({l:"持仓", v:(pos.max_holdings||6)+"支", c:C.muted});

    var html = '';
    for (var i = 0; i < tags.length; i++) {
      var t = tags[i];
      html += '<span class="qt-param-tag"><span style="color:'+C.muted+'">'+t.l+'</span><span style="color:'+t.c+';font-weight:600;">'+t.v+'</span></span>';
    }
    container.innerHTML = html;
  }

  // ── Metrics (8 cards) ────────────────────────────────────
  function renderMetrics(tpl) {
    var s = tpl.summary;
    var map = [
      {id:"m-annual",  v:s.annualReturn.toFixed(1)+"%", cls:s.annualReturn>=0?"green":"red"},
      {id:"m-total",   v:s.totalReturn.toFixed(1)+"%", cls:s.totalReturn>=0?"green":"red"},
      {id:"m-dd",      v:s.maxDrawdown.toFixed(1)+"%", cls:"red"},
      {id:"m-sharpe",  v:s.sharpe.toFixed(2), cls:"blue"},
      {id:"m-sortino", v:s.sortino.toFixed(2), cls:"blue"},
      {id:"m-wr",      v:s.winRate.toFixed(1)+"% / "+(s.payoffRatio||0).toFixed(2), cls:s.winRate>=50?"green":""},
      {id:"m-rb",      v:(s.rebalanceDays>0?Math.round(s.rebalanceCount/s.rebalanceDays*100)+"%":"-"), cls:""},
      {id:"m-comm",    v:(s.commissionPct||0).toFixed(2)+"%", cls:""},
    ];
    for (var i = 0; i < map.length; i++) {
      var el = document.getElementById(map[i].id);
      if (el) { el.textContent = map[i].v; el.className = "value " + map[i].cls; }
    }
  }

  // ── NAV Chart ────────────────────────────────────────────
  function renderNavChart(tpl) {
    var dom = document.getElementById("quant-nav-chart");
    if (!dom) return;
    if (navChart) { navChart.dispose(); }
    navChart = echarts.init(dom);
    LC.bindChart(dom, navChart);

    var dates, navPct;
    if (klineFreq === "weekly") {
      var res = resampleWeekly(tpl.navSeries.dates, tpl.navSeries.nav);
      dates = res.dates; navPct = res.values;
    } else {
      dates = tpl.navSeries.dates;
      navPct = tpl.navSeries.nav;
    }
    var benchPct = tpl.navSeries.hs300 || [];
    var eqPct = tpl.navSeries.eqWeight || null;
    var snapshots = tpl.weeklySnapshots || [];

    // Regime switch markPoints
    var switchMarkPts = [];
    if (snapshots.length > 1) {
      var dateLookup = {};
      for (var di = 0; di < dates.length; di++) dateLookup[dates[di]] = di;
      var prevRegime = snapshots[0].regime;
      for (var si = 1; si < snapshots.length; si++) {
        var cur = snapshots[si];
        if (cur.regime && cur.regime !== prevRegime) {
          var isToBear = cur.regime === "ma_below";
          var idx = dateLookup[cur.date];
          if (idx != null) {
            switchMarkPts.push({
              name: (isToBear ? "Bear " : "Bull ") + (cur.totalTarget * 100).toFixed(0) + "%",
              coord: [cur.date, navPct[idx]],
              symbol: "triangle", symbolRotate: isToBear ? 180 : 0, symbolSize: 12,
              itemStyle: { color: isToBear ? C.red : C.green, borderColor: "#0f1419", borderWidth: 1 },
              label: { show: false },
            });
          }
          prevRegime = cur.regime;
        }
      }
    }

    var series = [
      {
        name: "策略净值", type: "line", data: navPct, showSymbol: false,
        lineStyle: { color: C.blue, width: 3 },
        areaStyle: { color: new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:"rgba(59,130,246,0.25)"},{offset:1,color:"rgba(59,130,246,0.02)"}]) },
        itemStyle: { color: C.blue },
        markPoint: switchMarkPts.length > 0 ? { data: switchMarkPts, animation: false } : undefined,
      },
      { name: "沪深300", type: "line", data: benchPct, showSymbol: false,
        lineStyle: { color: C.orange, width: 1.5, type: "dashed" }, itemStyle: { color: C.orange } },
      { name: "等权持有", type: "line", data: eqPct || [], showSymbol: false,
        lineStyle: { color: C.purple, width: 1.5, type: "dotted" }, itemStyle: { color: C.purple } },
    ];

    navChart.setOption({
      tooltip: Object.assign(baseTooltip(), {trigger:"axis", axisPointer:{type:"line",lineStyle:{color:"rgba(255,255,255,0.6)",width:1}}, formatter:function(params){
        var d = params[0].axisValue;
        var out = '<div style="font-weight:600;margin-bottom:4px">'+d+'</div>';
        for (var i = 0; i < params.length; i++) {
          if (params[i].value != null) out += '<div>'+params[i].marker+' '+params[i].seriesName+': '+params[i].value.toFixed(2)+'</div>';
        }
        return out;
      }}),
      legend: { data:["策略净值","沪深300","等权持有"], textStyle:{color:C.muted,fontSize:11}, top:4,
        formatter: function(name){ if(name==="等权持有") return "等权持有(25支买入不动)"; return name; }
      },
      grid: { left:56, right:20, top:40, bottom:32 },
      xAxis: Object.assign(baseAxis(), {type:"category", data:dates, boundaryGap:false}),
      yAxis: Object.assign(baseAxis(), {type:"value", scale:true, name:"净值(%)", nameTextStyle:{color:C.muted,fontSize:11}}),
      series: series,
      dataZoom: [{type:"inside", start:0, end:100}],
    });

    // Click -> snapshot
    navChart.getZr().on("click", function(params) {
      var pointInPixel = [params.offsetX, params.offsetY];
      if (!navChart.containPixel("grid", pointInPixel)) return;
      var dataIdx = navChart.convertFromPixel({seriesIndex:0}, pointInPixel)[0];
      if (dataIdx == null || dataIdx < 0 || dataIdx >= dates.length) return;
      var clickDate = dates[Math.round(dataIdx)];
      var bestIdx = 0;
      for (var i = 0; i < snapshots.length; i++) {
        if (snapshots[i].date <= clickDate) bestIdx = i;
      }
      renderSnapshot(tpl, bestIdx);
    });
  }

  function resampleWeekly(dates, values) {
    if (!dates || !values) return { dates: dates || [], values: values || [] };
    var wDates = [], wVals = [], curWeek = null;
    for (var i = 0; i < dates.length; i++) {
      var d = new Date(dates[i]);
      var day = d.getDay() || 7;
      var thu = new Date(d);
      thu.setDate(d.getDate() + (4 - day));
      var wk = thu.getFullYear() + "-" + String(thu.getMonth()+1).padStart(2,"0") + "-" + String(thu.getDate()).padStart(2,"0");
      if (wk !== curWeek) {
        if (curWeek !== null) { wDates.push(dates[i-1]); wVals.push(values[i-1]); }
        curWeek = wk;
      }
    }
    if (dates.length > 0) { wDates.push(dates[dates.length-1]); wVals.push(values[values.length-1]); }
    return { dates: wDates, values: wVals };
  }

  // ── Drawdown Chart ────────────────────────────────────────
  function renderDrawdownChart(tpl) {
    var dom = document.getElementById("quant-drawdown-chart");
    if (!dom) return;
    if (ddChart) { ddChart.dispose(); }
    ddChart = echarts.init(dom);
    LC.bindChart(dom, ddChart);

    var snapshots = tpl.weeklySnapshots || [];

    ddChart.setOption({
      tooltip: Object.assign(baseTooltip(), {trigger:"axis", formatter:function(p){ return p[0].axisValue+'<br/>'+p[0].marker+' 回撤: '+p[0].value.toFixed(2)+'%'; }}),
      grid: { left:56, right:20, top:8, bottom:8 },
      xAxis: {type:"category", data:tpl.drawdownSeries.dates, boundaryGap:false, show:false},
      yAxis: {type:"value", axisLabel:{color:C.muted,fontSize:10}, splitLine:{lineStyle:{color:C.gridLine}}, axisLine:{show:false}, axisTick:{show:false}},
      series: [{
        type:"line", data:tpl.drawdownSeries.drawdown, showSymbol:false,
        lineStyle:{color:C.red, width:1.5},
        areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:"rgba(239,68,68,0.3)"},{offset:1,color:"rgba(239,68,68,0.02)"}])},
        itemStyle:{color:C.red},
      }],
      dataZoom:[{type:"inside", start:0, end:100}],
    });

    // Connect nav + dd charts for shared dataZoom and axisPointer
    if (navChart && ddChart) {
      echarts.connect([navChart, ddChart]);
    }
  }

  // ── Update markLines on NAV + DD charts without full redraw ──
  function updateMarkLines(dateStr) {
    var mlData = [{ xAxis: dateStr, lineStyle:{color:C.red,width:1.5,type:'dashed'} }];
    var mlOpt = {
      silent: true, symbol: 'none', animation: false,
      data: mlData,
      label: { show: false },
    };
    if (navChart) {
      navChart.setOption({ series: [{ markLine: mlOpt }] });
    }
    if (ddChart) {
      ddChart.setOption({ series: [{ markLine: mlOpt }] });
    }
  }

  // ── Snapshot ──────────────────────────────────────────────
  function renderSnapshot(tpl, sigIdx) {
    var snapshots = tpl.weeklySnapshots || [];
    if (sigIdx < 0 || sigIdx >= snapshots.length) return;
    currentSigIdx = sigIdx;
    var sig = snapshots[sigIdx];

    // Update markLine on NAV + DD charts (no full redraw)
    updateMarkLines(sig.date);

    // Subtitle
    var sub = document.getElementById("quant-snapshot-subtitle");
    if (sub) sub.textContent = sig.date + " \u00b7 \u7b2c " + (sig.index+1) + " \u6b21\u8c03\u4ed3";

    // Snapshot metrics
    var holdings = (sig.top6 || []).length;
    var totalPos = sig.totalTarget * 100;
    var avgConf = sig.avgConfidence * 100;
    var cash = Math.max(0, 100 - totalPos);

    var el;
    el = document.getElementById("snap-m-holdings"); if (el) { el.textContent = holdings + " \u652f"; el.style.color = C.blue; }
    el = document.getElementById("snap-m-total-pos"); if (el) { el.textContent = totalPos.toFixed(0) + "%"; el.style.color = totalPos > 70 ? C.green : totalPos > 40 ? C.orange : C.red; }
    el = document.getElementById("snap-m-avg-conf"); if (el) { el.textContent = avgConf.toFixed(0) + "%"; el.style.color = avgConf > 60 ? C.orange : C.gray; }
    el = document.getElementById("snap-m-cash"); if (el) { el.textContent = cash.toFixed(0) + "%"; el.style.color = cash > 50 ? C.red : cash > 20 ? C.orange : C.gray; }

    renderSnapshotTable(sig, tpl);
    syncSnapshotHeight();
  }

  // ── Scroll-lock for snapshot table ──────────────────────
  function syncSnapshotHeight() {
    var scroll = document.getElementById("quant-snapshot-scroll");
    var left = document.getElementById("quant-perf-section");
    if (!scroll || !left) return;
    scroll.style.maxHeight = (left.offsetHeight - 220) + "px";
  }

  (function() {
    var scroll = document.getElementById("quant-snapshot-scroll");
    if (!scroll) return;
    scroll.addEventListener("wheel", function(e) {
      var atTop = scroll.scrollTop <= 0;
      var atBottom = scroll.scrollTop + scroll.clientHeight >= scroll.scrollHeight - 1;
      if ((e.deltaY < 0 && atTop) || (e.deltaY > 0 && atBottom)) {
        return; // let page scroll
      }
      e.preventDefault();
      scroll.scrollTop += e.deltaY;
    }, {passive: false});
  })();

  function renderSnapshotTable(sig, tpl) {
    var tbody = document.getElementById("quant-snapshot-body");
    var footer = document.getElementById("quant-snapshot-footer");
    if (!tbody) return;

    var scores = sig.scores || {};
    var positions = sig.positions || {};
    var top6 = sig.top6 || [];

    var sorted = Object.keys(scores).sort(function(a,b){ return scores[b] - scores[a]; });
    var maxScore = sorted.length > 0 ? scores[sorted[0]] : 1;

    var html = '';
    var holdC = 0, outC = 0;

    var detail = sig.detail || {};
    for (var i = 0; i < sorted.length; i++) {
      var code = sorted[i];
      var score = scores[code] * 100;
      // positions from backtest are 0-1 ratios; display as percentage
      var pos = (positions[code] || 0) * 100;
      var inTop6 = top6.indexOf(code) >= 0;
      var name = Q.etfNameMap[code] || code;
      var codeDetail = detail[code] || {};

      // Score color: green if positive, neutral if zero/negative
      var scoreColor = score > 50 ? '#10b981' : (score > 30 ? '#f59e0b' : '#6b7280');
      var scoreWeight = score > 50 ? '700' : '400';

      // Action from detail
      var action = codeDetail.action || '';
      if (!action) {
        if (pos > 0) { action = 'HOLD'; holdC++; }
        else { action = 'OUT'; outC++; }
      } else {
        if (pos > 0) holdC++; else outC++;
      }
      var actionColor = {'new':'#10b981','add':'#3b82f6','reduce':'#f59e0b','adj_up':'#3b82f6','adj_down':'#f59e0b','HOLD':'#6b7280','OUT':'#4b5563'}[action] || '#6b7280';
      var actionLabel = {'new':'NEW','add':'UP','reduce':'DOWN','adj_up':'UP','adj_down':'DOWN','HOLD':'HOLD','OUT':'OUT'}[action] || '';
      if (action === 'OUT') { actionLabel = ''; }

      var topBadge = inTop6 ? '<span style="font-size:10px;margin-left:2px;">🔥</span>' : '';
      var posColor = pos > 0 ? '#10b981' : '#4b5563';
      var posStr = pos > 0 ? '<span style="color:'+posColor+';font-weight:600;">'+pos.toFixed(0)+'%</span>' : '<span style="color:#4b5563;">-</span>';

      html += '<tr class="qt-snap-row" data-code="'+code+'" style="'+(inTop6?'background:rgba(16,185,129,0.04);':'')+'cursor:pointer;">' +
        '<td style="padding:8px 10px;"><span style="color:#60a5fa;font-weight:600;font-size:12px;">'+code+'</span> <span style="color:#e0e0e0;font-size:12px;">'+name+'</span>'+topBadge+'</td>' +
        '<td style="text-align:center;padding:8px 6px;color:'+scoreColor+';font-weight:'+scoreWeight+';font-size:13px;">'+score.toFixed(1)+'</td>' +
        '<td style="text-align:center;padding:8px 6px;">'+posStr+'</td>' +
        '<td style="text-align:center;padding:8px 6px;font-size:11px;color:'+actionColor+';font-weight:600;">'+actionLabel+'</td>' +
        '</tr>';
    }

    tbody.innerHTML = html;
    if (footer) footer.textContent = "TOP6 \u6301\u4ed3 | \u5171 " + sorted.length + " \u652f ETF \u8bc4\u5206";

    // Row click -> K-line replay
    var rows = tbody.querySelectorAll('.qt-snap-row');
    for (var r = 0; r < rows.length; r++) {
      rows[r].onclick = function() {
        var code = this.getAttribute('data-code');
        onSnapshotRowClick(code, tpl);
      };
    }

    // Auto-select first-ranked ETF only if none selected yet
    if (currentKlineCode) {
      onSnapshotRowClick(currentKlineCode, tpl);
    } else if (sorted.length > 0) {
      onSnapshotRowClick(sorted[0], tpl);
    }
  }

  // ── K-line Replay (from tuner) ────────────────────────────
  function onSnapshotRowClick(code, tpl) {
    var sameEtf = (currentKlineCode === code);
    currentKlineCode = code;

    // Highlight selected row
    var rows = document.querySelectorAll('.qt-snap-row');
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      if (r.getAttribute('data-code') === code) {
        r.style.background = 'rgba(59,130,246,0.12)';
        r.style.boxShadow = 'inset 3px 0 0 #3b82f6';
      } else {
        var rc = r.getAttribute('data-code');
        var inTop6 = (tpl.weeklySnapshots[currentSigIdx].top6 || []).indexOf(rc) >= 0;
        r.style.background = inTop6 ? 'rgba(16,185,129,0.04)' : '';
        r.style.boxShadow = '';
      }
    }

    if (sameEtf && klineReplayChart) {
      // Same ETF — just update the markLine, skip full re-render
      updateKlineMarkLine(tpl);
    } else {
      renderKlineReplay(code, tpl);
    }
  }

  function updateKlineMarkLine(tpl) {
    if (!klineReplayChart) return;
    var sig = tpl.weeklySnapshots[currentSigIdx];
    var curDate = sig ? sig.date : null;
    if (!curDate) return;
    klineReplayChart.setOption({
      series: [{
        markLine: {
          silent: true, symbol: 'none', animation: false,
          data: [{ xAxis: curDate, lineStyle:{color:C.red,width:1.5,type:'dashed'} }],
          label: { show: false },
        },
      }],
    });
  }

  function renderKlineReplay(code, tpl) {
    var replayBlock = document.getElementById("quant-kline-replay-block");
    if (!replayBlock) return;

    // Check if kline replay data exists
    var klineData = (Q.klineReplay || {})[code];
    if (!klineData || !klineData.dates || klineData.dates.length === 0) {
      replayBlock.style.display = "none";
      return;
    }

    replayBlock.style.display = "block";

    // Update title
    var titleEl = document.getElementById("quant-kline-replay-title");
    var name = Q.etfNameMap[code] || code;
    var sig = tpl.weeklySnapshots[currentSigIdx];
    if (titleEl) titleEl.innerHTML = '<span style="color:#60a5fa;">' + code + '</span> ' + name +
      '  <span style="color:#6b7280;font-weight:normal;font-size:11px;">— 当前调仓 ' + (sig ? sig.date : '') + '</span>';

    var dom = document.getElementById("quant-kline-replay-chart");
    if (!dom) return;
    if (klineReplayChart) klineReplayChart.dispose();
    klineReplayChart = echarts.init(dom);
    LC.bindChart(dom, klineReplayChart);

    var prices = klineData;
    var snapshots = tpl.weeklySnapshots || [];

    // Build trades (buy/sell markers) from signal history
    var trades = buildTrades(code, prices, snapshots);

    // Build position mountain series
    var posSeries = new Array(prices.dates.length).fill(0);
    var sigPtr = 0;
    var curPos = 0;
    for (var i = 0; i < prices.dates.length; i++) {
      var bd = prices.dates[i];
      while (sigPtr < snapshots.length && snapshots[sigPtr].date <= bd) {
        var p = (snapshots[sigPtr].positions || {})[code];
        curPos = p != null ? p : 0;
        sigPtr++;
      }
      posSeries[i] = curPos;
    }

    // Mark points for trades
    var markPoints = [];
    var barIdxToTrade = {};
    var dateToIdx = {};
    for (var i = 0; i < prices.dates.length; i++) dateToIdx[prices.dates[i]] = i;

    for (var t = 0; t < trades.length; t++) {
      var tr = trades[t];
      barIdxToTrade[tr.barIdx] = tr;
      var spec;
      if (tr.action === 'new')        spec = {color:'#10b981', up:true, size:13};
      else if (tr.action === 'adj_up') spec = {color:'#34d399', up:true, size:11};
      else if (tr.action === 'adj_down') spec = {color:'#fca5a5', up:false, size:11};
      else if (tr.action === 'out')   spec = {color:'#ef4444', up:false, size:13};
      else                            spec = {color:'#6b7280', up:true, size:9};
      markPoints.push({
        name: tr.action.toUpperCase().replace('_',' ') + ' ' + tr.pos.toFixed(0) + '%',
        coord: [prices.dates[tr.barIdx], prices.close[tr.barIdx]],
        symbol: 'triangle',
        symbolRotate: spec.up ? 0 : 180,
        symbolSize: spec.size,
        itemStyle: {color: spec.color, borderColor: '#0f1419', borderWidth: 1},
        label: {show: false},
      });
    }

    // Current date marker line
    var curDate = sig ? sig.date : null;

    // Tooltip formatter
    var actionLabel = {new:'🟢 NEW (新建仓)', adj_up:'🟩 加仓', adj_down:'🟥 减仓', out:'🔴 OUT (清仓)'};
    function fmtTooltip(params) {
      if (!params || !params.length) return '';
      var idx = params[0].dataIndex;
      var dateStr = prices.dates[idx];
      var price = prices.close[idx];
      var rsi = prices.rsi ? prices.rsi[idx] : null;
      var vol = prices.volume ? prices.volume[idx] : null;
      var pos = posSeries[idx];
      var html = '<div style="font-weight:600;margin-bottom:4px;color:#e0e0e0;">' + dateStr + '</div>';
      html += '<div style="color:#94a3b8;font-size:11px;line-height:1.6;">';
      html += '\u4ef7\u683c <b style="color:#e0e0e0">' + (price != null ? price.toFixed(3) : '-') + '</b><br/>';
      html += '\u5f53\u524d\u6301\u4ed3 <b style="color:' + (pos > 0 ? '#10b981' : '#6b7280') + '">' + pos.toFixed(1) + '%</b><br/>';
      if (rsi != null) html += 'RSI <b style="color:#f59e0b">' + rsi.toFixed(1) + '</b><br/>';
      if (vol != null) html += '\u6210\u4ea4 <b style="color:#e0e0e0">' + (vol >= 1e8 ? (vol/1e8).toFixed(2)+' \u4ebf' : vol >= 1e4 ? (vol/1e4).toFixed(1)+' \u4e07' : vol.toFixed(0)) + '</b>';
      html += '</div>';
      var tr2 = barIdxToTrade[idx];
      if (tr2) {
        html += '<div style="margin-top:6px;padding-top:6px;border-top:1px solid rgba(255,255,255,0.08);font-size:11px;">';
        html += (actionLabel[tr2.action] || tr2.action.toUpperCase()) + ' \u2192 \u4ed3\u4f4d <b style="color:#10b981">' + tr2.pos.toFixed(1) + '%</b>';
        html += '</div>';
      }
      return html;
    }

    klineReplayChart.setOption({
      tooltip: {
        trigger: 'axis',
        axisPointer: {type: 'cross'},
        backgroundColor: 'rgba(10,25,47,0.95)',
        borderColor: 'rgba(59,130,246,0.2)',
        textStyle: {color: '#e0e0e0', fontSize: 11},
        formatter: fmtTooltip,
      },
      axisPointer: {link: [{xAxisIndex: 'all'}]},
      legend: {
        data: [
          {name: '\u4ef7\u683c', icon: 'rect'},
          {name: '\u6301\u4ed3', icon: 'rect'},
        ],
        textStyle: {color: '#94a3b8', fontSize: 10},
        top: 0, right: 8,
      },
      grid: [
        {left: 50, right: 44, top: 28, bottom: 28},
      ],
      xAxis: [
        {type:'category', data:prices.dates, boundaryGap:false, axisLine:{lineStyle:{color:'rgba(255,255,255,0.06)'}}, axisLabel:{color:'#6b7280',fontSize:9}, splitLine:{show:false}},
      ],
      yAxis: [
        {scale:true, axisLabel:{color:'#6b7280',fontSize:9}, splitLine:{lineStyle:{color:'rgba(255,255,255,0.05)'}}},
        {position:'right', min:0, max:100, splitNumber:2,
          axisLabel:{color:'#10b981',fontSize:9, formatter:'{value}%'},
          splitLine:{show:false},
          axisLine:{show:true, lineStyle:{color:'rgba(255,255,255,0.06)'}},
        },
      ],
      visualMap: {
        show: false,
        seriesIndex: 1,
        pieces: [
          {gte: 30, color: 'rgba(16,185,129,0.18)'},
          {gte: 10, lt: 30, color: 'rgba(16,185,129,0.32)'},
          {gt: 0, lt: 10, color: 'rgba(16,185,129,0.50)'},
          {value: 0, color: 'rgba(255,255,255,0)'},
        ],
      },
      dataZoom: [
        {type:'inside', xAxisIndex:[0], start:0, end:100},
      ],
      series: [
        {
          name: '\u4ef7\u683c', type: 'line', data: prices.close, showSymbol: false,
          color: '#94a3b8',
          lineStyle: {color: '#94a3b8', width: 1.2},
          areaStyle: {color: 'rgba(148,163,184,0.08)'},
          markPoint: markPoints.length > 0 ? {data: markPoints, animation: false, z: 10} : undefined,
          markLine: curDate ? {
            silent: true, symbol: 'none',
            data: [{xAxis: curDate, lineStyle:{color:'#ef4444',width:1.5,type:'dashed'}}],
          label: {show: false},
        } : undefined,
      },
      {
        name: '\u6301\u4ed3', type: 'line',
        yAxisIndex: 1,
        color: '#10b981',
        data: posSeries,
        showSymbol: false,
        step: 'end',
        lineStyle: {color: 'rgba(16,185,129,0.55)', width: 1},
        areaStyle: {color: 'rgba(16,185,129,0.18)'},
        z: 1,
      },
    ],
  });

    // Click -> jump to snapshot
    klineReplayChart.on('click', function(params) {
      if (params.componentType === 'markPoint' && params.data) return;
      // Click on blank area: find nearest snapshot date
      if (params.dataIndex != null) {
        var clickDate = prices.dates[params.dataIndex];
        var bestIdx = 0;
        for (var j = 0; j < snapshots.length; j++) {
          if (snapshots[j].date <= clickDate) bestIdx = j;
        }
        renderSnapshot(tpl, bestIdx);
      }
    });

    setTimeout(function(){ LC.resizeAllCharts(); }, 200);
  }

  function buildTrades(code, prices, snapshots) {
    var dateToIdx = {};
    for (var i = 0; i < prices.dates.length; i++) dateToIdx[prices.dates[i]] = i;
    function findBarIdx(rbDate) {
      if (dateToIdx[rbDate] != null) return dateToIdx[rbDate];
      for (var k = 0; k < prices.dates.length; k++) {
        if (prices.dates[k] >= rbDate) return k;
      }
      return prices.dates.length - 1;
    }

    var trades = [];
    var prevPos = 0;
    for (var i = 0; i < snapshots.length; i++) {
      var sig = snapshots[i];
      var pos = (sig.positions || {})[code];
      if (pos == null) continue;
      var curPos = pos;
      var refinedAction = '';
      if (curPos > prevPos + 0.01)      refinedAction = prevPos === 0 ? 'new' : 'adj_up';
      else if (curPos < prevPos - 0.01) refinedAction = curPos === 0 ? 'out' : 'adj_down';
      if (refinedAction) {
        var barIdx = findBarIdx(sig.date);
        trades.push({barIdx: barIdx, pos: curPos, prevPos: prevPos, action: refinedAction, date: sig.date});
      }
      prevPos = curPos;
    }
    return trades;
  }
})();
