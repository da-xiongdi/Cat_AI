import json,pathlib,math
import numpy as np,pandas as pd
from scipy.stats import spearmanr,kendalltau
from sklearn.metrics import mean_absolute_error,mean_squared_error,r2_score
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
P=pathlib.Path('.'); R=P/'artifacts/reports'; O=P/'research_review_20261125'; J=lambda p:json.loads(pathlib.Path(p).read_text(encoding='utf-8-sig'))
plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei'];plt.rcParams['axes.unicode_minus']=False
raw=pd.read_csv(R/'s4-01-20261120/record-audit.csv',encoding='utf-8-sig').set_index('record_id'); assert raw.index.is_unique
raw['signature']=raw.composition.apply(lambda x:json.dumps(sorted(json.loads(x)),ensure_ascii=False,separators=(',',':')))
cols=['doi','temperature_k','pressure_bar_abs','h2_co2_ratio','flow_nl_g_h']; names=['Extra Trees','Random Forest','Gradient Boosting','XGBoost','Ridge','Dummy']; primary=names[:4]
def arms(path):return {x['candidate_index']:{r['record_id']:r for r in x['predictions']} for x in J(path)}
def ok(r):return r['status'] in ('ok','caution') and r['raw_prediction'] is not None and math.isfinite(r['raw_prediction'])
def table(df):
 def v(x):
  if pd.isna(x): return '—'
  if isinstance(x,(float,np.floating)):return f'{x:.3f}'
  return str(x).replace('|','/')
 return '| '+' | '.join(df.columns)+' |\n| '+' | '.join(['---']*len(df.columns))+' |\n'+'\n'.join('| '+' | '.join(v(x) for x in row)+' |' for row in df.itertuples(index=False,name=None))
metrics=[]; highs=[]; groupdetails=[]; grouped=[]; membership=[]; discrepancies=[]
for s in [45,46,47]:
 fdir=R/f's5-04-e02-20261124-v1/fixed-{s}'; edir=R/f's5-05-e05-20261124-v1/run-{s}'
 fcfg=J(fdir/'config.json'); ecfg=J(edir/'config.json'); split=J(fdir/'split.json'); esplit=J(edir/'split.json'); assert split==esplit
 for key in ['view','snapshot','split','split_sha256','target','model_seed','catalog_database']: assert fcfg[key]==ecfg[key],key
 assert fcfg['candidates'][0]==ecfg['candidates'][0] and fcfg['candidates'][1]==ecfg['candidates'][3]
 assert all(x['feature']=='F_base' for x in fcfg['candidates']) and ecfg['candidates'][6]['feature']=='F_base' and ecfg['candidates'][6]['model']=='xgboost'
 a=arms(fdir/'holdout/all_arms.json'); b=arms(edir/'holdout/all_arms.json'); assert a[0]==b[0] and a[1]==b[3]
 models={names[0]:a[0],names[1]:a[1],names[2]:a[2],names[3]:b[6],names[4]:a[4],names[5]:a[3]}
 test=set(split['test']);assert len(test)==108 and all(set(v)==test for v in models.values())
 ids=sorted(set.intersection(*[set(k for k,v in d.items() if ok(v)) for d in models.values()])); assert len(ids)>0
 for i in ids:
  y=raw.loc[i,'conversion_pct']; assert all(abs(d[i]['observed']-y)<1e-7 and d[i]['doi']==raw.loc[i,'doi'] for d in models.values())
  membership.append({'seed':s,'record_id':i,'doi':raw.loc[i,'doi'],**{n:models[n][i]['raw_prediction'] for n in names}})
 hold=raw.loc[ids].copy()
 for n,d in models.items(): hold[n]=[d[i]['raw_prediction'] for i in ids]
 for n,d in models.items():
  y=hold.conversion_pct; p=hold[n]; e=p-y
  metrics.append([s,n,len(ids),sum(ok(r) for r in d.values()),mean_absolute_error(y,p),np.sqrt(mean_squared_error(y,p)),r2_score(y,p)])
  h=hold[hold.conversion_pct>=20]; delta=h[n]-h.conversion_pct
  highs.append([s,n,len(h),mean_absolute_error(h.conversion_pct,h[n]) if len(h) else np.nan,delta.mean(),int((delta<0).sum()),int((delta>0).sum()),int((delta==0).sum())])
 gs=[]
 for key,g in hold.groupby(cols,dropna=False):
  ag={'conversion_pct':'mean'};ag.update({n:'mean' for n in names}); h=g.groupby('signature',as_index=False).agg(ag)
  if len(h)>=3 and h.conversion_pct.nunique()>1: gs.append((key,h))
 eligible=[(k,h) for k,h in gs if all(h[n].nunique()>1 for n in primary)]
 top1=[(k,h) for k,h in eligible if (h.conversion_pct==h.conversion_pct.max()).sum()==1 and all((h[n]==h[n].max()).sum()==1 for n in primary)]
 top2=[(k,h) for k,h in eligible if h.conversion_pct.nlargest(2).iloc[-1]>h.conversion_pct.nlargest(3).iloc[-1] and all(h[n].nlargest(2).iloc[-1]>h[n].nlargest(3).iloc[-1] for n in primary)]
 for name in names:
  rankvalid=[(k,h) for k,h in eligible if h[name].nunique()>1]; # Dummy remains undefined
  one=[(k,h) for k,h in top1 if (h[name]==h[name].max()).sum()==1]
  two=[(k,h) for k,h in top2 if h[name].nlargest(2).iloc[-1]>h[name].nlargest(3).iloc[-1]]
  grouped.append([s,name,len(ids),len(gs),len(eligible),len(rankvalid),np.mean([spearmanr(h.conversion_pct,h[name])[0] for k,h in rankvalid]) if rankvalid else np.nan,np.mean([kendalltau(h.conversion_pct,h[name])[0] for k,h in rankvalid]) if rankvalid else np.nan,len(top1),len(one),sum(int(h.conversion_pct.idxmax()==h[name].idxmax()) for k,h in one) if one else np.nan,len(top2),len(two),np.mean([len(set(h.conversion_pct.nlargest(2).index)&set(h[name].nlargest(2).index))/2 for k,h in two]) if two else np.nan])
 for key,h in gs:
  groupdetails.append({'seed':s,'doi':key[0],'temperature_k':key[1],'pressure_bar_abs':key[2],'h2_co2_ratio':key[3],'flow_nl_g_h':key[4],'n_formulations':len(h),'four_rank_common':any(key==k for k,_ in eligible),'four_top1_common':any(key==k for k,_ in top1),'four_top2_common':any(key==k for k,_ in top2),**{f'{n}_rho':spearmanr(h.conversion_pct,h[n])[0] if h[n].nunique()>1 else np.nan for n in names},**{f'{n}_tau':kendalltau(h.conversion_pct,h[n])[0] if h[n].nunique()>1 else np.nan for n in names}})
 print(s,'common',len(ids),'eligible groups',len(gs),len(eligible),len(top1),len(top2))
