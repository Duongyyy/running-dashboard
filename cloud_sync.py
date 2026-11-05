"""GitHub Actions Garmin sync -> encrypted private history -> sanitized Pages site.

Do not run this script in untrusted PR workflows or with untrusted Actions code.
GARMIN_PERSONAL_API_KEY and STRIDE_ARCHIVE_KEY must be stored as Actions secrets.
"""
from __future__ import annotations
import json
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# Resolve local modules relative to this file, not the GitHub runner's directory.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PRIVATE = ROOT / '.private_work'
PRIVATE.mkdir(mode=0o700, exist_ok=True)
os.environ['STRIDE_DATA_DIR'] = str(PRIVATE)

from cryptography.fernet import Fernet, InvalidToken

ENC = ROOT / 'state' / 'history.enc'
SITE = ROOT / 'site'
ASSETS = ROOT / 'site_assets'


def safe_encryption_key():
    raw = os.environ.get('STRIDE_ARCHIVE_KEY', '').strip().encode()
    if not raw:
        raise RuntimeError('Missing STRIDE_ARCHIVE_KEY GitHub Actions secret. Generate one using generate_archive_key.py.')
    try:
        return Fernet(raw)
    except (ValueError, TypeError) as exc:
        raise RuntimeError('STRIDE_ARCHIVE_KEY is not a valid Fernet key. Generate a new one.') from exc


def bootstrap_state():
    # Restore first, BEFORE importing server.storage which initialises SQLite.
    cipher = safe_encryption_key()
    db_path = PRIVATE / 'stride.sqlite3'
    if ENC.exists():
        if db_path.exists():
            raise RuntimeError('Refusing to overwrite an existing decrypted working database.')
        try:
            contents = cipher.decrypt(ENC.read_bytes())
        except InvalidToken as exc:
            raise RuntimeError('Unable to decrypt saved history. Restore the original STRIDE_ARCHIVE_KEY secret.') from exc
        db_path.write_bytes(contents)
        db_path.chmod(0o600)
        print('Restored existing encrypted history.')
    else:
        print('First run: no encrypted history; will import Garmin activity history.')
    return cipher

if not os.environ.get('GARMIN_PERSONAL_API_KEY'):
    raise RuntimeError('Missing GARMIN_PERSONAL_API_KEY GitHub Actions secret.')
CIPHER = bootstrap_state()

from server.garmin import GarminPersonal, GarminAPIError
from server.storage import db, get_config, put_config, DB
from server.fit_reader import parse_activity_archive
from server.metrics import dashboard, profile_parse, clock, pace_string
from public_export import sanitized, slim_list


def is_run(raw):
    kind = raw.get('activityType') or raw.get('type') or ''
    if isinstance(kind, dict):
        kind = kind.get('typeKey') or kind.get('key') or ''
    return any(x in str(kind).lower() for x in ('run', 'trail', 'treadmill'))


def val(x):
    try: return float(x)
    except (TypeError, ValueError): return None


def normalise(raw):
    aid = raw.get('activityId') or raw.get('id')
    date = str(raw.get('startTimeLocal') or raw.get('startTimeGMT') or raw.get('startTime') or '')
    distance = val(raw.get('distance'))
    duration = val(raw.get('duration'))
    if not aid or not date or not duration or not distance or distance <= 0:
        return None
    kind = raw.get('activityType') or raw.get('type') or {}
    if isinstance(kind,dict): kind = kind.get('typeKey') or kind.get('key') or 'running'
    # Avoid retaining Garmin's original JSON (potential coordinates and profile data)
    # or private workout names. All private archive contents are encrypted regardless.
    return (str(aid), date, 'Garmin run', str(kind), distance, duration,
            val(raw.get('elapsedDuration')) or duration,
            val(raw.get('averageHR')) or val(raw.get('averageHeartRate')),
            val(raw.get('maxHR')) or val(raw.get('maxHeartRate')),
            val(raw.get('elevationGain')) or val(raw.get('totalAscent')) or 0,
            duration/(distance/1000), '{}', 'garmin')


def save_summaries(items):
    sql = '''INSERT INTO activities(id,date,name,type,distance,duration,elapsed,avg_hr,max_hr,ascent,pace,raw,source)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(id) DO UPDATE SET date=excluded.date, type=excluded.type,
      distance=excluded.distance, duration=excluded.duration, elapsed=excluded.elapsed,
      avg_hr=excluded.avg_hr, max_hr=excluded.max_hr, ascent=excluded.ascent, pace=excluded.pace'''
    with db() as c:
        c.executemany(sql, items)


