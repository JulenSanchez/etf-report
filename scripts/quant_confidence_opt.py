#!/usr/bin/env python3
"""Optimize confidence params: ma_bull_pos, ma_bear_pos, dead_zone, full_zone."""
import argparse, json, sys; from datetime import datetime; from pathlib import Path; import numpy as np
sys.stdout.reconfigure(encoding="utf-8")
SKILL_DIR = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(SKILL_DIR / "scripts"))
import optuna
from quant_backtest import run_backtest
from quant_data_utils import load_etf_data as _load_etf_data
from benchmark_data import load_hs300_daily_cached, build_hs300_weekly, build_ma_trend_cache
RESULTS_DIR = SKILL_DIR / "research" / "strategy" / "confidence"

def preload(preset):
    cfg=_load_cfg(preset); u=cfg["universe"]; d=str(SKILL_DIR/"data"/"quant"); ad={}; aw={}
    for e in u:
        c=e["code"]; dl,wl=_load_etf_data(c,d)
        if dl is not None: ad[c]=dl
        if wl is not None: aw[c]=wl
    hd=load_hs300_daily_cached(); hw=build_hs300_weekly(hd) if hd is not None else None
    hm=build_ma_trend_cache(hd,hw,period=24)
    return {"all_daily":ad,"all_weekly":aw,"hs300_above_ma":hm}
def _load_cfg(p):
    import yaml
    with (SKILL_DIR/"config"/"quant_universe.yaml").open("r",encoding="utf-8") as f: return yaml.safe_load(f)

def bs(dr,n=1000):
    nd=len(dr); f=np.empty(n)
    for i in range(n): idx=np.random.randint(0,nd,size=nd); f[i]=np.prod(1.0+dr[idx])
    return f

def ev(bull,bear,dz,fz,preset,prel):
    ov={"confidence":{"ma_bull_pos":bull,"ma_bear_pos":bear,"dead_zone":int(dz),"full_zone":int(fz)}}
    nv,_,_=run_backtest("2020-05-27","2026-05-26",preset=preset,preloaded=prel,config_override=ov,return_details=False,return_debug=False)
    dr=nv["nav"].pct_change().dropna().values; nd=len(dr); y=nd/252; nav=nv["nav"].values
    tr=(nav[-1]/nav[0]-1)*100; dd=(nav-np.maximum.accumulate(nav))/np.maximum.accumulate(nav)*100; mdd=float(dd.min())
    ann=((nav[-1]/nav[0])**(1/y)-1)*100; mu=float(np.mean(dr))*252; sd=float(np.std(dr))
    dn=dr[dr<0]; ss=float(np.std(dn))*np.sqrt(252) if len(dn)>0 else sd*np.sqrt(252)
    so=(mu-0.02)/ss if ss>0 else 0; ca=ann/abs(mdd) if abs(mdd)>0 else 0; sc=so*ca
    f=bs(dr); med=float(np.median(f)); ru=float(np.mean(f<1))*100
    return {"ma_bull":round(bull,2),"ma_bear":round(bear,2),"dead_zone":int(dz),"full_zone":int(fz),
            "total":round(tr,2),"mdd":round(mdd,2),"sortino":round(so,2),"calmar":round(ca,2),"sc":round(sc,2),"ruin":round(ru,2)}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--preset",default="preset1"); p.add_argument("--trials",type=int,default=40); a=p.parse_args()
    RESULTS_DIR.mkdir(parents=True,exist_ok=True)
    print(f"Confidence Opt — {a.preset} | Trials: {a.trials}")
    prel=preload(a.preset); all_t=[]
    def obj(t):
        bull=t.suggest_float("ma_bull_pos",0.5,1.0); bear=t.suggest_float("ma_bear_pos",0.05,0.5)
        dz=t.suggest_int("dead_zone",10,40); fz=t.suggest_int("full_zone",40,80)
        if fz<=dz+10: fz=dz+10
        m=ev(round(bull,2),round(bear,2),dz,fz,a.preset,prel); m["trial"]=t.number; all_t.append(m)
        for k in["total","sortino","ruin"]: t.set_user_attr(k,m[k])
        print(f"    [{t.number+1}/{a.trials}] bull={m['ma_bull']} bear={m['ma_bear']} DZ={m['dead_zone']} FZ={m['full_zone']}  S×C={m['sc']:.1f} total={m['total']:+.1f}% sortino={m['sortino']:.2f}")
        return m["sc"]
    s=optuna.create_study(direction="maximize",sampler=optuna.samplers.TPESampler(seed=42,n_startup_trials=10))
    s.optimize(obj,n_trials=a.trials,show_progress_bar=False)
    best=all_t[s.best_trial.number]; ref=ev(1.0,0.3,25,65,a.preset,prel)
    print(f"\n{'='*80}\n  Confidence Optimization — {a.preset}\n{'='*80}")
    print(f"\n  Optimal: bull={best['ma_bull']} bear={best['ma_bear']} DZ={best['dead_zone']} FZ={best['full_zone']}")
    print(f"    S×C={best['sc']:.1f} sortino={best['sortino']:.2f} total={best['total']:+.1f}% MDD={best['mdd']:.1f}%")
    print(f"\n  Preset1 ref (bull=1.0 bear=0.3 DZ=25 FZ=65):")
    print(f"    S×C={ref['sc']:.1f} sortino={ref['sortino']:.2f} total={ref['total']:+.1f}% MDD={ref['mdd']:.1f}%")
    st=sorted(all_t,key=lambda t:t["sc"],reverse=True)
    print(f"\n  Top 10:\n  {'R':<4} {'bull':<6} {'bear':<6} {'DZ':<5} {'FZ':<5} {'S×C':>6} {'Sortino':>7} {'Total%':>8} {'MDD%':>7}")
    for i,t in enumerate(st[:10]):
        m=" <-- OPT" if i==0 else ""
        print(f"  {i+1:<4} {t['ma_bull']:<6} {t['ma_bear']:<6} {t['dead_zone']:<5} {t['full_zone']:<5} {t['sc']:>5.1f}  {t['sortino']:>6.2f}  {t['total']:>+7.1f}% {t['mdd']:>6.1f}%{m}")
    out={"preset":a.preset,"optimal":{k:best[k] for k in["ma_bull","ma_bear","dead_zone","full_zone","sc","sortino","total","mdd"]},"ref":{k:ref[k] for k in["ma_bull","ma_bear","dead_zone","full_zone","sc","sortino","total","mdd"]},"all_trials":st}
    with (RESULTS_DIR/"results.json").open("w",encoding="utf-8") as f: json.dump(out,f,ensure_ascii=False,indent=2)
    print(f"\n  Saved.\n{'='*80}\n")

if __name__=="__main__": raise SystemExit(main())
