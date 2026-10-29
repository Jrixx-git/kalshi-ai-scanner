"""Validate normalized observations, run expanding chronological prototypes, seal reports."""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import mean
from .core import asof, instant, number, probability, prior_rows, seal
from .models import logistic_offset, weather, monthly_changes, finance
from .evaluation import compare

SPORT_FEATURES=('advanced_player_rating_diff','injury_minutes_diff','lineup_rating_diff')


def run(dataset, evidence_root=None):
    family=dataset['family']; synthetic=dataset.get('synthetic') is True
    if family not in ('sports','weather','finance'):raise ValueError('unknown_family')
    rows=dataset['events'];seen=set();accepted=[];rejections=[];scored=[]
    for row in sorted(rows,key=lambda r:instant(r['decision_at'])):
        event_id=row['event_id']
        if event_id in seen:raise ValueError('duplicate_event')
        seen.add(event_id)
        try:
            decision,target,label=(instant(row[k]) for k in ('decision_at','target_at','outcome_available_at'))
            if not decision<target<=label:raise ValueError('invalid_outcome_timing')
            if not row.get('cluster'):raise ValueError('cluster_required')
            # Outcome provenance is checked at label availability, never as an input feature.
            asof(row['outcome'],row['outcome_available_at'],evidence_root=evidence_root,synthetic=synthetic)
            inputs=row['inputs']
            for record in inputs.values():asof(record,row['decision_at'],evidence_root=evidence_root,synthetic=synthetic)
            train=prior_rows(accepted,row['decision_at'])
            item={k:row[k] for k in ('event_id','decision_at','outcome_available_at','cluster')}
            if family=='sports':
                y=number(row['outcome']['value'])
                if y not in (0,1):raise ValueError('binary_outcome_required')
                baseline=probability(inputs['legacy']['value'])
                # Explicit canonical game ID joins; provider numeric IDs are never assumed equal.
                for rec in inputs.values():
                    if rec.get('canonical_game_id')!=event_id:raise ValueError('game_identity_mismatch')
                if inputs['challenger'].get('data_quality')!='verified_unscrambled':raise ValueError('unverified_challenger_quality')
                features=[number(inputs['challenger']['features'][f]) for f in SPORT_FEATURES]
                item.update(features=features,baseline=baseline,y=y)
                if len(train)>=20:
                    pred=logistic_offset(train,features,baseline)
                    item['predictions']={'legacy':baseline,'advanced':pred}
                    for index,name in enumerate(SPORT_FEATURES):
                        subset=[dict(t,features=[t['features'][index]]) for t in train]
                        item['predictions'][name]=logistic_offset(subset,[features[index]],baseline)
                    if 'market' in inputs:item['predictions']['market']=probability(inputs['market']['value'])
            elif family=='weather':
                det=inputs['public'];ens=inputs['ensemble'];outcome=row['outcome']
                if outcome.get('kind')!='official_station_daily_max':raise ValueError('official_daily_observation_required')
                for rec in (det,ens):
                    if rec.get('kind')!='forecast_run' or not rec.get('run_id'):raise ValueError('archived_run_required')
                    if any(rec.get(k)!=row.get(k) for k in ('station','day','unit','day_definition')):raise ValueError('weather_identity_mismatch')
                if any(outcome.get(k)!=row.get(k) for k in ('station','day','unit','day_definition')):raise ValueError('observation_identity_mismatch')
                if row.get('unit')!='C' or row.get('operator')!='>':raise ValueError('unsupported_temperature_rule')
                threshold=number(row['threshold']);actual=number(outcome['value'])
                members=[number(v) for v in ens['member_maxima']]
                if len(members)<2:raise ValueError('ensemble_members_required')
                item.update(actual=actual,deterministic=number(det['value']),members=members,y=int(actual>threshold))
                # Station-specific calibration: never mix targets or units silently.
                item['station']=row['station'];item['day_definition']=row['day_definition']
                train=[t for t in train if t['station']==item['station'] and t['day_definition']==item['day_definition']]
                if len(train)>=20:item['predictions']=weather(train,item['deterministic'],members,threshold)
            else:
                vintage=inputs['vintage']
                if vintage.get('series_id')!='CPIAUCSL' or row['outcome'].get('kind')!='first_release_mom_percent':
                    raise ValueError('unsupported_macro_target')
                if row['outcome'].get('target_period')!=row['target_period'] or row['outcome'].get('series_id')!=vintage['series_id']:
                    raise ValueError('macro_label_identity_mismatch')
                changes=monthly_changes(vintage['values'],row['target_period'])
                actual=number(row['outcome']['value']);threshold=number(row['threshold'])
                item.update(actual=actual,persistence=changes[-1],trailing_three=mean(changes[-3:]),y=int(actual>threshold))
                if len(train)>=20:item['predictions']=finance(train,changes,threshold)
            accepted.append(item)
            if 'predictions' in item:scored.append(item)
        except (KeyError,ValueError,TypeError,OSError) as exc:
            rejections.append({'event_id':event_id,'reason':str(exc)})
    names={'sports':('legacy','advanced'),'weather':('public_calibrated','ensemble_calibrated'),'finance':('persistence','trailing_three')}[family]
    result=compare(scored,*names)
    result.update(family=family,synthetic=synthetic,eligible_events=len(rows),accepted_events=len(accepted),
                  warmup_events=len(accepted)-len(scored),rejections=rejections,forecasts=scored,
                  mode='RESEARCH_ONLY_NO_TRADING',data_claim='synthetic software demonstration' if synthetic else 'imported evidence; availability attestations require review')
    if family=='sports':
        paired=[r for r in scored if 'market' in r['predictions']]
        result['market_comparison']=compare(paired,'market','advanced')
        result['feature_ablations']={name:compare(scored,'legacy',name) for name in SPORT_FEATURES}
    if family=='weather':result['spread_ablation']=compare(scored,'ensemble_mean_fixed_variance','ensemble_calibrated')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset');parser.add_argument('--evidence-root');parser.add_argument('--output',default='research_outputs')
    args=parser.parse_args()
    # Prevent accidental output into operational archives even via a symlink.
    output=Path(args.output).resolve()
    if any(p in ('paper_v08','forward_test','.github') for p in output.parts):raise ValueError('operational_output_forbidden')
    raw=Path(args.dataset).read_bytes();dataset=json.loads(raw)
    report=run(dataset,args.evidence_root)
    report['input_sha256']=hashlib.sha256(raw).hexdigest()
    report['implementation_sha256']=hashlib.sha256(b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py')))).hexdigest()
    digest=seal(output,report)
    print(json.dumps({'report':str(output/(digest+'.json')),'synthetic':report['synthetic'],'scored':report['n'],'rejected':len(report['rejections']),'superiority_claim':False}))


if __name__=='__main__':main()