m=pd.DataFrame(metrics,columns=['种子','算法','共同n','各自可用n','MAE','RMSE','R²']);h=pd.DataFrame(highs,columns=['种子','算法','高值n','MAE','平均残差','低估数','高估数','相等数']);r=pd.DataFrame(grouped,columns=['种子','算法','共同记录n','候选组','四算法相关共同组','算法可算组','Spearman','Kendall','四算法Top1共同组','算法Top1可算组','Top1命中','四算法Top2共同组','算法Top2可算组','Top2平均召回'])
for df,filename in [(m,'算法统一_指标.csv'),(h,'算法统一_高值.csv'),(r,'算法统一_排序.csv'),(pd.DataFrame(groupdetails),'算法统一_排序逐组.csv'),(pd.DataFrame(membership),'算法统一_共同留出预测.csv')]:df.to_csv(O/filename,index=False,encoding='utf-8-sig')
fig,axs=plt.subplots(2,2,figsize=(13,8));x=np.arange(3); colors=plt.cm.tab10(np.linspace(0,1,6));
for i,n in enumerate(names):
 q=m[m['算法']==n].sort_values('种子');
 for ax,col in zip(axs.flat,['MAE','RMSE','R²','各自可用n']): ax.plot(x,q[col],marker='o',label=n,color=colors[i])
for ax,title in zip(axs.flat,['共同集 MAE（百分点）','共同集 RMSE（百分点）','共同集 R²','各臂入口可用条数 / 108']):ax.set_xticks(x);ax.set_xticklabels([45,46,47]);ax.set(xlabel='种子',title=title);ax.grid(alpha=.2)
axs[0,0].legend(fontsize=8,ncol=2);fig.tight_layout();fig.savefig(O/'算法统一_多种子.png',dpi=160);plt.close(fig)
fig,axs=plt.subplots(1,2,figsize=(12,4));
for i,n in enumerate(names):
 q=h[h['算法']==n].sort_values('种子');axs[0].plot(x,q.MAE,marker='o',label=n,color=colors[i]);axs[1].plot(x,q['平均残差'],marker='o',label=n,color=colors[i])
for ax,title in zip(axs,['高值子集 MAE','高值子集平均残差（预测 − 实测）']):ax.set_xticks(x);ax.set_xticklabels([45,46,47]);ax.set(xlabel='种子',ylabel='百分点',title=title);ax.grid(alpha=.2)
axs[1].axhline(0,color='black',lw=.8);axs[0].legend(fontsize=8,ncol=2);fig.tight_layout();fig.savefig(O/'算法统一_高值.png',dpi=160);plt.close(fig)
fig,axs=plt.subplots(1,2,figsize=(11,4));
for i,n in enumerate(primary):
 q=r[r['算法']==n].sort_values('种子');axs[0].plot(x,q.Spearman,marker='o',label=n,color=colors[i]);axs[1].plot(x,q.Kendall,marker='o',label=n,color=colors[i])
