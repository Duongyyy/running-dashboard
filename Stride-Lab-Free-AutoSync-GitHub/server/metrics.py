"""Deterministic, inspectable running metrics. No inferred thresholds or fake measurements."""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime,date,timedelta
from zoneinfo import ZoneInfo
from statistics import mean,median
from math import ceil
import json,zlib
from .fit_reader import fastest_effort,time_in_zones

DISTANCES=[('400 m',400),('1 km',1000),('1 mile',1609.344),('3 km',3000),('5 km',5000),('10 km',10000),('15 km',15000),('10 miles',16093.44),('Half marathon',21097.5),('Marathon',42195),('50 km',50000)]

def num(v):
    try:
        x=float(v)
        return x if x==x and x!=float('inf') else None
    except (ValueError,TypeError):return None

def pace_string(seconds,dist_km):
    if not seconds or not dist_km:return '—'
    spk=seconds/dist_km
    if spk<90 or spk>3600:return '—'
    return f'{int(round(spk))//60}:{int(round(spk))%60:02d}/km'

def clock(seconds):
    if not seconds:return '—'
    seconds=int(round(seconds)); h,rem=divmod(seconds,3600); m,s=divmod(rem,60)
    return f'{h}:{m:02}:{s:02}' if h else f'{m}:{s:02}'

def unpack_samples(row):
    try:return json.loads(zlib.decompress(row['samples'])) if row['samples'] else []
    except Exception:return []

def running(row):
    k=str(row.get('type') or '').lower()
    return ('run' in k or 'trail' in k or k=='treadmill') and not ('transition' in k)

def zones_for(settings,profile):
    mode=settings.get('zone_method','auto')
    lt=num(settings.get('lthr')) or num(profile.get('lthr'))
    maximum=num(settings.get('max_hr')) or num(profile.get('max_hr'))
    rest=num(settings.get('rest_hr')) or num(profile.get('rest_hr'))
    if mode=='auto': mode='lthr' if lt else 'hrr' if maximum and rest else 'max' if maximum else 'unavailable'
    purpose=['Recovery','Easy aerobic','Steady / moderate','Threshold-focused','High intensity']
    if mode=='lthr' and lt:
        edges=[0,.85,.90,.95,1.00,1.10]
        lows=[1,round(lt*.85),round(lt*.90),round(lt*.95),round(lt)]
        highs=[round(lt*.85)-1,round(lt*.90)-1,round(lt*.95)-1,round(lt)-1,round(lt*1.1)]
        method='Illustrative 5-zone %LTHR model; aerobic threshold cannot be identified precisely from LTHR alone.'
    elif mode=='hrr' and maximum and rest and maximum>rest:
        vals=[round(rest+(maximum-rest)*x) for x in [.5,.6,.7,.8,.9,1]]
        lows=[1,*vals[1:5]]; highs=[v-1 for v in vals[1:5]]+[vals[5]]
        method='Five-zone heart-rate reserve model (Z1 below 60% HRR; Z2–Z5 span 60–100%).'
    elif mode=='max' and maximum:
        vals=[round(maximum*x) for x in [.5,.6,.7,.8,.9,1]]
        lows=[1,*vals[1:5]]; highs=[v-1 for v in vals[1:5]]+[vals[5]]
        method='Five-zone maximum-heart-rate model (Z1 below 60% HRmax; Z2–Z5 span 60–100%).'
    else:return {'available':False,'zones':[],'method':'Add a verified LTHR or maximum heart rate in Settings to calculate training zones.','selected':mode}
    # 5 consecutive ranges, including a catch-all low zone.
    if mode=='lthr':
        lows=[1,highs[0]+1,highs[1]+1,highs[2]+1,highs[3]+1]
    else:
        lows=[1,highs[0]+1,highs[1]+1,highs[2]+1,highs[3]+1]
    result=[]
    for i in range(5):result.append({'name':f'Z{i+1}','low':int(lows[i]),'high':int(highs[i]),'purpose':purpose[i]})
    return {'available':True,'zones':result,'method':method,'selected':mode,'easy':[result[1]['low'],result[1]['high']],'source':'User-entered values' if settings.get('lthr') or settings.get('max_hr') else 'Garmin profile values (when available)'}

