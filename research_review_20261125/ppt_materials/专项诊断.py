import json, pathlib, pandas as pd, numpy as np
from scipy.stats import spearmanr,kendalltau
from sklearn.metrics import mean_absolute_error,mean_squared_error,r2_score
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from collections import Counter
P=pathlib.Path('.'); R=P/'artifacts/reports'; O=P/'research_review_20261125'; J=lambda x:json.loads(pathlib.Path(x).read_text(encoding='utf-8-sig'))
plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei']; plt.rcParams['axes.unicode_minus']=False
raw=pd.read_csv(R/'s4-01-20261120/record-audit.csv',encoding='utf-8-sig'); assert raw.record_id.is_unique
ids=J(R/'s4-02-20261120-v1/all-view.json')['content']['common_record_ids']; cu=J(R/'s4-02-20261120-v1/cu-view.json')['content']['common_record_ids']; data=raw.set_index('record_id').loc[ids].copy(); assert len(data)==542 and set(cu)<=set(ids) and len(cu)==211
data['signature']=data.composition.apply(lambda s: json.dumps(sorted(json.loads(s)),ensure_ascii=False,separators=(',',':')))
def comp(s): return {(a,b):float(c)/100 for a,b,c in json.loads(s)}
data['cm']=data.composition.map(comp)
def sim(a,b): return max(0,1-sum(abs(a.get(k,0)-b.get(k,0)) for k in set(a)|set(b))/2)
def metric(y,p):
 return (mean_absolute_error(y,p),np.sqrt(mean_squared_error(y,p)),r2_score(y,p) if len(y)>1 and np.ptp(y)>0 else np.nan)
def fmt(x): return '—' if not np.isfinite(x) else f'{x:.3f}'
def tab(df):
 return '| ' + ' | '.join(map(str,df.columns)) + ' |\n| ' + ' | '.join(['---']*len(df.columns)) + ' |\n' + '\n'.join('| ' + ' | '.join(str(x).replace('|','/') for x in row) + ' |' for row in df.itertuples(index=False,name=None))
def arms(path): return {a['candidate_index']:{r['record_id']:r for r in a['predictions']} for a in J(path)}
def ok(r): return r['status'] in ('ok','caution') and r['raw_prediction'] is not None and np.isfinite(r['raw_prediction'])
def stats(q):
 a=q.conversion_pct; return [len(q),q.doi.nunique(),a.min(),a.median(),a.quantile(.75),a.max()]
L=[]
def add(s): L.append(s+'\n')
add('''## 专项诊断：材料识别与筛选（观察后分析）

以下均重新计算自 S4 冻结视图、原始记录审计与 S5 已保存留出预测；不重新训练。三种子成员重叠，同文献记录相关，结果不是独立外部验证。所有分组、阈值、相似度与排序评价均为事后探索，不能作显著性或部署准确率保证。

### 共同母池分布与特征宽度

S4 全体系共同资格 542 条、铜基视图 211 条；铜基是全体系的子集，不是额外样本。配方由来源角色、物种及 mol% 的完整列表定义，仍不能等同于实测结构、独立制备批次或催化体系族。''')
t=[]
for label,q in [('全体系',data),('铜基',data.loc[cu]),('非铜基',data.drop(cu))]:
 v=stats(q);t.append([label,*v[:2],len(set(q.signature)),*[round(x,2) for x in v[2:]]])
add(tab(pd.DataFrame(t,columns=['范围','记录','DOI','名义配方数','转化率最小','中位','P75','最大'])))
cols=['temperature_k','pressure_bar_abs','h2_co2_ratio','flow_nl_g_h']; names=['温度 K','绝压 bar','H2/CO2','流量 NL/g/h']; rows=[]
for label,q in [('全体系',data),('铜基',data.loc[cu])]:
 for col,name in zip(cols,names):
  a=q[col].dropna(); rows.append([label,name,len(a),*[round(x,3) for x in [a.min(),a.quantile(.25),a.median(),a.quantile(.75),a.max()]]])
add('\n'+tab(pd.DataFrame(rows,columns=['范围','变量','n','最小','P25','中位','P75','最大'])))
for label,q in [('全体系',data),('铜基',data.loc[cu])]:
 c=Counter();
 for x in q.composition:
  for role,species,v in json.loads(x):
   if role=='compound' and v>0:c[species]+=1
 add(f'\n{label}来源活性角色中出现次数最高的物种（多标签，可重叠）：'+ '、'.join(f'{k} {v} 条' for k,v in c.most_common(10))+'。')
