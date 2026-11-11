"""Validate immutable entry links and generate a compact comparison artifact offline."""
import csv
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from collect import ROOT, OUT

def dt(s):
    d=datetime.fromisoformat(s.replace('Z','+00:00'))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

def main():
    evidence=json.loads((OUT/'summary.json').read_text())
    results=[]
    positions={p['signal_id']:p for p in evidence['local']['positions']}
    for item in evidence['local']['entries']:
        entry=json.loads(item['entry_json']);p=positions[item['signal_id']];f=entry['forecast']
        archive=ROOT/'forward_test/state/predictions'/entry['archive']
        manifest=json.loads((archive/'manifest.json').read_text())
        for name,expected in dict({'predictions.csv':manifest['csv_sha256'],'metadata.json':manifest['metadata_sha256']},**manifest['snapshots']).items():
            assert hashlib.sha256((archive/name).read_bytes()).hexdigest()==expected,name
        archived=next(r for r in csv.DictReader((archive/'predictions.csv').read_text().splitlines()) if r['game_id']==entry['game_id'])
        assert all(str(f[k])==str(v) for k,v in archived.items() if k in f)
        assert dt(manifest['observed_at']) < dt(entry['quote']['observed_at']) <= dt(entry['decision_at']) < dt(f['tipoff_utc'])
        comp=next(c for c in evidence['comparisons'] if set(c['pair'])=={f['home_team'],f['away_team']})
        assert comp['home']==f['home_team'] and comp['away']==f['away_team']
        assert dt(comp['tipoff_utc'])==dt(f['tipoff_utc'])
        assert dt(evidence['requests'][-1]['received_at']) < dt(f['tipoff_utc'])
        contract_team=p['ticker'].rsplit('-',1)[1]
        yes_probability=Decimal(f['home_win_probability'] if contract_team==f['home_team'] else f['away_win_probability'])
        probability=yes_probability if p['side']=='YES' else 1-yes_probability
        signal=entry['signal']; cost=Decimal(p['price'])+Decimal(p['fee'])
        assert probability==Decimal(signal['probability'])
        assert cost==Decimal(signal['assumed_price'])+Decimal(signal['fee'])
        assert probability-cost==Decimal(signal['net_edge'])
        results.append(dict(position=contract_team+' '+p['side'],opponent=f['away_team'] if contract_team==f['home_team'] else f['home_team'],sealed_contract_probability=str(probability),observed_ask=signal['ask'],assumed_fill=p['price'],fee=p['fee'],total_cost=str(cost),model_net_edge=signal['net_edge'],decision_at=entry['decision_at'],quote_at=entry['quote']['observed_at'],archive=entry['archive'],game_id=entry['game_id'],sportsdataio_game_id=comp['sportsdataio_game_id'],tipoff_utc=f['tipoff_utc'],classification=comp['classification']))
    assert len(results)==7
    (OUT/'comparison.json').write_text(json.dumps(dict(verified_entries=7,entry_forecasts_match_sealed_csv=True,archive_hashes_verified=True,provider_home_away_and_tipoff_match=True,all_collected_before_tipoff=True,results=results),indent=2)+'\n')
    print('Verified seven entry/forecast links, archive hashes, contract-side arithmetic, and provider schedule identities.')
if __name__=='__main__':main()
