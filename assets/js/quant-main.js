/**
 * REQ-177 M3.1 v2: quant-main.js
 * 多模板量化回测可视化 - 模板切换 + 净值曲线click联动快照
 *
 * 数据结构: window.__QUANT_RUNTIME__ = {
 *   templateMeta: { conservative: {label, description}, ... },
 *   templates: { conservative: {summary, navSeries, hs300Pct, drawdownSeries, signalHistory, ...}, ... },
 *   config: { conservative: {scoring, confidence, position, factors}, ... },
 *   etfNameMap: { "512400": "有色金属ETF", ... },
 * }
 */
(function () {
  "use strict";

  var Q = window.__QUANT_RUNTIME__;
  if (!Q) { console.warn("[quant-main] __QUANT_RUNTIME__ not found"); return; }

  var LC = window.__etfChartLifecycle || { bindChart: function(){}, resizeAllCharts: function(){} };

  // ── Colors ────────────────────────────────────────────────
  var C = {
    green: "#10b981", red: "#ef4444", blue: "#3b82f6",
    orange: "#f59e0b", cyan: "#06b6d4", purple: "#8b5cf6",
    gray: "#64748b", text: "#e0e0e0", muted: "#94a3b8",
    gridLine: "rgba(255,255,255,0.06)",
  };
  var PALETTE = [C.blue, C.green, C.orange, C.red, C.cyan, C.purple, "#ec4899", "#a78bfa", "#34d399", "#fbbf24"];

  function baseAxis() {
    return { axisLine:{lineStyle:{color:C.gridLine}}, axisTick:{show:false}, axisLabel:{color:C.muted,fontSize:11}, splitLine:{lineStyle:{color:C.gridLine}} };
  }
  function baseTooltip() {
    return { backgroundColor:"rgba(10,25,47,0.92)", borderColor:"rgba(59,130,246,0.2)", textStyle:{color:C.text,fontSize:12} };
  }

  // ── State ─────────────────────────────────────────────────
  var activeTemplate = "baseline";
  var navChart = null;  // keep reference for click binding
  var initialized = false;

  // ── Public API ────────────────────────────────────────────
  window.__initQuantPanel = function () {
    if (!initialized) {
      initialized = true;
      renderAll();
    } else {
      setTimeout(function(){ LC.resizeAllCharts(); }, 200);
    }
  };

  window.__switchQuantTemplate = function (tid) {
    if (!Q.templates[tid]) return;
    activeTemplate = tid;

    // Update button active state
    document.querySelectorAll("#quant-template-buttons .nav-tab").forEach(function(b){ b.classList.remove("active"); });
    var btn = document.getElementById("quant-tpl-btn-" + tid);
    if (btn) btn.classList.add("active");

    renderAll();
  };

  // ── Master render ─────────────────────────────────────────
  function renderAll() {
    var tpl = Q.templates[activeTemplate];
    if (!tpl) {
      console.warn('[quant-main] Template not found:', activeTemplate);
      return;
    }

    renderTemplateDesc();
    renderParams();
    renderMetricCards(tpl);
    renderNavChart(tpl);
    renderDrawdownChart(tpl);
    renderSnapshot(tpl, tpl.weeklySnapshots.length - 1);  // latest week
    renderFreqBar(tpl);
    renderLatestSignal(tpl);
    renderRiskOrders(tpl);
    renderFooter();

    setTimeout(function(){ LC.resizeAllCharts(); }, 300);
  }

  // ── Template description ──────────────────────────────────
  function renderTemplateDesc() {
    var el = document.getElementById("quant-template-desc");
    if (!el) return;
    var meta = Q.templateMeta[activeTemplate];
    el.textContent = meta ? meta.description : "";
  }

  // ── Params ────────────────────────────────────────────────
  function renderParams() {
    var cfg = Q.config[activeTemplate];
    var grid = document.getElementById("quant-param-grid");
    if (!grid || !cfg) return;

    var groups = [
      { id:"quant-param-weights", title:"因子权重", items:[
        ["EMA 偏离度",(cfg.scoring.weights.ema_deviation*100).toFixed(0)+"%"],
        ["RSI 自适应",(cfg.scoring.weights.rsi_adaptive*100).toFixed(0)+"%"],
        ["方向性量比",(cfg.scoring.weights.volume_ratio*100).toFixed(0)+"%"],
        ["偏好加成",cfg.scoring.bias_bonus+" 分"],
      ]},
      { id:"quant-param-confidence", title:"信心函数", items:[
        ["函数类型",cfg.confidence.type],
        ["死区阈值","< "+cfg.confidence.dead_zone+" 分"],
        ["满配阈值",">= "+cfg.confidence.full_zone+" 分"],
      ]},
      { id:"quant-param-position", title:"仓位控制", items:[
        ["最大持仓",cfg.position.max_holdings+" 支"],
        ["离散化步长",(cfg.position.discretize_step*100).toFixed(0)+"%"],
      ]},
      { id:"quant-param-factors", title:"因子参数", items:[
        ["EMA周期",cfg.factors.ema.period_weeks+" 周"],
        ["RSI周期",cfg.factors.rsi.period_days+" 日"],
        ["量比窗口",cfg.factors.volume_ratio.window_days+" 日"],
      ]},
    ];

    var cs='background:rgba(17,34,64,0.55);border:1px solid rgba(59,130,246,0.1);border-radius:12px;padding:18px;';
    var ts='font-size:14px;color:#3b82f6;margin:0 0 14px;font-weight:600;';
    var rs='display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04);';

    var html="";
    for(var g=0;g<groups.length;g++){
      html+='<div id="'+groups[g].id+'" style="'+cs+'"><h3 style="'+ts+'">'+groups[g].title+'</h3>';
      for(var p=0;p<groups[g].items.length;p++){
        var last=p===groups[g].items.length-1;
        var r=last?rs.replace('border-bottom:1px solid rgba(255,255,255,0.04);',''):rs;
        html+='<div style="'+r+'"><span style="font-size:13px;color:#94a3b8;">'+groups[g].items[p][0]+'</span><span style="font-size:13px;color:#e0e0e0;font-weight:600;font-family:monospace;">'+groups[g].items[p][1]+'</span></div>';
      }
      html+='</div>';
    }
    grid.innerHTML=html;
  }

  // ── Metric Cards ──────────────────────────────────────────
  function renderMetricCards(tpl) {
    var s=tpl.summary;
    // First row: 4 primary metrics
    var map=[
      {id:"quant-metric-total-return-value",v:s.totalReturn.toFixed(2)+"%",pos:s.totalReturn>=0},
      {id:"quant-metric-annual-return-value",v:s.annualReturn.toFixed(2)+"%",pos:s.annualReturn>=0},
      {id:"quant-metric-max-drawdown-value",v:s.maxDrawdown.toFixed(2)+"%",pos:false},
      {id:"quant-metric-sharpe-value",v:s.sharpe.toFixed(2),pos:s.sharpe>=1},
    ];
    for(var i=0;i<map.length;i++){
      var el=document.getElementById(map[i].id);
      if(el){el.textContent=map[i].v;el.style.color=map[i].pos?C.green:C.red;}
    }
    // Extended metrics (rendered below the 4 cards)
    var ext=document.getElementById("quant-metric-extended");
    if(ext){
      ext.innerHTML=
        '<span>Sortino <b style="color:'+C.text+'">'+s.sortino.toFixed(2)+'</b></span>'+
        '<span>Calmar <b style="color:'+C.text+'">'+s.calmar.toFixed(2)+'</b></span>'+
        '<span>日胜率 <b style="color:'+C.text+'">'+s.winRate.toFixed(1)+'%</b></span>'+
        '<span>月胜率 <b style="color:'+C.text+'">'+s.monthlyWinRate.toFixed(1)+'%</b></span>'+
        '<span>最佳月 <b style="color:'+C.green+'">+'+s.bestMonth.toFixed(1)+'%</b></span>'+
        '<span>最差月 <b style="color:'+C.red+'">'+s.worstMonth.toFixed(1)+'%</b></span>'+
        '<span>连涨 <b style="color:'+C.text+'">'+s.maxWinStreak+'日</b></span>'+
        '<span>连跌 <b style="color:'+C.text+'">'+s.maxLossStreak+'日</b></span>';
    }
  }

  // ── NAV Chart (with click → snapshot) ─────────────────────
  function renderNavChart(tpl) {
    var dom=document.getElementById("quant-nav-chart");
    if(!dom) return;

    if(navChart){navChart.dispose();}
    navChart=echarts.init(dom);
    LC.bindChart(dom,navChart);

    var dates=tpl.navSeries.dates;
    var navPct=tpl.navSeries.nav;
    var benchPct=tpl.navSeries.hs300||(function(){var a=[];for(var i=0;i<dates.length;i++)a.push(100);return a;})();
    var eqPct=tpl.navSeries.eqWeight||null;

    navChart.setOption({
      tooltip:Object.assign(baseTooltip(),{trigger:"axis",axisPointer:{type:"line",lineStyle:{color:"rgba(255,255,255,0.6)",width:1}},formatter:function(params){
        var d=params[0].axisValue;
        var out='<div style="font-weight:600;margin-bottom:4px">'+d+'</div>';
        for(var i=0;i<params.length;i++) out+='<div>'+params[i].marker+' '+params[i].seriesName+': '+params[i].value.toFixed(2)+'%</div>';
        return out;
      }}),
      legend:{data:["策略净值","沪深300","等权持有"],textStyle:{color:C.muted,fontSize:11},top:4,
        formatter:function(name){if(name==="等权持有")return"等权持有(25支买入不动)";return name;}},
      grid:{left:56,right:20,top:40,bottom:32},
      xAxis:Object.assign(baseAxis(),{type:"category",data:dates,boundaryGap:false}),
      yAxis:Object.assign(baseAxis(),{type:"value",name:"净值(%)",nameTextStyle:{color:C.muted,fontSize:11}}),
      series:[
        {name:"策略净值",type:"line",data:navPct,showSymbol:false,
          lineStyle:{color:C.blue,width:3},
          areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:"rgba(59,130,246,0.25)"},{offset:1,color:"rgba(59,130,246,0.02)"}])},
          itemStyle:{color:C.blue},
        },
        {name:"沪深300",type:"line",data:benchPct,showSymbol:false,
          lineStyle:{color:C.orange,width:1.5,type:"dashed"},itemStyle:{color:C.orange}},
        {name:"等权持有",type:"line",data:eqPct||[],showSymbol:false,
          lineStyle:{color:C.purple,width:1.5,type:"dotted"},itemStyle:{color:C.purple}},
      ],
      dataZoom:[{type:"inside",start:0,end:100}],
    });

    // Click anywhere on chart area → find nearest rebalance date and show snapshot
    navChart.getZr().on("click",function(params){
      var pointInPixel=[params.offsetX,params.offsetY];
      if(!navChart.containPixel("grid",pointInPixel)) return;
      var dataIdx=navChart.convertFromPixel({seriesIndex:0},pointInPixel)[0];
      if(dataIdx==null||dataIdx<0||dataIdx>=dates.length) return;
      var clickDate=dates[Math.round(dataIdx)];
      // Find nearest signal at or before this date
      var bestIdx=0;
      for(var i=0;i<tpl.weeklySnapshots.length;i++){
        if(tpl.weeklySnapshots[i].date<=clickDate) bestIdx=i;
      }
      renderSnapshot(tpl,bestIdx);
    });
  }

  // ── Drawdown Chart ────────────────────────────────────────
  function renderDrawdownChart(tpl) {
    var dom=document.getElementById("quant-drawdown-chart");
    if(!dom) return;
    var chart=echarts.init(dom);
    LC.bindChart(dom,chart);

    chart.setOption({
      tooltip:Object.assign(baseTooltip(),{trigger:"axis",formatter:function(p){return p[0].axisValue+'<br/>'+p[0].marker+' 回撤: '+p[0].value.toFixed(2)+'%';}}),
      grid:{left:56,right:20,top:24,bottom:32},
      xAxis:Object.assign(baseAxis(),{type:"category",data:tpl.drawdownSeries.dates,boundaryGap:false}),
      yAxis:Object.assign(baseAxis(),{type:"value",name:"回撤(%)",nameTextStyle:{color:C.muted,fontSize:11}}),
      series:[{type:"line",data:tpl.drawdownSeries.drawdown,showSymbol:false,
        lineStyle:{color:C.red,width:1.5},
        areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:"rgba(239,68,68,0.3)"},{offset:1,color:"rgba(239,68,68,0.02)"}])},
        itemStyle:{color:C.red}}],
      dataZoom:[{type:"inside",start:0,end:100}],
    });
  }

  // ── Snapshot (week drill-down) ────────────────────────────
  function renderSnapshot(tpl, sigIdx) {
    var sig=tpl.weeklySnapshots[sigIdx];
    if(!sig) return;

    // Update subtitle
    var sub=document.getElementById("quant-snapshot-subtitle");
    if(sub) sub.textContent=sig.date+" · 第 "+(sig.index+1)+" 次调仓 · 平均信心 "+(sig.avgConfidence*100).toFixed(0)+"% · 总仓位 "+(sig.totalTarget*100).toFixed(0)+"%";

    // Ranking table
    renderSnapshotRanking(sig);
    // Position bar chart
    renderSnapshotPositionChart(sig);
  }

  function renderSnapshotRanking(sig) {
    var container=document.getElementById("quant-snapshot-ranking");
    if(!container) return;

    var scores=sig.scores;
    var sorted=Object.keys(scores).sort(function(a,b){return scores[b]-scores[a];});
    var maxScore=scores[sorted[0]]||1;

    var html='<table style="width:100%;border-collapse:collapse;font-size:13px;"><thead><tr>'+
      '<th style="text-align:left;padding:8px 10px;color:#94a3b8;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">#</th>'+
      '<th style="text-align:left;padding:8px 10px;color:#94a3b8;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">ETF</th>'+
      '<th style="text-align:left;padding:8px 10px;color:#94a3b8;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">综合分</th>'+
      '<th style="text-align:left;padding:8px 10px;color:#94a3b8;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">仓位</th>'+
      '<th style="text-align:left;padding:8px 10px;color:#94a3b8;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">状态</th>'+
      '</tr></thead><tbody>';

    for(var i=0;i<sorted.length;i++){
      var code=sorted[i];
      var score=scores[code];
      var pos=sig.positions[code]||0;
      var inTop6=sig.top6.indexOf(code)>=0;
      var name=Q.etfNameMap[code]||code;
      var barW=Math.round(score/maxScore*100);
      var badge=inTop6?'<span style="background:rgba(16,185,129,0.15);color:#10b981;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:600;">TOP6</span>':'';

      html+='<tr style="border-bottom:1px solid rgba(255,255,255,0.03);">'+
        '<td style="padding:6px 10px;color:'+C.muted+'">'+( i+1)+'</td>'+
        '<td style="padding:6px 10px;"><span style="color:'+C.blue+';font-weight:600;font-size:12px;">'+code+'</span> <span style="color:'+C.text+';font-size:12px;">'+name+'</span></td>'+
        '<td style="padding:6px 10px;">'+score.toFixed(1)+
          '<span style="width:60px;height:5px;background:rgba(255,255,255,0.06);border-radius:3px;display:inline-block;vertical-align:middle;margin-left:6px;">'+
          '<span style="display:block;height:100%;border-radius:3px;background:linear-gradient(90deg,#3b82f6,#10b981);width:'+barW+'%"></span></span></td>'+
        '<td style="padding:6px 10px;color:'+(pos>0?C.green:C.muted)+';font-weight:600;font-size:12px;">'+(pos>0?(pos*100).toFixed(1)+'%':'-')+'</td>'+
        '<td style="padding:6px 10px;">'+badge+'</td>'+
        '</tr>';
    }
    html+='</tbody></table>';
    container.innerHTML=html;
  }

  function renderSnapshotPositionChart(sig) {
    var dom=document.getElementById("quant-snapshot-position-chart");
    if(!dom) return;
    var chart=echarts.init(dom);
    LC.bindChart(dom,chart);

    var positions=sig.positions;
    var codes=Object.keys(positions).filter(function(c){return positions[c]>0;});
    codes.sort(function(a,b){return positions[b]-positions[a];});

    var names=[],values=[];
    for(var i=0;i<codes.length;i++){
      names.push(Q.etfNameMap[codes[i]]||codes[i]);
      values.push(Math.round(positions[codes[i]]*1000)/10);
    }

    chart.setOption({
      tooltip:Object.assign(baseTooltip(),{formatter:function(p){return p.name+': '+p.value+'%';}}),
      grid:{left:110,right:32,top:8,bottom:24},
      xAxis:Object.assign(baseAxis(),{type:"value",max:function(v){return Math.ceil(v.max/5)*5;},name:"%"}),
      yAxis:Object.assign(baseAxis(),{type:"category",data:names.reverse(),axisLabel:{width:100,overflow:"truncate",color:C.text,fontSize:12}}),
      series:[{type:"bar",data:values.reverse(),barWidth:16,
        itemStyle:{color:new echarts.graphic.LinearGradient(0,0,1,0,[{offset:0,color:C.blue},{offset:1,color:C.green}]),borderRadius:[0,4,4,0]},
        label:{show:true,position:"right",color:C.muted,fontSize:11,formatter:"{c}%"}}],
    });
  }

  // ── Sector Pie ────────────────────────────────────────────
  function renderSectorPie(tpl) {
    var dom=document.getElementById("quant-sector-chart");
    if(!dom) return;
    var chart=echarts.init(dom);
    LC.bindChart(dom,chart);

    var sd=tpl.sectorDistribution;
    if(!sd||sd.length===0) return;

    var data=[];
    for(var i=0;i<sd.length;i++){
      data.push({value:sd[i].weight,name:sd[i].sector,itemStyle:{color:PALETTE[i%PALETTE.length]}});
    }

    chart.setOption({
      tooltip:Object.assign(baseTooltip(),{formatter:function(p){return p.name+': '+p.value.toFixed(1)+'%';}}),
      series:[{type:"pie",radius:["36%","68%"],center:["50%","50%"],data:data,
        label:{color:C.text,fontSize:12,formatter:"{b}\n{d}%"},
        labelLine:{lineStyle:{color:C.gridLine}},
        emphasis:{itemStyle:{shadowBlur:10,shadowColor:"rgba(0,0,0,0.4)"}},
        itemStyle:{borderRadius:6,borderColor:"rgba(10,25,47,0.8)",borderWidth:2}}],
    });
  }

  // ── Freq Bar ──────────────────────────────────────────────
  function renderFreqBar(tpl) {
    var dom=document.getElementById("quant-freq-chart");
    if(!dom) return;
    var chart=echarts.init(dom);
    LC.bindChart(dom,chart);

    var freq=tpl.rebalanceFreq;
    if(!freq||freq.length===0) return;

    var top=freq.slice(0,12);
    var names=[],counts=[];
    for(var i=top.length-1;i>=0;i--){names.push(top[i].name);counts.push(top[i].count);}

    chart.setOption({
      tooltip:Object.assign(baseTooltip(),{formatter:function(p){return p.name+': '+p.value+' 次';}}),
      grid:{left:100,right:32,top:8,bottom:24},
      xAxis:Object.assign(baseAxis(),{type:"value",name:"入选次数"}),
      yAxis:Object.assign(baseAxis(),{type:"category",data:names}),
      series:[{type:"bar",data:counts,barWidth:14,
        itemStyle:{color:new echarts.graphic.LinearGradient(0,0,1,0,[{offset:0,color:C.blue},{offset:1,color:C.green}]),borderRadius:[0,4,4,0]},
        label:{show:true,position:"right",color:C.muted,fontSize:11,formatter:"{c}"}}],
    });
  }

  // ── Latest Signal (M4.2 position recommendation) ──────────
  function renderLatestSignal(tpl) {
    var container=document.getElementById("quant-latest-signal-table");
    var subtitle=document.getElementById("quant-latest-signal-subtitle");
    if(!container) return;

    var sig=tpl.latestSignal;
    if(!sig||!sig.holdings||sig.holdings.length===0){
      container.innerHTML='<p style="color:#64748b">暂无最新信号数据</p>';
      return;
    }

    if(subtitle) subtitle.textContent="数据截止: "+sig.date+" 收盘 · 平均信心: "+(sig.avgConfidence*100).toFixed(0)+"% · 目标总仓位: "+sig.totalTarget.toFixed(1)+"% · 现金: "+sig.cashTarget.toFixed(1)+"% · 最大持仓: "+sig.maxHoldings+"支";

    var html='<table style="width:100%;border-collapse:collapse;font-size:13px;"><thead><tr>'+
      '<th style="text-align:left;padding:10px 10px;color:#94a3b8;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">#</th>'+
      '<th style="text-align:left;padding:10px 10px;color:#94a3b8;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">ETF</th>'+
      '<th style="text-align:left;padding:10px 10px;color:#94a3b8;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">行业</th>'+
      '<th style="text-align:center;padding:10px 10px;color:#94a3b8;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">综合分</th>'+
      '<th style="text-align:center;padding:10px 10px;color:#94a3b8;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">信心度</th>'+
      '<th style="text-align:center;padding:10px 10px;color:#94a3b8;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">目标仓位</th>'+
      '<th style="text-align:center;padding:10px 10px;color:#94a3b8;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">现价</th>'+
      '<th style="text-align:center;padding:10px 10px;color:#94a3b8;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">标记</th>'+
      '</tr></thead><tbody>';

    for(var i=0;i<sig.holdings.length;i++){
      var h=sig.holdings[i];
      var confPct=(h.confidence*100).toFixed(0);
      var confColor=h.confidence>=0.8?C.green:h.confidence>=0.5?C.orange:C.muted;
      var badges='';
      if(h.bias) badges+='<span style="background:rgba(245,158,11,0.15);color:#f59e0b;padding:2px 6px;border-radius:4px;font-size:10px;margin-left:4px;">偏好</span>';

      html+='<tr style="border-bottom:1px solid rgba(255,255,255,0.03);">'+
        '<td style="padding:8px 10px;color:'+C.muted+'">'+(i+1)+'</td>'+
        '<td style="padding:8px 10px;"><span style="color:'+C.blue+';font-weight:600;font-size:12px;">'+h.code+'</span> <span style="color:'+C.text+';font-size:12px;">'+h.name+'</span></td>'+
        '<td style="padding:8px 10px;color:'+C.muted+';font-size:12px;">'+h.sector+'</td>'+
        '<td style="padding:8px 10px;text-align:center;color:'+C.text+';font-weight:600;">'+h.score.toFixed(1)+'</td>'+
        '<td style="padding:8px 10px;text-align:center;color:'+confColor+';font-weight:600;">'+confPct+'%</td>'+
        '<td style="padding:8px 10px;text-align:center;color:'+C.green+';font-weight:700;font-size:14px;">'+h.position.toFixed(1)+'%</td>'+
        '<td style="padding:8px 10px;text-align:center;color:'+C.text+';">'+h.price.toFixed(3)+'</td>'+
        '<td style="padding:8px 10px;text-align:center;">'+badges+'</td>'+
        '</tr>';
    }
    html+='</tbody></table>';
    container.innerHTML=html;
  }

  // ── Risk Orders (M4.2) ─────────────────────────────────────
  function renderRiskOrders(tpl) {
    var container=document.getElementById("quant-risk-orders-table");
    var subtitle=document.getElementById("quant-risk-orders-subtitle");
    if(!container) return;

    var ro=tpl.riskOrders;
    if(!ro||!ro.orders||ro.orders.length===0){
      container.innerHTML='<p style="color:#64748b">暂无风控挂单数据</p>';
      return;
    }

    if(subtitle) subtitle.textContent="基于 "+ro.date+" 调仓信号 · Top-6 门槛分: "+ro.thresholdScore.toFixed(1)+" · 假设 RSI/量比不变，仅通过价格变动反推临界点";

    var html='<table style="width:100%;border-collapse:collapse;font-size:13px;"><thead><tr>'+
      '<th style="text-align:left;padding:10px 10px;color:#94a3b8;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">ETF</th>'+
      '<th style="text-align:center;padding:10px 10px;color:#94a3b8;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">综合分</th>'+
      '<th style="text-align:center;padding:10px 10px;color:#94a3b8;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">现价</th>'+
      '<th style="text-align:center;padding:10px 10px;color:#94a3b8;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">EMA</th>'+
      '<th style="text-align:center;padding:10px 10px;color:#94a3b8;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">仓位</th>'+
      '<th style="text-align:center;padding:10px 10px;color:#ef4444;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">止损价</th>'+
      '<th style="text-align:center;padding:10px 10px;color:#10b981;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">止盈价</th>'+
      '<th style="text-align:center;padding:10px 10px;color:#3b82f6;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">买入价</th>'+
      '<th style="text-align:center;padding:10px 10px;color:#94a3b8;border-bottom:1px solid rgba(59,130,246,0.15);font-size:11px;">状态</th>'+
      '</tr></thead><tbody>';

    for(var i=0;i<ro.orders.length;i++){
      var o=ro.orders[i];
      var badge=o.inTop6?
        '<span style="background:rgba(16,185,129,0.15);color:#10b981;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:600;">持仓</span>':
        '<span style="background:rgba(59,130,246,0.15);color:#3b82f6;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:600;">候补</span>';

      var slCell=o.stopLoss?
        '<span style="color:#ef4444;font-weight:600">'+o.stopLoss.toFixed(3)+'</span><br><span style="font-size:10px;color:#94a3b8">'+o.stopLossPct.toFixed(1)+'%</span>':'-';
      var tpCell=o.takeProfit?
        '<span style="color:#10b981;font-weight:600">'+o.takeProfit.toFixed(3)+'</span><br><span style="font-size:10px;color:#94a3b8">+'+o.takeProfitPct.toFixed(1)+'%</span>':'-';
      var buyCell=o.buyPrice?
        '<span style="color:#3b82f6;font-weight:600">'+o.buyPrice.toFixed(3)+'</span><br><span style="font-size:10px;color:#94a3b8">'+((o.buyPricePct>=0?'+':'')+o.buyPricePct.toFixed(1))+'%</span>':'-';

      html+='<tr style="border-bottom:1px solid rgba(255,255,255,0.03);">'+
        '<td style="padding:8px 10px;"><span style="color:'+C.blue+';font-weight:600;font-size:12px;">'+o.code+'</span> <span style="color:'+C.text+';font-size:12px;">'+o.name+'</span></td>'+
        '<td style="padding:8px 10px;text-align:center;color:'+C.text+'">'+o.currentScore.toFixed(1)+'</td>'+
        '<td style="padding:8px 10px;text-align:center;color:'+C.text+';font-weight:600">'+o.currentPrice.toFixed(3)+'</td>'+
        '<td style="padding:8px 10px;text-align:center;color:'+C.muted+'">'+o.ema.toFixed(3)+'</td>'+
        '<td style="padding:8px 10px;text-align:center;color:'+(o.position>0?C.green:C.muted)+';font-weight:600">'+(o.position>0?o.position.toFixed(1)+'%':'-')+'</td>'+
        '<td style="padding:8px 10px;text-align:center">'+slCell+'</td>'+
        '<td style="padding:8px 10px;text-align:center">'+tpCell+'</td>'+
        '<td style="padding:8px 10px;text-align:center">'+buyCell+'</td>'+
        '<td style="padding:8px 10px;text-align:center">'+badge+'</td>'+
        '</tr>';
    }
    html+='</tbody></table>';
    container.innerHTML=html;
  }

  // ── Footer ────────────────────────────────────────────────
  function renderFooter() {
    var el=document.getElementById("quant-generated-at");
    if(el&&Q.generatedAt) el.textContent=Q.generatedAt.replace("T"," ").substring(0,19);
  }
})();