fig,ax=plt.subplots(2,3,figsize=(12,7));
for j,(col,label) in enumerate(zip(['conversion_pct']+cols,['转化率 (%)']+names)):
 ax.flat[j].hist(data[col].dropna(),bins=18,alpha=.55,label='全体系'); ax.flat[j].hist(data.loc[cu,col].dropna(),bins=18,alpha=.65,label='铜基'); ax.flat[j].set(xlabel=label,ylabel='记录数');
ax.flat[0].legend(); ax.flat[5].axis('off'); fig.suptitle('共同母池与铜基子集：分布并非互斥'); fig.tight_layout();fig.savefig(O/'专项_数据分布.png',dpi=160);plt.close(fig)
add('\n![全体系与铜基分布](专项_数据分布.png)')
add('''
S5-02 保存的全训练拟合包实际 `n_features_in_`（包含缺角色占位及适用标志，非原始测量变量个数）：

| 范围/种子 | F_cond | F_base | F1 | F2 | F3-P | F3-H | F3-I | Cu 扩展 B2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 全体系 45 | 4 | 38 | 42 | 48 | 18 | 52 | 21 | — |
| 全体系 46 | 4 | 39 | 43 | 49 | 18 | 53 | 21 | — |
| 全体系 47 | 4 | 37 | 41 | 47 | 18 | 51 | 21 | — |
| 铜基 45 | 4 | 19 | 23 | 29 | 18 | 33 | 21 | 37 |
| 铜基 46 | 4 | 21 | 25 | 31 | 18 | 35 | 21 | 39 |
| 铜基 47 | 4 | 20 | 24 | 30 | 18 | 34 | 21 | 38 |

Cu B2 在铜基 F_base 上增加 18 列；各训练折词表可能更短。宽度从可信已保存模型包读取，不重拟合。''')
add('### F_cond 与 F_base：严格共同留出配对\n\n固定 ET，种子相同、同一留出成员；两臂均 ok/caution 且有限预测的交集计算 MAE、RMSE、R²。覆盖分别以 108 条为分母。ΔMAE = F_cond − F_base，正值表示组成特征改善。')
rows=[]; per=[]
for s in [45,46,47]:
 aa=arms(R/f's5-02-e01-seed{s}-range-v2/run/holdout/all_arms.json'); b,c=aa[0],aa[1]; both=[i for i in b if ok(b[i]) and ok(c[i])]; y=np.array([b[i]['observed'] for i in both]); bp=np.array([b[i]['raw_prediction'] for i in both]); cp=np.array([c[i]['raw_prediction'] for i in both]); bm=metric(y,bp); cm=metric(y,cp); rows.append([s,len(both),sum(map(ok,c.values())),sum(map(ok,b.values())),*[round(v,3) for v in cm],*[round(v,3) for v in bm],round(cm[0]-bm[0],3)])
 for i,yy,bb,cc in zip(both,y,bp,cp): per.append({'seed':s,'record_id':i,'observed':yy,'base':bb,'cond':cc,'gain':abs(cc-yy)-abs(bb-yy),**data.loc[i,['classification','temperature_k','pressure_bar_abs','h2_co2_ratio','flow_nl_g_h','doi']].to_dict()})
add(tab(pd.DataFrame(rows,columns=['种子','共同n','cond可用/108','base可用/108','cond MAE','cond RMSE','cond R²','base MAE','base RMSE','base R²','ΔMAE'])))
per=pd.DataFrame(per); per['温度层']=pd.cut(per.temperature_k,[-np.inf,500,550,600,np.inf],labels=['<500','500–<550','550–<600','≥600'],right=False); per['目标层']=pd.cut(per.observed,[-np.inf,5,10,20,np.inf],labels=['<5','5–<10','10–<20','≥20'],right=False)
for by in ['classification','温度层','目标层']:
 t=per.groupby(['seed',by],observed=True).agg(n=('gain','size'),gain=('gain','mean')).reset_index(); t['gain']=t.gain.round(3); add(f'\n分层：{by}；正值表示 F_base 较 F_cond 的 MAE 改善。\n\n'+tab(t))
