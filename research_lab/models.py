"""Small, auditable comparators. All fitting is confined to earlier outcomes."""
import math
from statistics import mean, pstdev
from .core import number, probability


def sigmoid(z):
    return 1/(1+math.exp(-max(-40,min(40,z))))


def logit(p):
    p=min(1-1e-9,max(1e-9,probability(p)))
    return math.log(p/(1-p))


def logistic_offset(train, features, baseline, *, epochs=300, penalty=0.1):
    """Ridge logistic adjustment to fixed legacy probability; train-only scaling."""
    if len(train)<20:raise ValueError('insufficient_training:20_required')
    width=len(features)
    if not width or any(len(r['features'])!=width for r in train):raise ValueError('feature_shape')
    centers=[mean(r['features'][i] for r in train) for i in range(width)]
    scales=[max(1e-6,pstdev(r['features'][i] for r in train)) for i in range(width)]
    standardized=lambda x:[1.]+[(number(v)-c)/s for v,c,s in zip(x,centers,scales)]
    xs=[standardized(r['features']) for r in train];weights=[0.]*(width+1)
    for _ in range(epochs):
        grad=[0.]*(width+1)
        for r,x in zip(train,xs):
            error=sigmoid(logit(r['baseline'])+sum(w*v for w,v in zip(weights,x)))-r['y']
            for i,v in enumerate(x):grad[i]+=error*v/len(train)
        weights=[w-0.05*(g+(penalty*w if i else 0)) for i,(w,g) in enumerate(zip(weights,grad))]
    return sigmoid(logit(baseline)+sum(w*v for w,v in zip(weights,standardized(features))))


def exceedance(mu, sigma, threshold):
    mu,sigma,threshold=map(number,(mu,sigma,threshold))
    if sigma<=0:raise ValueError('nonpositive_scale')
    return 0.5*math.erfc((threshold-mu)/(sigma*math.sqrt(2)))


def weather(train, deterministic, members, threshold):
    if len(train)<20:raise ValueError('insufficient_training:20_required')
    members=[number(v) for v in members]
    if len(members)<2:raise ValueError('ensemble_members_required')
    det_errors=[r['actual']-r['deterministic'] for r in train]
    ens_errors=[r['actual']-mean(r['members']) for r in train]
    det_sigma=max(0.25,pstdev(det_errors))
    # Spread calibration by training residual RMS relative to ensemble spread.
    floor=0.25
    ratio=math.sqrt(mean((e-mean(ens_errors))**2/max(floor**2,pstdev(r['members'])**2)
                         for e,r in zip(ens_errors,train)))
    ens_sigma=max(floor,pstdev(members)*ratio)
    return {'public_calibrated':exceedance(number(deterministic)+mean(det_errors),det_sigma,threshold),
            'ensemble_calibrated':exceedance(mean(members)+mean(ens_errors),ens_sigma,threshold),
            'ensemble_mean_fixed_variance':exceedance(mean(members)+mean(ens_errors),max(floor,pstdev(ens_errors)),threshold),
            'climatology':(sum(r['actual']>threshold for r in train)+1)/(len(train)+2)}


def monthly_changes(values, target_period):
    rows=sorted(values,key=lambda x:x['date'])
    if any(r['date']>=target_period for r in rows):raise ValueError('target_or_future_period_in_features')
    if len({r['date'] for r in rows})!=len(rows):raise ValueError('duplicate_period')
    result=[]
    for a,b in zip(rows,rows[1:]):
        ay,am=map(int,a['date'][:7].split('-'));by,bm=map(int,b['date'][:7].split('-'))
        if by*12+bm!=ay*12+am+1:raise ValueError('monthly_gap')
        if number(a['value'])<=0 or number(b['value'])<=0:raise ValueError('nonpositive_index')
        result.append(100*(number(b['value'])/number(a['value'])-1))
    if len(result)<3:raise ValueError('insufficient_vintage_history')
    # Target must be the immediately following month, not an arbitrary future horizon.
    ty,tm=map(int,target_period[:7].split('-'));ly,lm=map(int,rows[-1]['date'][:7].split('-'))
    if ty*12+tm!=ly*12+lm+1:raise ValueError('unsupported_forecast_horizon')
    return result


def finance(train, changes, threshold):
    if len(train)<20:raise ValueError('insufficient_training:20_required')
    forecasts={'persistence':changes[-1],'trailing_three':mean(changes[-3:])}
    out={}
    for name,mu in forecasts.items():
        errors=[r['actual']-r[name] for r in train]
        out[name]=exceedance(mu+mean(errors),max(0.01,pstdev(errors)),threshold)
    return out