def profile_parse(profile_json, zone_json):
    """Read Garmin's *configured* HR references, preferring RUNNING over DEFAULT.

    Garmin HR-zone v2 returns `*Used` keys, not the similarly-named fields
    accepted when a user edits their zone configuration. These are configured
    values, not verified physiological test results or current daily RHR.
    """
    result = {}
    field_sources = {}

    recognized = {
        'lactateThresholdHeartRateUsed': 'lthr',
        'lactateThresholdHeartRate': 'lthr',
        'lactateThresholdHeartRateBpm': 'lthr',
        'lactateThresholdHr': 'lthr',
        'maxHeartRateUsed': 'max_hr',
        'maxHeartRate': 'max_hr',
        'maximumHeartRate': 'max_hr',
        'restingHeartRateUsed': 'rest_hr',
        'restingHeartRate': 'rest_hr',
        'restingHr': 'rest_hr',
        'lactateThresholdPace': 'threshold_pace',
    }
    ranges = {'lthr': (70, 220), 'max_hr': (90, 250),
              'rest_hr': (25, 130), 'threshold_pace': (120, 1200)}

    def take(record, label):
        if not isinstance(record, dict):
            return
        for key, target in recognized.items():
            if key not in record or target in result:
                continue
            value = num(record[key])
            lo, hi = ranges[target]
            if value is not None and lo <= value <= hi:
                result[target] = round(value) if target != 'threshold_pace' else value
                field_sources[target] = label

    # Prefer the running-specific profile, followed by the default profile.
    # Never import a cycling- or swimming-only threshold as a running value.
    entries = []
    if isinstance(zone_json, list):
        entries = [x for x in zone_json if isinstance(x, dict)]
    elif isinstance(zone_json, dict):
        for key in ('heartRateZones', 'zones', 'items', 'profiles'):
            if isinstance(zone_json.get(key), list):
                entries = [x for x in zone_json[key] if isinstance(x, dict)]
                break
        if not entries and ('sport' in zone_json or 'maxHeartRateUsed' in zone_json):
            entries = [zone_json]

    def sport_kind(item):
        sport = str(item.get('sport') or 'DEFAULT').upper()
        if sport in ('RUNNING', 'RUN', 'TRAIL_RUNNING'):
            return 0
        if sport in ('DEFAULT', 'GENERIC', 'ALL'):
            return 1
        return 2

    appropriate = sorted((e for e in entries if sport_kind(e) < 2), key=sport_kind)
    for e in appropriate:
        sport = str(e.get('sport') or 'DEFAULT').upper()
        take(e, f'Garmin {sport.lower()} HR-zone configuration')

    # Actual Garmin floor boundaries are shown separately from our calculated
    # zones, so that calculated and watch-configured zones are not conflated.
    for e in appropriate:
        floors = [num(e.get(f'zone{i}Floor')) for i in range(1, 6)]
        if all(v is not None and 30 <= v <= 250 for v in floors) and all(a < b for a, b in zip(floors, floors[1:])):
            result['garmin_zone_floors'] = [round(v) for v in floors]
            result['garmin_zone_sport'] = str(e.get('sport') or 'DEFAULT').upper()
            result['garmin_zone_method'] = str(e.get('trainingMethod') or 'Unknown')[:40]
            break

    # Profile settings may carry a reference that wasn't in the zone endpoint.
    # Do not recursively search activity/daily summaries; a day's peak HR is
    # not the user's configured HRmax.
    def scan_profile(value, depth=0):
        if depth > 4:
            return
        if isinstance(value, dict):
            take(value, 'Garmin profile settings')
            for key, child in value.items():
                if key not in ('activities', 'records') and isinstance(child, (dict, list)):
                    scan_profile(child, depth + 1)
        elif isinstance(value, list):
            for child in value[:50]:
                scan_profile(child, depth + 1)

    scan_profile(profile_json)
    if field_sources:
        result['field_sources'] = field_sources
    return result