per.to_csv(O/'专项_Fcond配对.csv',index=False,encoding='utf-8-sig')
add('### 排序能力：先定义可评价条件\n\n以每个留出种子、同一 DOI、四项工况数值完全相同为组；将组内相同名义配方的重复记录的实测和预测取均值，仅保留至少 3 个不同配方、实测及预测均有变化的组。Spearman ρ、Kendall τ-b 按组计算后等权平均；Top-1 命中为预测最高配方是否为唯一实测最高配方；若最高实测或预测存在并列则 Top-1 不计入。分组只比较同文献且工况完全相同的留出记录，不是前瞻性新配方盲筛；Top-2 召回率为预测前二与实测前二交集数除以二，边界并列的组不计算。因各算法可能产生常数预测或并列，各自可算组数不同，跨算法平均值不是完全配对。排除组数及结果在表中。所有四算法使用五臂（ET、RF、GB、XGB、F_cond）严格共同可用记录，以便可比。')
ranking=[]; examples=[]; modelmetrics=[]; allhold=[]
for s in [45,46,47]:
 fixed=arms(R/f's5-04-e02-20261124-v1/fixed-{s}/holdout/all_arms.json'); e05=arms(R/f's5-05-e05-20261124-v1/run-{s}/holdout/all_arms.json'); e01=arms(R/f's5-02-e01-seed{s}-range-v2/run/holdout/all_arms.json'); models={'ET':fixed[0],'RF':fixed[1],'GB':fixed[2],'XGB':e05[6],'F_cond':e01[1]}; common=set.intersection(*[set(k for k,v in d.items() if ok(v)) for d in models.values()]); assert all(abs(models['ET'][k]['observed']-data.loc[k,'conversion_pct'])<1e-7 for k in common)
 train=J(R/f's5-05-e05-20261124-v1/run-{s}/split.json')['train']; tr=data.loc[train]; trdoi=set(tr.doi); trsig=set(tr.signature)
 hold=data.loc[sorted(common)].copy(); hold['seed']=s; hold['sim']=hold.cm.apply(lambda c:max(sim(c,x) for x in tr.cm)); hold['same_formula']=hold.signature.isin(trsig); hold['same_doi']=hold.doi.isin(trdoi)
 for name,d in models.items(): hold[name]=[d[i]['raw_prediction'] for i in hold.index]
 allhold.append(hold.reset_index())
 groupcols=['doi']+cols; groups=list(hold.groupby(groupcols,dropna=False));
 for name in models:
  valid=[]; hits=[]; top2=[]; candidates=0; n_ge3=0; ties=0
  for key,g in groups:
   h=g.groupby('signature',as_index=False).agg(y=('conversion_pct','mean'),p=(name,'mean'),n=('conversion_pct','size'))
   if len(h)<3: continue
   n_ge3+=1; candidates+=len(h)
   if h.y.nunique()<2 or h.p.nunique()<2: continue
   rho=spearmanr(h.y,h.p)[0]; tau=kendalltau(h.y,h.p)[0]; valid.append((rho,tau))
   if (h.y==h.y.max()).sum()==1 and (h.p==h.p.max()).sum()==1: hits.append(int(h.y.idxmax()==h.p.idxmax()))
   else: ties+=1
   if len(h)>=3 and h.y.nlargest(2).iloc[-1] > h.y.nlargest(3).iloc[-1] and h.p.nlargest(2).iloc[-1] > h.p.nlargest(3).iloc[-1]: top2.append(len(set(h.y.nlargest(2).index) & set(h.p.nlargest(2).index))/2)
   if name=='ET': examples.append([s,key[0],*key[1:],len(h),round(rho,3),round(tau,3),hits[-1] if (h.y==h.y.max()).sum()==1 and (h.p==h.p.max()).sum()==1 else None])
  ranking.append([s,name,len(common),len(groups),n_ge3,candidates,len(valid),np.mean([x[0] for x in valid]) if valid else np.nan,np.mean([x[1] for x in valid]) if valid else np.nan,len(hits),sum(hits),ties,len(top2),np.mean(top2) if top2 else np.nan])
  for layer,sel in [('全部',hold),('高值≥20%',hold[hold.conversion_pct>=20])]:
   if len(sel):
    mm=metric(sel.conversion_pct,sel[name]); modelmetrics.append([s,name,layer,len(sel),*mm,(sel[name]-sel.conversion_pct).mean()])
