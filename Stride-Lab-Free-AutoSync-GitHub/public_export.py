"""Create a strictly read-only public summary of local Stride Lab data.

Only a fixed allowlist of aggregated metrics can cross into the output directory.
No key, personal profile, local paths, route, GPS, or workout FIT samples are exported.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import shutil
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SITE = HERE / 'site'
SOURCE = HERE / 'assets'
LOCAL_ENDPOINT = 'http://127.0.0.1:8765/api/state'


def slim_dict(obj, keys):
    return {key: obj[key] for key in keys if isinstance(obj, dict) and key in obj}


def slim_list(seq, keys, max_items=500):
    if not isinstance(seq, list):
        return []
    return [slim_dict(obj, keys) for obj in seq[-max_items:] if isinstance(obj, dict)]


def sanitized(raw, include_physiology=False):
    """Explicit allowlist: no connection, keys, routes, identifiers, or activity names."""
    if not isinstance(raw, dict) or not isinstance(raw.get('summary'), dict):
        raise ValueError('Missing real Stride Lab dashboard measurements')
    if raw.get('sample'):
        raise ValueError('Refusing to publish sample data as if it were your real history.')
    res = {
        'schema_version': 1,
        'sample': False,
        'published_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'overview': slim_dict(raw['summary'], [
            'runs', 'all_km', 'this_week_km', 'last_week_km', 'last_28_km',
            'prev_28_km', 'year_km', 'hours_28', 'longest_km',
            'active_weeks_12', 'runs_week_average_12',
        ]),
        'pbs': slim_list(raw.get('pbs'), [
            'name', 'meters', 'time', 'seconds', 'pace', 'date', 'source', 'kind', 'official'
        ], 30),
        'pb_trend_5k': slim_list(raw.get('pb_trend_5k'), ['date', 'seconds'], 365),
        'weeks': slim_list(raw.get('weeks'), ['week', 'label', 'km', 'runs', 'hours'], 104),
        'months': slim_list(raw.get('months'), ['label', 'km', 'runs'], 36),
        'long_runs': slim_list(raw.get('long_runs'), ['week', 'label', 'km', 'runs'], 104),
        'insights': slim_list(raw.get('insights'), ['type', 'title', 'body'], 8),
        'upcoming_guidance': slim_list(raw.get('upcoming_guidance'), ['title', 'text', 'signal'], 8),
        'coverage': slim_dict(raw.get('coverage'), ['activities', 'detailed', 'percent']),
        'goal': slim_dict(raw.get('goal'), ['distance', 'time', 'target_pace']),
        'race_projection': slim_dict(raw.get('race_projection'), ['distance', 'time', 'source_distance', 'note']),
        'physiology_shared': bool(include_physiology),
    }
    if include_physiology:
        z = raw.get('zones') or {}
        res['zones'] = {
            'available': bool(z.get('available')),
            'method': z.get('method'),
            'source': z.get('source'),
            'selected': z.get('selected'),
            'easy': z.get('easy'),
            'zones': slim_list(z.get('zones'), ['name', 'low', 'high', 'purpose'], 5),
        }
        res['threshold'] = slim_dict(raw.get('threshold'), ['lthr', 'pace_seconds', 'pace', 'source', 'note'])
        res['time_in_zone'] = [float(x) for x in (raw.get('time_in_zone') or [])[:5] if isinstance(x, (int,float))]
        res['intensity_weeks'] = slim_list(raw.get('intensity_weeks'), ['week', 'label', 'seconds', 'total_seconds'], 16)
        ec = raw.get('efficiency_comparison') or {}
        res['efficiency_comparison'] = slim_dict(ec, ['hr_band', 'early_pace', 'recent_pace', 'delta_sec', 'n', 'caution'])
        # Median-based monthly aggregates only; individual run timestamps / names are excluded.
        buckets = {}
        for a in raw.get('efficiency') or []:
            if not isinstance(a, dict):
                continue
            date = a.get('date','')
            pace, hr = a.get('pace'), a.get('hr')
            if isinstance(date,str) and len(date)>=7 and isinstance(pace,(int,float)) and isinstance(hr,(int,float)):
                b = buckets.setdefault(date[:7], {'pace': [], 'hr': []})
                b['pace'].append(pace); b['hr'].append(hr)
        from statistics import median
        res['efficiency_months'] = [
            {'month': m, 'pace': round(median(v['pace'])), 'hr': round(median(v['hr'])), 'runs': len(v['pace'])}
            for m,v in sorted(buckets.items()) if len(v['pace']) >= 2
        ][-24:]
    else:
        res['zones'] = {'available':False, 'zones':[]}
        res['threshold'] = {}
        res['time_in_zone'] = []
        res['intensity_weeks'] = []
        res['efficiency_comparison'] = {}
        res['efficiency_months'] = []
    return res


def get_local_data():
    try:
        with urllib.request.urlopen(LOCAL_ENDPOINT,timeout=25) as resp:
            data=json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError,TimeoutError) as e:
        raise RuntimeError('Stride Lab is not running at 127.0.0.1:8765. Start run_windows.bat and retry.') from e
    return data


def build_site(raw, physiology):
    SITE.mkdir(exist_ok=True)
    for f in SOURCE.iterdir():
        if f.is_file():
            shutil.copyfile(f, SITE/f.name)
    payload = sanitized(raw,include_physiology=physiology)
    (SITE/'data.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
    # Header further reduces accidental cache/data previews from search indexing; public URLs remain publicly accessible.
    (SITE/'robots.txt').write_text('User-agent: *\nDisallow: /\n',encoding='utf-8')
    (SITE/'_headers').write_text('/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: no-referrer\n  X-Frame-Options: DENY\n',encoding='utf-8')
    archive=HERE/'Stride-Lab-Public-Website.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in SITE.iterdir():
            if p.is_file(): z.write(p,p.name)
    return archive,payload


def main():
    p=argparse.ArgumentParser(description='Export safe read-only public Stride Lab website')
    p.add_argument('--include-physiology',action='store_true',help='Also share your HR zones, LTHR and aggregated HR charts publicly')
    p.add_argument('--demo',action='store_true',help='Developer preview using clearly labelled fictional data')
    args=p.parse_args()
    if args.demo:
        raw=json.loads((HERE/'sample.json').read_text(encoding='utf-8'))
        raw['sample']=False # only allows renderer test; marked as demo after sanitization
        out,payload=build_site(raw,args.include_physiology)
        payload['sample']=True
        (SITE/'data.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            for q in SITE.iterdir():
                if q.is_file():z.write(q,q.name)
        print('Created FICTIONAL preview:',out)
        return
    if not sys.stdin.isatty():
        print('Interactive terminal required for public-data disclosure confirmation.',file=sys.stderr)
        sys.exit(2)
    print('\nPUBLIC DATA NOTICE: Anyone with the website link can view the exported running statistics.')
    print('No Garmin keys, GPS tracks, individual workout logs, or private account details are included.')
    if args.include_physiology:
        print('You have chosen to additionally share heart-rate zones and lactate-threshold values.')
    confirm=input('Type PUBLISH to create the shareable website ZIP: ').strip()
    if confirm!='PUBLISH':
        print('Cancelled: no website was generated.')
        return
    raw=get_local_data()
    archive,payload=build_site(raw,args.include_physiology)
    print('\nSUCCESS:',archive)
    print('Runs shown:',payload['overview'].get('runs',0))
    print('Shareable statistics created; upload this ZIP to Cloudflare Pages using Direct Upload.')
    print('IMPORTANT: This is a static snapshot. Repeat export and upload for updated runs.')

if __name__=='__main__':
    main()
