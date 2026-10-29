"""Paired proper scores with cluster bootstrap; no profitability inference."""
import math
import random
from collections import defaultdict
from statistics import mean
from .core import probability


def scores(ps, ys):
    if not ps or len(ps)!=len(ys) or any(y not in (0,1) for y in ys):raise ValueError('invalid_scoring_rows')
    ps=[probability(p) for p in ps]
    clipped=[min(1-1e-12,max(1e-12,p)) for p in ps]
    bins=[]
    for i in range(5):
        pairs=[(p,y) for p,y in zip(ps,ys) if min(4,int(p*5))==i]
        bins.append({'lower':i/5,'n':len(pairs),'mean_p':mean(p for p,y in pairs) if pairs else None,
                     'observed':mean(y for p,y in pairs) if pairs else None})
    return {'n':len(ps),'brier':mean((p-y)**2 for p,y in zip(ps,ys)),
            'log_loss':-mean(y*math.log(p)+(1-y)*math.log1p(-p) for p,y in zip(clipped,ys)), 'reliability':bins}


def compare(rows,baseline,challenger,seed=231,replicates=2000):
    if not rows:return {'status':'no_valid_comparisons','n':0}
    clusters=defaultdict(list)
    for r in rows:
        a,b=probability(r['predictions'][baseline]),probability(r['predictions'][challenger])
        clusters[r['cluster']].append((a-r['y'])**2-(b-r['y'])**2)
    values=list(clusters.values());rng=random.Random(seed)
    samples=[]
    for _ in range(replicates):
        sample=[v for block in rng.choices(values,k=len(values)) for v in block]
        samples.append(mean(sample))
    samples.sort()
    return {'status':'descriptive_research_only','n':len(rows),'clusters':len(values),
            'baseline':scores([r['predictions'][baseline] for r in rows],[r['y'] for r in rows]),
            'challenger':scores([r['predictions'][challenger] for r in rows],[r['y'] for r in rows]),
            'brier_improvement':mean(v for block in values for v in block),
            'cluster_bootstrap_95_interval': [samples[int(.025*replicates)],samples[int(.975*replicates)]] if len(values)>=20 else None,
            'interval_note':'Exploratory percentile interval, not multiplicity adjusted; suppressed below 20 clusters.',
            'seed':seed,'replicates':replicates,'superiority_claim':False}