rank=pd.DataFrame(ranking,columns=['种子','算法','共同n','工况组数','≥3配方组','配方数合计','可算组','Spearman均值','Kendall均值','Top1可算组','Top1命中组','Top1并列排除','Top2可算组','Top2平均召回']); rank.to_csv(O/'专项_排序.csv',index=False,encoding='utf-8-sig'); add('\n'+tab(rank.round(3)))
if not rank['可算组'].sum(): add('\n在严格条件下没有可计算排序的组，因此无法从这些留出预测判断材料排名与 Top-1 筛选能力。')
else: add('\n上述组的候选数、来源数与观察后选取均限制外推；不能将记录加权当作独立实验。')
add('\n### 算法对高值与整体的表现\n\n固定参数 F_base：ET/RF/GB 来自 S5-04，XGB 来自 S5-E05；严格五臂交集。高值阈值为观察后设定的实测 ≥20%，不是筛选门槛的科学标准。R²在目标方差为零时不定义。')
mm=pd.DataFrame(modelmetrics,columns=['种子','算法','区间','n','MAE','RMSE','R²','平均残差']); mm.to_csv(O/'专项_模型分层.csv',index=False,encoding='utf-8-sig'); add('\n'+tab(mm.round(3)))
hold=pd.concat(allhold); hold['残差']=hold.ET-hold.conversion_pct; hold['绝对误差']=abs(hold['残差']); hold['温度层']=pd.cut(hold.temperature_k,[-np.inf,500,550,600,np.inf],labels=['<500','500–<550','550–<600','≥600'],right=False); hold['相似度层']=pd.cut(hold.sim,[-.001,.5,.8,.95,1.001],labels=['<0.5','0.5–<0.8','0.8–<0.95','≥0.95'],right=False); hold['目标层']=pd.cut(hold.conversion_pct,[-np.inf,5,10,20,np.inf],labels=['<5','5–<10','10–<20','≥20'],right=False);
add('\n### 误差、配方邻域与工况\n\n相似度定义为 1 − ½×角色-物种材料 mol% 向量的 L1 距离，按 100 归一；每个留出记录只和该种子训练集比较，取最大值。1 表示名义配方完全相同，未包含结构或工况相似性。重复种子不合并为独立样本；相同 DOI 表示训练见过来源，而非见过该配方。以下均为五臂共同可用集的 ET。')
for col in ['目标层','温度层','classification','相似度层','same_formula','same_doi']:
 t=hold.groupby(['seed',col],observed=True).agg(n=('ET','size'),MAE=('绝对误差','mean'),bias=('残差','mean')).reset_index(); add(f'\n按 {col} 分层：\n\n'+tab(t.round(3)))
# other operating ranges with explicit count
for col,edges in [('pressure_bar_abs',[-np.inf,10,30,50,np.inf]),('h2_co2_ratio',[-np.inf,3,4,np.inf]),('flow_nl_g_h',[-np.inf,2,5,10,np.inf])]:
 hold[col+'_bin']=pd.cut(hold[col],edges,right=False); t=hold.groupby(['seed',col+'_bin'],observed=True).agg(n=('ET','size'),MAE=('绝对误差','mean'),bias=('残差','mean')).reset_index(); t[col+'_bin']=t[col+'_bin'].astype(str); add(f'\n按 {col} 分层：\n\n'+tab(t.round(3)))
add('\n高值记录逐条审计：以下表保留原样本名称、来源、工况、域状态及与训练配方的最大相似度；相似度高不保证附近工况有实验。完整记录及最近邻信息见 CSV。')
high=hold[hold.conversion_pct>=20].copy();
for idx,r in high.iterrows():
 tr=data.loc[J(R/f"s5-05-e05-20261124-v1/run-{int(r.seed)}/split.json")['train']]; scores=tr.cm.apply(lambda c:sim(r.cm,c)); best=scores.idxmax(); high.loc[idx,'nearest_id']=best; high.loc[idx,'nearest_doi']=tr.loc[best,'doi']; high.loc[idx,'nearest_conditions']=str([tr.loc[best,c] for c in cols]); high.loc[idx,'status']=arms(R/f"s5-05-e05-20261124-v1/run-{int(r.seed)}/holdout/all_arms.json")[0][r.record_id]['status']
high.drop(columns=['cm'],errors='ignore').to_csv(O/'专项_高值逐条.csv',index=False,encoding='utf-8-sig');
if len(high): add('\n'+tab(high[['seed','record_id','doi','sample_name','temperature_k','pressure_bar_abs','h2_co2_ratio','flow_nl_g_h','conversion_pct','ET','残差','sim','same_doi','status']].round(3)))
fig,axs=plt.subplots(1,2,figsize=(11,4));
for s,g in hold.groupby('seed'):
 axs[0].scatter(g.conversion_pct,g['残差'],s=15,alpha=.55,label=str(s)); axs[1].scatter(g.sim,g['绝对误差'],s=15,alpha=.55,label=str(s))