for ax,title in zip(axs,['Spearman ρ','Kendall τ-b']):ax.set_xticks(x);ax.set_xticklabels([45,46,47]);ax.set(xlabel='种子',ylabel='组等权相关系数',title=title);ax.axhline(0,color='black',lw=.7);ax.grid(alpha=.2)
axs[0].legend(fontsize=8);fig.suptitle('四算法都可计算的严格共同排序组，组数见表');fig.tight_layout();fig.savefig(O/'算法统一_排序.png',dpi=160);plt.close(fig)
L=[]
def add(x):L.append(x+'\n')
add('''## 六算法统一留出比较：补充诊断

本节是观察后对已有预测的重算，不重新训练、不重新选模。S5-04 固定臂包含 Extra Trees（ET）、Random Forest（RF）、Gradient Boosting（GB）、Ridge、Dummy；S5-E05 提供固定 XGBoost（XGB）。三种子两阶段配置的视图、快照、目标、目录、模型种子以及完整训练／留出成员和训练内五折划分逐项一致；同参数 ET、RF 的两个阶段留出预测和状态逐条一致。固定模型均使用 F_base；ET/RF 为 100 树、叶最小 2、深度不限、max_features=1，GB 和 XGB 均 100 树、深度 3、学习率 0.1，Ridge alpha=1，Dummy 为训练均值。算法实现、处理流程和各自适用状态仍不同；这不是同一阶段预先登记的六算法联合实验。已观察留出数据、反复研究、种子成员重叠和文献相关性限制结论，非独立外部验证。

### 整体误差和覆盖率

每个种子取六臂共同 ok/caution 且预测有限的严格交集，所有 MAE、RMSE、R² 在同一成员上重新计算；“各自可用”以各自 108 条留出为分母，不能用各自可用集分数替代共同集作排名。R² 取决于同一共同集目标方差，误差单位为 CO2 转化率百分点。''')
add(table(m));add('\n![统一算法多种子比较](算法统一_多种子.png)')
add('''
### 严格共同排序组

同一种子、同一 DOI、温度、绝压、H2/CO2 和流量完全相同的六臂共同可用记录构成组；先对相同名义配方的重复记录取实测和预测均值，要求至少三个配方且实测有变化。Spearman 和 Kendall τ-b 仅使用四个主要算法都具有非恒定预测的相同组，按组等权。Top-1 进一步要求实测和四算法预测最高值均不并列；Top-2 要求实测和四算法的第 2 与第 3 名均不并列，召回率为预测前二与实测前二交集除以 2。Ridge 在这些四算法共同组上作为参照，若其自身恒定或边界并列则不计相应指标；Dummy 为恒定预测，相关系数与 Top-K 均不可定义，不作零分。各指标的共同组可以不同，表内注明分母。各组涉及的 DOI、工况、配方数及相关系数见 [逐组数据](算法统一_排序逐组.csv)。
''')
add(table(r));add('\n![严格共同排序组比较](算法统一_排序.png)')
add('''
### 高转化率子集

以同一六臂共同记录中实测转化率 ≥20% 定义高值；此阈值是观察后诊断，不是预设的应用标准。平均残差为预测减实测，低估数以严格小于零计。各算法同一种子的分母相同；种子间不能累加为独立样本。
''');add(table(h));add('\n![统一高值表现](算法统一_高值.png)')
add('''
### 如何理解 GB 的误差与排序

MAE 衡量预测值距实测值的绝对偏差；排序相关性只衡量同组内相对顺序，对某组内共同偏移或单调尺度变化不敏感。因此一个模型可以产生较大的绝对误差、同时较好地区分同条件下的高低，也可能因预测并列而无法排序。比较应以本节四算法相同排序组为准：上一节各模型各自可算组不同的相关系数不构成公平配对。在同一共同留出集上，GB 的 MAE 比 ET 分别高 0.082、0.160、0.074；但 GB 的 RMSE 在种子 45、47 较低，R² 相应较高。严格共同排序组上的 GB / ET Spearman 分别为 0.724 / 0.750（2 组）、1.000 / −0.500（1 组）、0.457 / 0.261（3 组）。这只说明 46、47 的极少数组中 GB 的相对顺序较好，45 则相反；种子 45 没有四算法共同可算 Top-1 组。共同组数量太少，不能据此认定 GB 的排序优势或推荐更换模型。MAE、排序指标、Top-K 的目标及权重各异；本分析不将任何留出结果用于重新选模。

来源：[S5-04 固定臂运行](../artifacts/reports/s5-04-e02-20261124-v1/)、[S5-E05 运行](../artifacts/reports/s5-05-e05-20261124-v1/)、[共同预测与 ID](算法统一_共同留出预测.csv)、[可复核计算脚本](算法统一分析.py)。各阶段固定参数及划分以其配置和 split 文件为准。''')
(O/'算法统一补充.md').write_text('\n'.join(L),encoding='utf-8');print('done')