def fetch_physiology(api):
    successful = 0
    for cache_key, callback in [('profile_raw', api.profile),('heart_zones_raw', api.hr_zones)]:
        try:
            payload = callback()
            if isinstance(payload, (dict, list)) and payload:
                # These records can contain account data; only encrypted DB stores them.
                put_config(cache_key, payload)
                successful += 1
        except GarminAPIError as exc:
            print('Garmin physiology endpoint temporarily unavailable:', str(exc)[:140])
    profile = profile_parse(get_config('profile_raw', {}), get_config('heart_zones_raw', []))
    if profile:
        put_config('profile_normalized', profile)
    print('Physiology endpoints retrieved:', successful, 'recognised values:', ', '.join(k for k in ('lthr','max_hr','rest_hr','threshold_pace') if profile.get(k)) or 'none')


def sync(api):
    first = not bool(get_config('last_garmin_sync'))
    fetch_physiology(api)
    page_limit = 200 if first else 3
    run_rows = []
    complete = False
    activity_count = 0
    for page in range(page_limit):
        data = api.activities(start=page * 100, limit=100)
        if isinstance(data, dict):
            data = data.get('activities') or data.get('items') or []
        if not isinstance(data, list):
            raise RuntimeError('Garmin activity listing had an unexpected format; not updating public statistics.')
        activity_count += len(data)
        run_rows.extend(v for a in data if isinstance(a,dict) and is_run(a) if (v:=normalise(a)) is not None)
        if len(data) < 100:
            complete = True
            break
    save_summaries(run_rows)
    print('Garmin activities checked:', activity_count, 'running summaries imported:', len(run_rows), 'historical archive scanned:', complete if first else 'recent')
    if first:
        put_config('archive_complete', complete)
    max_details = max(1, min(int(os.environ.get('DETAIL_BATCH') or '60'), 150))
    with db() as c:
        todo = [r['id'] for r in c.execute('''SELECT id FROM activities
        WHERE detail_status='pending' ORDER BY date DESC LIMIT ?''', (max_details,)).fetchall()]
    import zlib
    details_ok = 0
    failed = 0
    for aid in todo:
        try:
            blob = api.activity_zip(aid)
            if len(blob) > 35_000_000:
                raise ValueError('Download exceeded file safety limit')
            pts = parse_activity_archive(blob)
            data = zlib.compress(json.dumps(pts, separators=(',',':')).encode(), 6) if pts else None
            with db() as c:
                c.execute('UPDATE activities SET samples=?,detail_status=? WHERE id=?', (data, 'ready' if pts else 'no_stream', aid))
            details_ok += 1
        except (ValueError, OSError) as exc:
            failed += 1
            with db() as c:
                c.execute("UPDATE activities SET detail_status='unavailable' WHERE id=?", (aid,))
            print('FIT import unavailable for one activity:', str(exc)[:100])
        except GarminAPIError as exc:
            failed += 1
            print('Garmin FIT request failed; will retry in next scheduled sync:', str(exc)[:120])
            break
        time.sleep(0.12)
    stamp = datetime.now(timezone.utc).isoformat()
    put_config('last_garmin_sync', stamp)
    with db() as c:
        total = c.execute('SELECT COUNT(*) FROM activities').fetchone()[0]
        detailed = c.execute("SELECT COUNT(*) FROM activities WHERE detail_status='ready'").fetchone()[0]
        pending = c.execute("SELECT COUNT(*) FROM activities WHERE detail_status='pending'").fetchone()[0]
    print('Detailed FIT processed:',details_ok, 'failed:',failed, 'total runs:',total, 'FIT ready:',detailed, 'FIT pending:',pending)
    return {'time':stamp, 'runs':total, 'fit_ready':detailed, 'fit_pending':pending}