axs[0].axhline(0,color='black',lw=.8);axs[0].axvline(20,color='grey',ls='--');axs[0].set(xlabel='实测转化率 (%)',ylabel='ET 预测 − 实测（百分点）');axs[1].set(xlabel='训练集最大名义配方相似度',ylabel='ET 绝对误差（百分点）');axs[0].legend(title='种子');fig.tight_layout();fig.savefig(O/'专项_高值与相似度.png',dpi=160);plt.close(fig)
add('\n![高值偏差与训练配方相似度](专项_高值与相似度.png)')
add('''

解释边界：高值偏差只描述所列观察后子集；树模型均值回归、训练高值稀缺、配方和来源混杂均是可能解释，不能从相关性确定原因。比较只使用入口共同可用样本，遗漏的拒绝记录仍是筛选风险。以上模型的排序是在严格交集上针对已发表、同来源相同工况做的事后检验；即使局部排序良好，也不能证明其能识别未知材料或可靠推荐全新配方。应以独立来源、盲法和实际候选集合验证排序、Top-K 和覆盖，且对每个候选保留实验确认。

数据与计算来源：[共同视图](../artifacts/reports/s4-02-20261120-v1/all-view.json)、[铜基视图](../artifacts/reports/s4-02-20261120-v1/cu-view.json)、[记录审计](../artifacts/reports/s4-01-20261120/record-audit.csv)、[S5-02 逐臂预测](../artifacts/reports/s5-02-e01-seed45-range-v2/run/holdout/all_arms.json)、[S5-04 逐臂预测](../artifacts/reports/s5-04-e02-20261124-v1/fixed-45/holdout/all_arms.json)、[S5-E05 逐臂预测](../artifacts/reports/s5-05-e05-20261124-v1/run-45/holdout/all_arms.json)。计算及全部种子路径见 [诊断脚本](专项诊断.py)。
''')
# Additional evidence at the same grain; avoid pooling dependent seeds.
add('\n### 来源与高值的补充统计\n\n下表 DOI 分层仅列每个种子共同可用集里不少于 3 条的来源，未见 DOI 组在随机划分中不存在。')
doi=hold.groupby(['seed','doi']).agg(n=('ET','size'),MAE=('绝对误差','mean'),bias=('残差','mean')).reset_index(); doi=doi[doi.n>=3]; doi.to_csv(O/'专项_DOI误差.csv',index=False,encoding='utf-8-sig'); add('\n'+tab(doi.round(3)))
if len(high):
 t=high.groupby('seed').agg(n=('ET','size'),平均残差=('残差','mean'),低估数=('残差',lambda x:(x<0).sum()),同名义配方数=('same_formula','sum'),同DOI数=('same_doi','sum')).reset_index(); add('\n实测 ≥20% 的高值记录按预测减实测统计（重复种子不可相加）：\n\n'+tab(t.round(3)))
fig,axs=plt.subplots(1,2,figsize=(11,4));
for i,s in enumerate([45,46,47]):
 g=per[per.seed==s]; axs[0].bar(i,g.gain.mean(),color='#348491'); axs[0].text(i,g.gain.mean(),f'{g.gain.mean():.3f}',ha='center',va='bottom')
axs[0].set_xticks(range(3)); axs[0].set_xticklabels(['45','46','47']); axs[0].set(xlabel='种子',ylabel='MAE 改善（百分点）',title='F_cond − F_base，共同可用集');axs[0].axhline(0,color='black',lw=.7)
for j,name in enumerate(['ET','RF','GB','XGB']):
 q=rank[rank['算法']==name]; axs[1].plot(q['种子'],q['Spearman均值'],marker='o',label=name)
axs[1].axhline(0,color='black',lw=.7);axs[1].set_xticks([45,46,47]);axs[1].set(xlabel='种子',ylabel='组等权 Spearman',title='同 DOI、完全相同工况；可算组不同');axs[1].legend();fig.tight_layout();fig.savefig(O/'专项_组成和排序.png',dpi=160);plt.close(fig)
add('\n![配方特征增益与有限排序结果](专项_组成和排序.png)')
(O/'专项诊断补充.md').write_text('\n'.join(L),encoding='utf8'); print('generated',len(hold),'ranking',rank[['种子','算法','≥3配方组','可算组','Top1可算组','Top1命中组']].to_string(index=False)); print('high',len(high)); print('paired',rows)