def dashboard(all_rows,settings,profile,official_records=None):
    today=datetime.now(ZoneInfo("Australia/Melbourne")).date()
    rows=[dict(r) for r in all_rows if running(dict(r)) and num(r['distance']) and num(r['duration']) and num(r['duration'])>0]
    rows.sort(key=lambda r:r['date'] or '',reverse=True)
    z=zones_for(settings,profile)
    dist_total=sum(r['distance'] for r in rows)/1000
    runs=len(rows)
    now_week=today-timedelta(days=today.weekday())
    def when(r):
        try:return date.fromisoformat((r['date'] or '')[:10])
        except ValueError:return date.min
    def sum_range(a,b):return sum(r['distance']/1000 for r in rows if a<=when(r)<b)
    this_week=sum_range(now_week,now_week+timedelta(days=7))
    last_week=sum_range(now_week-timedelta(days=7),now_week)
    last_28=sum_range(today-timedelta(days=27),today+timedelta(days=1))
    prev_28=sum_range(today-timedelta(days=55),today-timedelta(days=27))
    weeks=[]
    for i in range(19,-1,-1):
        first=now_week-timedelta(weeks=i)
        chosen=[r for r in rows if first<=when(r)<first+timedelta(days=7)]
        weeks.append({'week':first.isoformat(),'label':first.strftime('%d %b'),'km':round(sum(r['distance'] for r in chosen)/1000,1),'runs':len(chosen),'hours':round(sum(r['duration'] for r in chosen)/3600,1),'longest_km':round(max((r['distance'] for r in chosen),default=0)/1000,1)})
    months=[]
    for i in range(11,-1,-1):
        m=(today.year*12+today.month-1)-i; year=(m//12); month=m%12+1
        chosen=[r for r in rows if when(r).year==year and when(r).month==month]
        months.append({'label':date(year,month,1).strftime('%b %y'),'km':round(sum(r['distance'] for r in chosen)/1000,1),'runs':len(chosen),'longest_km':round(max((r['distance'] for r in chosen),default=0)/1000,1)})
    pb=[]; details_count=0; distribution=[0]*5; sample_coverage=0
    weekly_zones=defaultdict(lambda:[0]*5)
    decoded=[]
    for r in rows:
        pts=unpack_samples(r)
        if pts and len(pts)>3:
            details_count+=1; decoded.append((r,pts))
            if z['available']:
                per=time_in_zones(pts,z['zones'])
                distribution=[a+b for a,b in zip(distribution,per)]
                wk=when(r)-timedelta(days=when(r).weekday())
                weekly_zones[wk.isoformat()]=[a+b for a,b in zip(weekly_zones[wk.isoformat()],per)]
    official_records=official_records or []
    for name,m in DISTANCES:
        best=None
        for r,pts in decoded:
            # Meaningful acceleration of records calculation: skip runs too short.
            if r['distance']<m*.95:continue
            result=fastest_effort(pts,m)
            if result and (best is None or result['seconds']<best['seconds']):
                best={**result,'activity_id':r['id'],'activity_name':r['name'],'date':r['date'][:10], 'source':'FIT stream'}
        # Activity time can corroborate nearly exact-distance events, but must never be scored faster than truly traversed distance.
        for r in rows:
            if not r['distance'] or abs(r['distance']-m)/m>0.008:continue
            seconds=num(r['elapsed']) or num(r['duration'])
            if seconds and (best is None or seconds<best['seconds']):
                best={'seconds':seconds,'activity_id':r['id'],'activity_name':r['name'],'date':r['date'][:10],'kind':'activity_approximate','source':'Garmin activity summary'}
        official=next((x for x in official_records if abs(float(x['distance'])-m)<1),None)
        record={'name':name,'meters':m,'time':clock(best['seconds']) if best else '—','seconds':best['seconds'] if best else None,'pace':pace_string(best['seconds'],m/1000) if best else '—','date':best['date'] if best else None,'source':best['source'] if best else 'Not recorded','activity_id':best['activity_id'] if best else None,'kind':best['kind'] if best else 'none'}
        if official:record['official']={'time':clock(official['seconds']),'seconds':official['seconds'],'date':official['date']}
        pb.append(record)
    # Predecessor-derived best effort trend, valid only when records can be computed.
    trend=[]
    for r,pts in sorted(decoded,key=lambda x:x[0]['date']):
        best=fastest_effort(pts,5000) if r['distance']>=5000 else None
        if best:trend.append({'date':r['date'][:10],'seconds':best['seconds'],'activity_id':r['id']})
    cum=[]; fastest=None
    for p in trend:
        fastest=min(fastest,p['seconds']) if fastest is not None else p['seconds']
        if not cum or fastest<cum[-1]['seconds']:
            cum.append({'date':p['date'],'seconds':round(fastest)})
    # Run comparison in a narrow HR range, pace only for moderate distance with good quality.
    efficiency=[]
    for r in sorted(rows,key=lambda x:x['date']):
        hr=num(r['avg_hr']);d=num(r['distance']);duration=num(r['duration'])
        if not hr or not d or d<3500 or not duration or duration<1200:continue
        pace=duration/(d/1000)
        if pace<170 or pace>780:continue
        efficiency.append({'date':r['date'][:10],'hr':round(hr),'pace':round(pace),'label':r['name'],'distance':round(d/1000,1)})
    # Train at comparable HR: filter around selectable 140-155 / 155-170 based on athlete's distribution.
    comparison=None
    if len(efficiency)>=8:
        center=round(median(x['hr'] for x in efficiency)/5)*5
        matching=[x for x in efficiency if abs(x['hr']-center)<=5]
        if len(matching)>=6:
            half=max(2,len(matching)//3)
            early=mean(x['pace'] for x in matching[:half]); late=mean(x['pace'] for x in matching[-half:])
            comparison={'hr_band':[center-5,center+5],'early_pace':round(early),'recent_pace':round(late),'delta_sec':round(late-early),'n':len(matching),'caution':'Not adjusted for terrain, temperature or workout structure.'}
    # A twelve-week, duration-based intensity view. Only observed FIT HR samples count.
    intensity=[]
    for w in weeks[-12:]:
        values=weekly_zones[w['week']]
        intensity.append({'week':w['week'],'label':w['label'],'seconds':values,'total_seconds':sum(values),'runs':w['runs']})
    long_runs=[{'week':w['week'],'label':w['label'],'km':w['longest_km'],'runs':w['runs']} for w in weeks]
    # Recent completed weeks are more defensible baselines than a partial current week.
    completed=weeks[-5:-1]
    active_completed=[w for w in completed if w['runs']>0]
    baseline_km=round(median([w['km'] for w in active_completed]),1) if len(active_completed)>=2 else None
    consistency_12=sum(w['runs']>0 for w in weeks[-12:])
    weekly_running_days=round(sum(w['runs'] for w in weeks[-13:-1])/12,1)
    guidance=[]
    if len(active_completed)<2:
        guidance.append({'title':'Establish a training baseline','text':'Log several consistent weeks before choosing a target weekly volume or interpreting short-term workload changes.','signal':'Fewer than two active completed weeks in the last four.'})
    else:
        guidance.append({'title':'Use recent volume as your starting point','text':f'Your median completed active week over the past four weeks was {baseline_km:g} km. Plan around your current capacity and recovery rather than automatically increasing mileage.','signal':f'{len(active_completed)} active completed weeks of the last four; median {baseline_km:g} km.'})
    if consistency_12<8:
        guidance.append({'title':'Focus on repeatability','text':'A manageable number of repeatable runs may be more useful right now than adding complex intensity.','signal':f'{consistency_12}/12 weeks contained at least one run.'})
    else:
        guidance.append({'title':'Protect easy running days','text':'Keep truly easy sessions comfortable, especially when quality or long-run days are included. Your configured HR zones are a reference, not a substitute for effort.','signal':f'{consistency_12}/12 weeks contained at least one run.'})
    if z['available'] and sum(distribution)>3600:
        total_zone=sum(distribution)
        upper=sum(distribution[2:])/total_zone*100
        guidance.append({'title':'Review your intensity mix','text':f'{upper:.0f}% of your recorded running time with usable HR samples has been in Z3–Z5 under your selected model. Compare this with the purpose of your sessions; no universal zone split is assumed.','signal':f'{round(total_zone/3600,1)} hours of classified HR samples.'})
    else:
        guidance.append({'title':'Improve physiological data quality','text':'Use a consistent HR sensor and add a verified threshold or maximum-HR reference before relying on numerical training zones.','signal':'HR reference or detailed time-in-zone coverage is limited.'})
    # Year rolling heat map (90d); no inferred future miles.
    daily=defaultdict(lambda:{'km':0,'runs':0})
    for r in rows:
        dt=when(r)
        if dt==date.min:continue
        daily[dt.isoformat()]['km']+=r['distance']/1000; daily[dt.isoformat()]['runs']+=1
    heat=[]
    for i in range(97,-1,-1):
        dt=today-timedelta(days=i)
        heat.append({'date':dt.isoformat(),'km':round(daily[dt.isoformat()]['km'],1),'runs':daily[dt.isoformat()]['runs']})
    recent=[]
    for r in rows[:24]:
        recent.append({'id':r['id'],'name':r['name'],'date':r['date'][:10],'km':round(r['distance']/1000,2),'time':clock(r['duration']),'pace':pace_string(r['duration'],r['distance']/1000),'hr':round(r['avg_hr']) if r['avg_hr'] else None,'ascent':round(r['ascent'] or 0),'detail_status':r['detail_status']})
    # This is a descriptive summary, not an unvalidated prediction or injury diagnosis.
    insights=[]
    if runs:
        if last_28 and prev_28:
            pct=(last_28-prev_28)/prev_28*100
            insights.append({'type':'volume','title':'Four-week volume '+('increased' if pct>0 else 'decreased'), 'body':f'{last_28:.1f} km over the last 28 days versus {prev_28:.1f} km previously ({pct:+.0f}%). Consider this alongside fatigue, recovery and training goals.'})
        else:insights.append({'type':'volume','title':'Building your baseline','body':'Keep logging runs to establish a reliable four-week volume comparison.'})
        active_weeks=sum(w['runs']>0 for w in weeks[-12:])
        insights.append({'type':'consistency','title':f'{active_weeks} of the last 12 weeks active','body':'Regular running provides a stronger basis for judging trends than any single standout session.'})
        if comparison:
            direction='faster' if comparison['delta_sec']<0 else 'slower'
            insights.append({'type':'efficiency','title':'Pace at similar heart rate','body':f'For runs around {comparison["hr_band"][0]}–{comparison["hr_band"][1]} bpm, your latest sample was {abs(comparison["delta_sec"])} sec/km {direction} on average. This comparison does not control for terrain, weather or session type.'})
        if details_count < max(3,min(15,runs//4)):
            insights.append({'type':'quality','title':'Detailed activity data still syncing','body':f'Only {details_count} of {runs} runs have detailed streams. In-run personal bests and time-in-zone totals may be incomplete until FIT downloads finish.'})
    else:
        insights=[{'type':'connect','title':'Your training story starts here','body':'Connect Garmin or import your own FIT files to unlock personal records, workload trends and personalised heart-rate guidance.'}]
    lthr=num(settings.get('lthr')) or num(profile.get('lthr'))
    threshold_pace=num(settings.get('threshold_pace')) or num(profile.get('threshold_pace'))
    goal_distance=num(settings.get('goal_distance',21097.5)) or 21097.5
    goal_seconds=num(settings.get('goal_seconds'))
    eligible=[x for x in pb if x['seconds'] and 3000<=x['meters']<=42195]
    # choose closest verified short race distance to limit extrapolation; no pseudo 'fitness readiness' score.
    race_est=None
    if eligible:
        reference=min(eligible,key=lambda r:abs(__import__('math').log(goal_distance/r['meters'])))
        est=reference['seconds']*(goal_distance/reference['meters'])**1.06
        if .5 <=goal_distance/reference['meters']<=4:
            race_est={'distance':goal_distance,'seconds':round(est),'time':clock(est),'source_distance':reference['name'],'note':'Riegel projection from recorded best effort; not a guaranteed race performance.'}
    return {
      'generated_at':datetime.now().isoformat(), 'has_data':bool(runs),
      'summary':{'runs':runs,'all_km':round(dist_total,1),'this_week_km':round(this_week,1),'last_week_km':round(last_week,1),'last_28_km':round(last_28,1),'prev_28_km':round(prev_28,1),'year_km':round(sum_range(date(today.year,1,1),today+timedelta(days=1)),1),'hours_28':round(sum(r['duration'] for r in rows if today-timedelta(days=27)<=when(r)<=today)/3600,1),'days_7':sum(1 for r in rows if today-timedelta(days=6)<=when(r)<=today),'active_weeks_12':consistency_12,'runs_week_average_12':weekly_running_days,'median_completed_week_km':baseline_km,'detailed_runs':details_count,'longest_km':round(max((r['distance'] for r in rows),default=0)/1000,2)},
      'pbs':pb, 'pb_trend_5k':cum,'weeks':weeks,'months':months,'heatmap':heat,'long_runs':long_runs,'intensity_weeks':intensity,'upcoming_guidance':guidance,
      'zones':z,'time_in_zone':distribution,
      'threshold':{'lthr':round(lthr) if lthr else None,'pace_seconds':round(threshold_pace) if threshold_pace else None,'pace':pace_string(threshold_pace,1) if threshold_pace else None,'source':'Manually entered' if settings.get('lthr') or settings.get('threshold_pace') else 'Garmin profile (if available)' if lthr else 'Unavailable','note':'A training estimate, not a laboratory measurement unless you entered a lab-tested value.'},
      'efficiency':efficiency[-80:],'efficiency_comparison':comparison,
      'recent':recent,'insights':insights,'race_projection':race_est,'goal':{'distance':goal_distance,'seconds':goal_seconds,'time':clock(goal_seconds) if goal_seconds else None,'target_pace':pace_string(goal_seconds,goal_distance/1000) if goal_seconds else None},
      'coverage':{'activities':runs,'detailed':details_count,'percent':round(100*details_count/runs) if runs else 0},
    }