def _public_activity_data(rows, include_physiology, include_activities):
    """Only date-level activity summaries and relative HR samples; never coordinates, IDs or raw FIT."""
    if not include_activities:
        return [], {}
    import zlib, math
    feed=[]
    streams={}
    for idx, row in enumerate(rows[:5000]):
        km = float(row['distance'] or 0)/1000
        duration=float(row['duration'] or 0)
        if km<=0 or duration<=0:continue
        day=str(row['date'] or '')[:10]
        if len(day)!=10 or day[4]!='-' or day[7]!='-':continue
        item_id=f'run-{idx+1}'  # synthetic public ID; not Garmin's private source identifier
        item={'id':item_id,'name':'Garmin run','date':day,'km':round(km,2),
              'duration_seconds':round(duration),'seconds':round(duration),
              'elapsed_seconds':round(float(row['elapsed'] or duration)),
              'time':clock(duration),'pace':pace_string(duration,km),
              'ascent_m':round(float(row['ascent'] or 0)),
              'ascent':round(float(row['ascent'] or 0)),
              'detail_status':'ready' if row['detail_status']=='ready' else 'summary'}
        if include_physiology:
            for k, out in [('avg_hr','hr'),('max_hr','peak_hr')]:
                val=row[k]
                if val is not None and 30<=float(val)<=250:
                    item[out]=round(float(val))
                    if out=='hr':item['average_hr']=item[out]
                    if out=='peak_hr':item['recorded_peak_hr']=item[out]
        feed.append(item)
        # Detailed relative-time HR only, no timestamps, GPS, altitudes, paths or raw FIT data.
        if include_physiology and row['samples'] and len(streams)<300:
            try:
                points=json.loads(zlib.decompress(row['samples']))
                suitable=[x for x in points if isinstance(x,dict) and isinstance(x.get('t'),(int,float))
                          and isinstance(x.get('hr'),(int,float)) and 30<=x['hr']<=250]
                if len(suitable)>2:
                    start=suitable[0]['t']
                    step=max(1,(len(suitable)+129)//130)
                    streams[item_id]=[{'minute':round((x['t']-start)/60,1),'hr':round(x['hr'])}
                                      for x in suitable[::step][:140] if 0<=x['t']-start<=24*3600]
            except (ValueError,TypeError,IndexError,zlib.error):
                pass
    return feed, streams


def make_site(summary):
    SITE.mkdir(exist_ok=True)
    for name in ['index.html', 'style.css', 'app.js']:
        shutil.copy2(ASSETS/name, SITE/name)
    with db() as c:
        rows=c.execute('SELECT * FROM activities ORDER BY date DESC').fetchall()
        official=[dict(r) for r in c.execute('SELECT * FROM records').fetchall()]
    profile=get_config('profile_normalized',{})
    raw=dashboard(rows,get_config('settings',{}),profile,official)
    physiology=(os.environ.get('PUBLISH_PHYSIOLOGY') or '').lower()=='true'
    activity_feed=(os.environ.get('PUBLISH_ACTIVITY_SUMMARIES') or '').lower()=='true'
    published=sanitized(raw,include_physiology=physiology,reference_values=profile)
    feed, streams=_public_activity_data(rows,physiology,activity_feed)
    published['activity_feed_shared']=activity_feed
    published['activity_feed']=feed
    published['activity_hr_streams']=streams
    published['sync']={'garmin_last_success':summary['time'],
                      'historical_archive_complete':get_config('archive_complete',False),
                      'fits_available':summary['fit_ready'],'fits_pending':summary['fit_pending']}

    # Same field schema as the original locally rendered Stride Lab UI. Sanitise field-by-field.
    info=published['overview']
    summary_card={**info,'detailed_runs':published['coverage']['detailed']}
    public_state={
        'summary':summary_card,
        'pbs':published['pbs'],
        'pb_trend_5k':published['pb_trend_5k'],
        'weeks':[{**w,'longest_km':next((x['km'] for x in published['long_runs'] if x['week']==w.get('week')),0)}
                 for w in published['weeks']],
        'months':published['months'],
        'heatmap':slim_list(raw.get('heatmap'),['date','km','runs'],98),
        'long_runs':published['long_runs'],
        'intensity_weeks':published['intensity_weeks'],
        'upcoming_guidance':published['upcoming_guidance'],
        'zones':published['zones'],
        'time_in_zone':published['time_in_zone'],
        'threshold':published['threshold'],
        'efficiency':slim_list(raw.get('efficiency'),['date','hr','pace','distance'],80) if physiology else [],
        'efficiency_comparison':published.get('efficiency_comparison') or None,
        'recent':feed[:24],
        'insights':published['insights'],
        'race_projection':published['race_projection'] if published['race_projection'] else None,
        'goal':published['goal'],
        'coverage':published['coverage'],
        'connection':{
            'connected':True,'last_sync':summary['time'],'last_sync_error':None,
            'sync':{'running':False},
            'settings':{'zone_method':'auto'},
            'profile':published['physiology_references'],
            'physiology_status':{},
        },
    }
    published['public_state']=public_state
    (SITE/'data.json').write_text(json.dumps(published,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    (SITE/'.nojekyll').write_text('',encoding='utf-8')
    (SITE/'robots.txt').write_text('User-agent: *\nDisallow: /\n',encoding='utf-8')
    print('Created local-interface-matching read-only website. No Garmin keys, GPS, raw FIT or activity source IDs exported.')

def persist(cipher):
    # Write only encrypted history to Git. Preserve continuity for personal bests.
    with db() as c:
        c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    data = DB.read_bytes()
    if len(data) > 85_000_000:
        raise RuntimeError('Encrypted database exceeds safe GitHub storage size. Use external private persistence instead.')
    ENC.parent.mkdir(parents=True, exist_ok=True)
    tmp = ENC.with_suffix('.tmp')
    tmp.write_bytes(cipher.encrypt(data))
    tmp.replace(ENC)
    print('Encrypted history saved. No plaintext database will be committed.')


def main():
    cipher = CIPHER
    api = GarminPersonal()
    api.access_token()  # fail fast; no invalid publish on failed auth
    info = sync(api)
    make_site(info)
    persist(cipher)
    print('SUCCESS: public site ready, encrypted history updated.')


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        print('SYNC FAILED:', str(exc)[:300],file=sys.stderr)
        sys.exit(1)
