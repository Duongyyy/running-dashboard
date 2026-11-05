'use strict';
let data=null,page='overview',demo=false,period='12w',lastSyncRunning=false,toastTimer=null;
let explorer={q:'',offset:0,limit:30,total:0,items:[]};
const $=s=>document.querySelector(s), $$=s=>Array.from(document.querySelectorAll(s));
const safe=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const n=(value,d=0)=>value==null||!Number.isFinite(Number(value))?'—':Number(value).toLocaleString('en-AU',{maximumFractionDigits:d,minimumFractionDigits:d});
const prettyDate=s=>s?new Date(String(s).slice(0,10)+'T12:00:00').toLocaleDateString('en-AU',{day:'numeric',month:'short',year:'numeric'}):'Not available';
const formatSec=s=>{if(s==null)return '—';let v=Math.round(Number(s)),h=Math.floor(v/3600),m=Math.floor(v%3600/60),sec=v%60;return h?`${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`:`${m}:${String(sec).padStart(2,'0')}`;};
const pace=s=>!s?'—':`${Math.floor(s/60)}:${String(Math.round(s)%60).padStart(2,'0')}/km`;
const percent=(x,t)=>t?Math.round(x/t*100):0;
let sitePayload=null;
async function api(url,opt={}){
 if(opt.method && opt.method.toUpperCase()!=='GET') throw Error('The GitHub Pages dashboard is read-only. Garmin sync runs automatically in GitHub Actions.');
 if(url==='/api/state') return sitePayload?.public_state || null;
 if(url==='/api/sync-status') return {running:false};
 if(url.startsWith('/api/activities')){
   const u=new URL(url,'https://local.invalid');
   const q=(u.searchParams.get('q')||'').trim().toLowerCase();
   const offset=Math.max(0,Number(u.searchParams.get('offset'))||0);
   const limit=Math.min(100,Math.max(1,Number(u.searchParams.get('limit'))||30));
   const source=sitePayload?.activity_feed||[];
   const filtered=q?source.filter(a=>[a.name,a.date,String(a.km)].some(v=>String(v||'').toLowerCase().includes(q))):source;
   return {total:filtered.length,offset,limit,items:filtered.slice(offset,offset+limit)};
 }
 if(url.startsWith('/api/activity/')){
   const id=decodeURIComponent(url.slice('/api/activity/'.length));
   const act=(sitePayload?.activity_feed||[]).find(x=>x.id===id);
   if(!act) throw Error('That activity is not included in the published history.');
   return {id,name:act.name,date:act.date,distance:act.km*1000,duration:act.duration_seconds,avg_hr:act.hr,
           detail_status:act.detail_status,source:'Published Garmin summary (no GPS or FIT file)',
           samples:(sitePayload?.activity_hr_streams||{})[id]||[]};
 }
 throw Error('This feature needs the private local application.');
}
function toast(message,error=false){const el=$('#toast');el.textContent=message;el.classList.toggle('error',error);el.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('show'),4400);}
async function refresh(){
 try{
   const response=await fetch('./data.json?refresh='+Date.now(),{cache:'no-store'});
   if(!response.ok) throw Error('Published Garmin data not found. Check the most recent GitHub Actions deployment.');
   sitePayload=await response.json();
   if(!sitePayload.public_state) throw Error('The published data is from an older Stride Lab version. Run GitHub Actions again.');
   data=sitePayload.public_state;
   render();
 }catch(e){$('#main').innerHTML=`<div class="notice warning">Could not load dashboard: ${safe(e.message)}</div>`;}
}
const heading=(title,desc='',controls='')=>`<div class="page-lead"><div><div class="eyebrow">RUNNING PERFORMANCE / ${safe(page.toUpperCase())}</div><h1 class="page-title">${title}</h1><p class="desc">${desc}</p></div>${controls?`<div class="toolbar">${controls}</div>`:''}</div>`;
const empty=(title,body)=>`<div class="empty"><div class="empty-icon">↗</div><b>${title}</b><p>${body}</p></div>`;
const panel=(title,subtitle,content,button='')=>`<section class="panel"><div class="panel-head"><div><h3>${title}</h3>${subtitle?`<div class="subtle" style="margin-top:6px">${subtitle}</div>`:''}</div>${button}</div><div class="panel-content">${content}</div></section>`;
const colors=['#7996ba','#74aefb','#78cba1','#efc47a','#ee817b'];
function periodControls(){return `<span class="period-label">VIEW</span><select id="period-select" class="select"><option value="8w" ${period==='8w'?'selected':''}>Last 8 weeks</option><option value="12w" ${period==='12w'?'selected':''}>Last 12 weeks</option><option value="20w" ${period==='20w'?'selected':''}>Last 20 weeks</option><option value="12m" ${period==='12m'?'selected':''}>Last 12 months</option></select>`;}
function volumeRows(){return period==='12m'?data.months:data.weeks.slice(period==='8w'?-8:period==='20w'?-20:-12)};
function barChart(rows,key='km',label='label',unit='km'){
 if(!rows?.length||rows.every(r=>!Number(r[key])))return empty('No mileage to chart yet','Sync runs to see your weekly volume history.');
 const W=680,H=214,l=36,t=13,b=32,r=7,plot=H-t-b,max=Math.max(...rows.map(x=>Number(x[key])||0),5)*1.13;
 const step=(W-l-r)/rows.length,bar=Math.min(27,step*.64);let svg=`<svg class="svg-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Training volume bar chart">`;
 for(let i=0;i<4;i++){let y=t+plot*i/3,v=max*(1-i/3);svg+=`<line class="grid-line" x1="${l}" y1="${y}" x2="${W-r}" y2="${y}"/><text class="axis-text" x="${l-7}" y="${y+3}" text-anchor="end">${Math.round(v)}</text>`;}
 rows.forEach((x,i)=>{let v=Number(x[key])||0,hh=plot*v/max,xx=l+i*step+step/2,yy=t+plot-hh;svg+=`<rect class="bar" x="${(xx-bar/2).toFixed(1)}" y="${yy.toFixed(1)}" width="${bar.toFixed(1)}" height="${Math.max(1,hh).toFixed(1)}" rx="4"><title>${safe(x[label])}: ${v.toFixed(1)} ${unit}</title></rect>`;let stride=Math.max(1,Math.ceil(rows.length/7));if(i%stride===0)svg+=`<text class="axis-text" x="${xx.toFixed(1)}" y="${H-11}" text-anchor="middle">${safe(x[label])}</text>`});
 return svg+'</svg>';
}
function lineChart(rows,key='seconds',label='date',opts={}){
 if(!rows?.length)return empty('Not enough records yet','Detailed workouts are needed to populate this trend.');
 const W=680,H=215,l=46,t=14,b=31,r=12,plot=H-t-b;
 let values=rows.map(r=>Number(r[key])).filter(Number.isFinite);if(!values.length)return empty('No numeric values','There are no comparable measurements in this period.');
 let min=Math.min(...values),max=Math.max(...values);let pad=Math.max(1,(max-min)*.17);min-=pad;max+=pad;
 const x=i=>l+(W-l-r)*(rows.length===1?.5:i/(rows.length-1));const y=v=>t+(max-v)/(max-min)*plot;
 let svg=`<svg class="svg-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Performance trend chart">`;
 for(let i=0;i<4;i++){let val=max-i*(max-min)/3,yy=y(val);svg+=`<line class="grid-line" x1="${l}" y1="${yy}" x2="${W-r}" y2="${yy}"/><text class="axis-text" x="${l-7}" y="${yy+3}" text-anchor="end">${opts.pace?formatSec(val):Math.round(val)}</text>`;}
 const coordinates=rows.map((item,i)=>[x(i),y(item[key])]);
 const points=coordinates.map(z=>z.map(v=>v.toFixed(2)).join(',')).join(' ');
 const line=opts.color||'#b8f56a';
 if(rows.length>1){svg+=`<polygon points="${l},${t+plot} ${points} ${x(rows.length-1)},${t+plot}" fill="${line}" opacity=".07"/><polyline points="${points}" fill="none" stroke="${line}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`}
 rows.forEach((row,i)=>{let [xx,yy]=coordinates[i];if(rows.length<45||i%2===0)svg+=`<circle cx="${xx.toFixed(1)}" cy="${yy.toFixed(1)}" r="3.4" fill="${line}" stroke="#111c25" stroke-width="1.6"><title>${safe(row[label])} — ${opts.pace?formatSec(row[key]):row[key]}</title></circle>`;});
 const k=Math.max(1,Math.ceil((rows.length-1)/5));rows.forEach((r,i)=>{if(i%k===0||i===rows.length-1)svg+=`<text class="axis-text" x="${x(i)}" y="${H-9}" text-anchor="middle">${safe(String(r[label]).slice(5,10)||r[label])}</text>`});
 return svg+'</svg>';
}
function recordSummaryRow(rec,i){let name=safe(rec.name);return `<div class="record-row"><span class="record-rank">${i+1}</span><div class="record-info"><div class="record-name">${name}</div><div class="record-sub">${rec.date?prettyDate(rec.date):'Awaiting complete data'} · ${safe(rec.pace)}</div></div><div class="record-time">${safe(rec.time)}</div></div>`;}
function renderInsights(short=false){let items=short?data.insights.slice(0,3):data.insights;return items.map(i=>`<div class="insight-item"><span class="insight-symbol">${i.type==='volume'?'↗':i.type==='quality'?'◷':i.type==='consistency'?'▦':'✳'}</span><div><b>${safe(i.title)}</b><p>${safe(i.body)}</p></div></div>`).join('')||empty('No insights','Import training activity to unlock meaningful observations.');}
function selectedPBS(){return ['5 km','10 km','Half marathon','Marathon'].map(n=>data.pbs.find(r=>r.name===n));}
function dashboardHero(){const connected=data.connection?.connected||demo,s=data.summary;
 return `<section class="hero"><div><div class="hero-label">THE LONG GAME. IN FOCUS.</div><h2>${connected?'Every kilometre tells a story.':'Your running. Finally, all in one place.'}</h2><p>${connected?`Explore ${n(s.runs)} running activities, spot meaningful trends and use your data to guide your next training block.`:'Connect your Garmin account to turn your running history into personal records, heart-rate guidance and actionable training trends.'}</p><div class="hero-actions">${!connected?`<button class="accent-btn" data-action="open-settings">Connect Garmin →</button><button class="secondary-btn" data-action="demo">Explore sample view</button>`:`<button class="accent-btn" data-page="trends">Explore training trends →</button>${demo?'<button class="secondary-btn" data-action="exit-demo">Exit sample mode</button>':''}`}</div></div><div class="hero-right"><div class="hero-rings"><div class="hero-rings-inner"><small>RUNS</small><b>${connected?n(s.runs):'—'}</b><small>ALL TIME</small></div></div></div></section>`;
}
function statCard(label,value,foot,glyph='↗'){return `<div class="stat-card"><div class="stat-top"><span class="stat-label">${label}</span><span class="stat-glyph">${glyph}</span></div><div class="stat-value">${value}</div><div class="stat-foot">${foot}</div></div>`;}
function overview(){const picks=selectedPBS(),summary=data.summary,threshold=data.threshold,zones=data.zones,weekSum=data.weeks.slice(-4).reduce((a,x)=>a+x.km,0);
 let pbs=picks.map((x,i)=>statCard(x.name.toUpperCase()+' PB',safe(x.time),x.date?prettyDate(x.date)+' · '+safe(x.pace):'Awaiting valid effort',i%2?'↗':'◈')).join('');
 let zoneContent=zones.available?`<div class="signal-wrap"><div><div class="signal-caption">LACTATE THRESHOLD HR</div><div class="signal-big">${threshold.lthr??'—'}<small> bpm</small></div><span class="subtle">${safe(threshold.source)}</span></div><div><div class="signal-caption">RECOMMENDED EASY HR</div><div class="signal-big" style="font-size:26px">${zones.easy[0]}–${zones.easy[1]}<small> bpm</small></div><span class="subtle">Based on ${safe(zones.selected.toUpperCase())}</span></div></div>${zoneGraphic()}<p class="detail-line" style="margin-top:15px">${safe(zones.method)}</p>`:empty('Heart-rate zones need a reference','Enable physiology publication to show the imported Garmin-based zone calculations.');
 return heading('Performance overview','A clearer picture of how you run, where you are and what comes next.',periodControls())+dashboardHero()+`<div class="stat-grid">${pbs}</div>`+`<div class="grid-main">${panel('Weekly training volume','Consistency compounds. Your running kilometres over time.',barChart(volumeRows()),'<span class="pill">DISTANCE / KM</span>')}${panel('Physiology snapshot','Your training intensity guide at a glance.',zoneContent,'<button class="small-link" data-page="physiology">VIEW DETAILS ↗</button>')}</div>`+`<div class="grid-main">${panel('Training pulse','Volume, frequency and aerobic foundation.',`<div class="mini-kpis"><div class="mini-kpi"><span>THIS WEEK</span><strong>${n(summary.this_week_km,1)} km</strong></div><div class="mini-kpi"><span>LAST 28 DAYS</span><strong>${n(summary.last_28_km,1)} km</strong></div><div class="mini-kpi"><span>RUNS LOGGED</span><strong>${n(summary.runs)}</strong></div></div><div class="divider"></div><div class="micro">RECENT CONSISTENCY · LAST 14 WEEKS</div>${heatMap(98)}<div class="detail-line">Detailed streams: ${summary.detailed_runs} / ${summary.runs} runs. Record accuracy improves as FIT streams sync.</div>`)}${panel('What your data says','Practical insights, not a generic fitness score.',renderInsights(true),'<button class="small-link" data-page="insights">ALL INSIGHTS ↗</button>')}</div>`+(data.connection?.sync?.running?syncBanner():'');
}
function heatMap(days=98){let rows=data.heatmap.slice(-days),grid=[];for(let i=0;i<rows.length;i++){let item=rows[i],lev=item.km<=0?0:item.km<5?1:item.km<10?2:item.km<16?3:4;grid.push(`<div class="heatcell ${lev?'level'+lev:''}" title="${item.date}: ${n(item.km,1)} km"></div>`)}return `<div class="heatmap">${grid.join('')}</div><div class="mini-meta"><span>Less <span style="color:#3e6044">■</span> <span style="color:#6eac61">■</span> <span style="color:#b8f56a">■</span> More</span><span>Daily distance · 14 weeks</span></div>`;}
function zoneGraphic(){let totals=data.time_in_zone||[],sum=totals.reduce((a,b)=>a+b,0);if(!data.zones.available)return '';return `<div class="zone-graphic">${totals.map((v,i)=>`<span style="flex:${sum?Math.max(v/sum,0.007):1};background:${colors[i]}" title="Z${i+1}: ${formatSec(v)}"></span>`).join('')}</div><div class="zone-legend">${totals.map((v,i)=>`<span>Z${i+1}<br>${sum?percent(v,sum)+'%':'—'}</span>`).join('')}</div>`;}
function intensityHistory(){
 const rows=data.intensity_weeks||[];
 const valid=rows.filter(r=>r.total_seconds>0);
 if(!valid.length)return empty('Detailed HR data needed','Import detailed FIT activities and add a defensible heart-rate reference to see your intensity by week.');
 return `<div class="intensity-history">${rows.map(row=>{
    const total=row.total_seconds||0;
    const parts=total?row.seconds.map((seconds,i)=>`<span style="width:${100*seconds/total}%;background:${colors[i]}" title="Z${i+1}: ${formatSec(seconds)}"></span>`).join(''):'<span class="intensity-none"></span>';
    return `<div class="intensity-week"><span>${safe(row.label)}</span><div class="intensity-strip">${parts}</div><span>${total?formatSec(total):'No HR'}</span></div>`;
 }).join('')}</div><div class="zone-key">${['Recovery','Easy','Steady','Threshold','Hard'].map((x,i)=>`<span><i style="background:${colors[i]}"></i>Z${i+1} ${x}</span>`).join('')}</div><p class="detail-line">Only timestamped HR samples counted. Missing or unclassified time is excluded; the balance reflects the currently selected zone model.</p>`;
}
function nextFocus(){
 const items=data.upcoming_guidance||[];
 return items.length?items.map((item,i)=>`<div class="insight-item"><span class="insight-symbol">${i+1}</span><div><b>${safe(item.title)}</b><p>${safe(item.text)}</p><div class="detail-line">Basis: ${safe(item.signal)}</div></div></div>`).join(''):empty('Training history required','Import running data to unlock tailored, data-grounded guidance for the next training block.');
}
function records(){let info=panel('Personal records','Calculated in-activity records depend on detailed FIT streams.',`<div class="table-scroller"><table class="data-table"><thead><tr><th>Distance</th><th>Best effort</th><th>Avg. pace</th><th>Date</th><th>Evidence</th></tr></thead><tbody>${data.pbs.map((p,i)=>`<tr><td><b>${safe(p.name)}</b>${p.official?`<div class="detail-line" style="color:var(--lime)">Official: ${p.official.time}</div>`:''}</td><td class="big">${safe(p.time)}</td><td>${safe(p.pace)}</td><td>${p.date?prettyDate(p.date):'—'}</td><td>${p.activity_id?`<button class="table-link" data-activity="${safe(p.activity_id)}">${p.kind==='recorded_segment'?'FIT segment ↗':'Approx. activity ↗'}</button>`:safe(p.source||'—')}</td></tr>`).join('')}</tbody></table></div>`);
 let trends=panel('5K best-effort progression','Only recorded 5K efforts imported into the detailed history are included.',lineChart(data.pb_trend_5k,'seconds','date',{pace:true})+(data.pb_trend_5k.length?`<div class="detail-line">Each step represents a new fastest FIT-recorded 5 km effort, not a model prediction.</div>`:''));
 let official=panel('Add an official race result','Keep race-chip times distinct from GPS-derived efforts.',`<form id="official-form"><div class="two-field"><div class="form-control"><label>DISTANCE</label><select name="distance">${data.pbs.map(p=>`<option value="${p.meters}">${safe(p.name)}</option>`).join('')}</select></div><div class="form-control"><label>OFFICIAL FINISH TIME (HH:MM:SS)</label><input name="time" placeholder="1:45:30" required></div><div class="form-control"><label>RACE DATE</label><input type="date" name="date" required></div></div><button type="submit" class="accent-btn">Save official result</button></form>`);
 return heading('Your personal bests','Every distance. Every breakthrough. Based on recorded evidence.')+`<div class="notice">Records are grouped by evidence: continuous FIT segments, close-distance Garmin activity summaries and manually entered official race results. Garmin summary-only activities cannot prove their fastest internal splits.</div><div class="grid-main" style="grid-template-columns:minmax(0,1.65fr) minmax(280px,1fr)">${info}${panel('Your key distances','Popular distance records at a glance.',selectedPBS().map(recordSummaryRow).join(''))}</div><div class="grid-half">${trends}${panel('Read-only published records','Manual race results are added in your local dashboard.',`<p class="detail-line">Race records and calculated Garmin best efforts update here after the next scheduled GitHub Actions sync. No changes can be made from this public site.</p>`)}</div>`;
}
function physiology(){
 const z=data.zones,t=data.threshold,settings=data.connection?.settings||{},source=data.connection?.profile||{};
 const bpm=t.lthr?`${t.lthr} <small>bpm</small>`:'—';
 const zoneRows=z.available?`<table class="zone-table"><thead><tr><th>Zone</th><th>Heart rate</th><th>Training purpose</th></tr></thead><tbody>${z.zones.map((x,i)=>`<tr><td><span class="zone-pill" style="background:${colors[i]}">${x.name}</span></td><td><b>${x.low}–${x.high} bpm</b></td><td>${safe(x.purpose)}</td></tr>`).join('')}</tbody></table><p class="detail-line" style="margin-top:13px">${safe(z.method)}</p>`:empty('No published HR reference','Enable physiology publication in GitHub repository variables to show Garmin-based zones.');
 const lt=panel('Lactate threshold','Device-supported or user-entered reference; never fabricated.',`<div class="signal-wrap"><div><div class="signal-caption">THRESHOLD HEART RATE</div><div class="signal-big">${bpm}</div></div><div><div class="signal-caption">THRESHOLD PACE</div><div class="signal-big" style="font-size:28px">${safe(t.pace||'—')}</div></div></div><div class="divider"></div><div class="detail-line"><b>Source:</b> ${safe(t.source)}<br><b>Interpretation:</b> ${safe(t.note)}<br><b>History:</b> No historical threshold series is fabricated from a single current measurement.</div><div class="notice">A lactate threshold HR estimate cannot directly establish your aerobic threshold. Consider a supported field test or laboratory assessment to calibrate your zone model.</div><button class="secondary-btn" data-page="settings">View data source →</button>`);
 let zoneShare=empty('Awaiting HR settings','Time-in-zone calculations need a zone model.');
 if(z.available){
   const total=data.time_in_zone.reduce((a,b)=>a+b,0);
   const parts=z.zones.map((x,i)=>{let v=data.time_in_zone[i];return `<div class="mini-meta" style="justify-content:space-between;margin:12px 0"><span style="color:${colors[i]};font-weight:800">${x.name} · ${safe(x.purpose)}</span><strong>${formatSec(v)} · ${total?percent(v,total):0}%</strong></div><div class="hr-progress"><span style="width:${total?percent(v,total):0}%;background:${colors[i]}"></span></div>`}).join('');
   zoneShare=zoneGraphic()+'<div class="divider"></div>'+parts;
 }
 const physiologySummary=`<div class="mini-kpis"><div class="mini-kpi"><span>MAX HR</span><strong>${n(settings.max_hr||source.max_hr)} bpm</strong></div><div class="mini-kpi"><span>REST HR</span><strong>${n(settings.rest_hr||source.rest_hr)} bpm</strong></div><div class="mini-kpi"><span>LTHR</span><strong>${n(settings.lthr||source.lthr)} bpm</strong></div></div><div class="divider"></div><p class="detail-line">Heart-rate values are only used if provided by an identified Garmin profile field or manually entered in Settings. Available fields vary by Garmin device and API endpoint.</p><button class="secondary-btn" data-page="settings">Edit HR settings</button>`;
 return heading('Heart rate & physiology','Grounded guidance for easy runs, threshold sessions and sustainable training.')+
 `<div class="stat-grid">${statCard('LTHR',t.lthr?`${t.lthr} bpm`:'—',t.source,'♡')}${statCard('THRESHOLD PACE',safe(t.pace||'—'),'Only when supported','↗')}${statCard('EASY TRAINING HR',z.available?`${z.easy.join('–')} bpm`:'—',z.available?'Illustrative zone model':'Requires reference','◈')}${statCard('ZONE MODEL',z.available?safe(z.selected.toUpperCase()):'—','Garmin-synced reference','▤')}</div>`+
 `<div class="grid-half">${panel('Personalised heart-rate zones','Five-zone model with transparent reference values.',zoneRows)}${lt}</div>`+
 `<div class="grid-half">${panel('Actual time in each zone','Based on FIT heart-rate streams, not Garmin summary averages.',zoneShare)}${panel('Your physiology settings','The dashboard never treats an observed peak as a verified HR max.',physiologySummary)}</div>`;
}
function trends(){const s=data.summary,eff=data.efficiency,comparison=data.efficiency_comparison,effPlot=eff.map(e=>({date:e.date,seconds:e.pace}));
 return heading('Training trends','Training volume, endurance, heart-rate distribution and aerobic performance over time.',periodControls())+
 `<div class="stat-grid">${statCard('LAST 28 DAYS',`${n(s.last_28_km,1)} km`,'Rolling 28-day distance')}${statCard('RUNNING TIME',`${n(s.hours_28,1)} hrs`,'Last 28 days')}${statCard('12-WEEK CONSISTENCY',`${n(s.active_weeks_12)}/12`,'Weeks with recorded runs')}${statCard('LONGEST RUN',`${n(s.longest_km,1)} km`,'Available activity history')}</div>`+
 `<div class="grid-main">${panel('Weekly running mileage','Progression with distance and running frequency.',barChart(volumeRows()),'<span class="pill">KM / WEEK</span>')}${panel('Consistency calendar','Recent running activity, day by day.',heatMap(98))}</div>`+
 `<div class="grid-half">${panel('Longest run each week','Endurance progression across the last 20 weeks.',barChart(data.long_runs||[], 'km'),'<span class="pill">KM / LONG RUN</span>')}${panel('Weekly time in HR zones','Intensity distribution based on measured FIT streams.',intensityHistory())}</div>`+
 `<div class="grid-half">${panel('Running pace trends','Recorded training runs; weather, terrain and session type may differ.',effPlot.length?lineChart(effPlot,'seconds','date',{pace:true,color:'#74aefb'}):empty('Not enough paired data','Import runs with average pace and heart rate.'),'<span class="pill">PACE / KM</span>')}${panel('Aerobic pace at comparable HR','Observational comparison within a narrow heart-rate range.',comparison?`<div class="signal-caption">COMPARISON BAND</div><div class="signal-big">${comparison.hr_band.join('–')}<small> bpm</small></div><div class="mini-kpis"><div class="mini-kpi"><span>EARLY PACE</span><strong>${pace(comparison.early_pace)}</strong></div><div class="mini-kpi"><span>RECENT PACE</span><strong>${pace(comparison.recent_pace)}</strong></div><div class="mini-kpi"><span>CHANGE</span><strong>${comparison.delta_sec>0?'+':''}${comparison.delta_sec}s/km</strong></div></div><div class="notice">${safe(comparison.caution)} Not a controlled fitness test.</div>`:empty('More comparable runs needed','At least six runs in a narrow average HR band are required for a descriptive comparison.'))}</div>`+
 `<div class="grid-half">${panel('Monthly mileage','Last 12 calendar months.',barChart(data.months))}${panel('Recent running activities','Open a run for details and available HR samples.',recentActivities(10))}</div>`;
}

function recentActivities(limit){if(!data.recent.length)return empty('No activities yet','Connect Garmin or import FIT files.');return `<div class="table-scroller"><table class="data-table"><thead><tr><th>Run</th><th>Distance</th><th>Pace</th><th>HR</th></tr></thead><tbody>${data.recent.slice(0,limit).map(r=>`<tr><td><button class="table-link" data-activity="${safe(r.id)}">${safe(r.name)}</button><div class="detail-line">${prettyDate(r.date)}</div></td><td>${n(r.km,2)} km</td><td>${safe(r.pace)}</td><td>${r.hr||'—'}</td></tr>`).join('')}</tbody></table></div>`;}
function activities(){
 let items=demo?data.recent||[]:explorer.items||[],count=demo?items.length:explorer.total;
 return heading('Activity explorer','Search your full running archive and open an individual workout to inspect available HR samples.')+
 `<section class="panel"><div class="panel-head"><div><h3>All running activities</h3><div class="subtle" style="margin-top:6px">${n(count)} matching runs ${demo?'· sample only':'· published Garmin summaries'}</div></div><span class="pill">${demo?'SAMPLE':'PUBLISHED HISTORY'}</span></div><div class="panel-content"><form id="activity-search-form" class="archive-search"><input name="query" aria-label="Search runs" placeholder="Search activity name or date (e.g. October 2026)" value="${safe(explorer.q)}"><button class="secondary-btn" type="submit">Search</button></form><div class="table-scroller"><table class="data-table"><thead><tr><th>Activity</th><th>Distance</th><th>Time</th><th>Pace</th><th>HR</th><th>Detail</th></tr></thead><tbody>${items.map(r=>`<tr><td><button class="table-link" data-activity="${safe(r.id)}">${safe(r.name)}</button><div class="detail-line">${prettyDate(r.date)}</div></td><td>${n(r.km,2)} km</td><td>${r.time||formatSec(r.seconds)}</td><td>${safe(r.pace||'—')}</td><td>${r.hr||'—'}</td><td>${r.detail_status==='ready'?'<span style="color:var(--mint)">FIT</span>':'Summary'}</td></tr>`).join('')||`<tr><td colspan="6">${demo?'No synthetic activities.':'No runs match this search.'}</td></tr>`}</tbody></table></div>${demo?'':`<div class="archive-pager"><span>${n(count)?`${n(explorer.offset+1)}–${n(Math.min(count,explorer.offset+explorer.limit))} of ${n(count)}`:'0 runs'}</span><div><button class="secondary-btn" id="prev-activities" ${explorer.offset===0?'disabled':''}>Previous</button><button class="secondary-btn" id="next-activities" ${explorer.offset+explorer.limit>=count?'disabled':''}>Next</button></div></div>`}</div></section>`;
}
async function loadActivities(){
 if(demo){render();return;}
 try{const result=await api(`/api/activities?q=${encodeURIComponent(explorer.q)}&limit=${explorer.limit}&offset=${explorer.offset}`);explorer={...explorer,...result};render()}
 catch(err){toast(err.message,true)}
}
function insights(){let rs=data.race_projection;
 return heading('Training intelligence','Practical, explainable guidance driven by your running history.')+
 `<div class="grid-main">${panel('Patterns worth noticing','Weekly observations based on recorded activity.',renderInsights()+`<div class="notice">These are deterministic summaries, not medical advice or an AI-generated training prescription. Review them alongside recovery and how you feel.</div>`)}${panel('Goal pace & race estimate','Separate your target from a model-derived projection.',`<div class="goal-card"><div class="signal-caption">YOUR TARGET DISTANCE</div><div class="goal-number">${data.goal.distance===21097.5?'Half marathon':data.goal.distance===42195?'Marathon':n(data.goal.distance/1000,1)+' km'}</div><p class="detail-line">${data.goal.time?`Goal finish: ${data.goal.time} · Target pace: ${safe(data.goal.target_pace||'—')}`:'Set a goal finish time in Settings.'}</p></div><div class="divider"></div>${rs?`<div class="signal-caption">MODEL-BASED PROJECTION</div><div class="signal-big">${safe(rs.time)}</div><p class="detail-line">Based on ${safe(rs.source_distance)} using a Riegel exponent. ${safe(rs.note)}</p>`:empty('Not enough performance evidence','A recorded effort at a suitable distance is needed for a race projection.')}<button class="secondary-btn" data-page="settings">View published goal →</button>`)}</div>`+
 `<div class="grid-half">${panel('Your next training focus','Training signals grounded in your own recent running history.',nextFocus())}${panel('Evidence quality','Know when your data is complete enough for decisions.',`<div class="signal-caption">DETAILED STREAM COVERAGE</div><div class="signal-big">${data.coverage.percent}<small>%</small></div><div class="hr-progress" style="height:12px"><span style="width:${data.coverage.percent}%"></span></div><div class="detail-line">${n(data.coverage.detailed)} of ${n(data.coverage.activities)} runs contain detailed timestamped streams.</div><div class="divider"></div><p class="detail-line">Summary-only runs support total mileage but cannot prove internal-distance PBs, measured time-in-zone or high-resolution pace trends. Race predictions are estimates only.</p>`)}</div>`;
}

function syncBanner(){let s=data.connection.sync;return `<div class="notice" style="display:flex;gap:12px;align-items:center"><span class="spinner"></span><div><b>Sync in progress: ${safe(s.phase)}</b><br><span class="detail-line">${n(s.activities_seen)} activities scanned · ${n(s.details_done)} FIT streams downloaded · ${n(s.details_failed)} unavailable</span></div></div>`;}
function settings(){
 const sync=sitePayload?.sync||{},refs=data.connection?.profile||{},f=sitePayload?.physiology_shared;
 return heading('About this dashboard','The online version of your private Stride Lab application: same performance views, read-only data.')+
 `<div class="grid-half">${panel('Garmin synchronisation','Automated by GitHub Actions, not your computer.',
 `<div class="notice">Garmin import is configured in GitHub repository secrets. No key is stored in the published website.</div>
 <div class="mini-kpis"><div class="mini-kpi"><span>ACTIVITIES</span><strong>${n(data.summary.runs)}</strong></div>
 <div class="mini-kpi"><span>DETAILED FIT</span><strong>${n(data.coverage.detailed)}</strong></div></div>
 <p class="detail-line">Last successful sync: ${safe(sync.garmin_last_success||'Awaiting first run')}<br>
 Historical archive scan complete: ${sync.historical_archive_complete?'Yes':'Not confirmed'}<br>
 Detailed FIT files still pending: ${n(sync.fits_pending)}</p>
 <p class="detail-line">To sync immediately, open your GitHub repository → Actions → Stride Lab → Run workflow. Otherwise the workflow checks periodically while enabled.</p>`)}
 ${panel('Data-sharing controls','The website is publicly accessible, even when your source code is in a private repository.',
 `<div class="status-list"><div class="status-metric"><b>${f?'Published':'Not published'}</b><small>PHYSIOLOGY</small></div>
 <div class="status-metric"><b>${sitePayload.activity_feed_shared?'Published':'Not published'}</b><small>ACTIVITY SUMMARIES</small></div></div>
 <p class="detail-line">To change these options, use GitHub repository variables <code>PUBLISH_PHYSIOLOGY</code> and <code>PUBLISH_ACTIVITY_SUMMARIES</code>.</p>
 <div class="notice">GPS tracks, exact activity start times, raw FIT files, account information and Garmin API credentials are excluded from the public website.</div>`)}
 </div><div class="grid-half">
 ${panel('Garmin physiology references','Read-only values supplied through your configured Garmin reference settings.',
 `<div class="mini-kpis"><div class="mini-kpi"><span>MAX HR</span><strong>${n(refs.max_hr)} bpm</strong></div>
 <div class="mini-kpi"><span>REST HR</span><strong>${n(refs.rest_hr)} bpm</strong></div>
 <div class="mini-kpi"><span>LTHR</span><strong>${n(refs.lthr)} bpm</strong></div></div>
 <p class="detail-line">${refs.garmin_zone_floors?.length?'Garmin running-zone floors: '+refs.garmin_zone_floors.join(' · ')+' bpm.':'No Garmin configured zone boundaries published.'}</p>`)}
 ${panel('Your goal','Training goals and physiological settings can be changed in the local dashboard only.',
 `<div class="goal-card"><div class="signal-caption">GOAL DISTANCE</div><div class="signal-big">${n(data.goal.distance/1000,1)} km</div><div class="detail-line">Published target: ${safe(data.goal.time||'Not set')}</div></div>`)}
 </div>`;
}
function render(){if(!data)return;const connected=data.connection?.connected&&!demo;
 $('#crumb').textContent=({overview:'Overview',records:'Personal bests',physiology:'Heart rate & LT',trends:'Training trends',activities:'Activity explorer',insights:'Training insights',settings:'Connections & settings'})[page];
 $$('.nav-item').forEach(el=>el.classList.toggle('active',el.dataset.page===page));
 $('#demo-indicator').classList.toggle('hidden',!demo);
 $('#connection-badge').innerHTML=`<span class="pulse-dot online"></span> Garmin data published`;
 $('#side-dot').classList.toggle('online',connected);
 $('#side-source').textContent=demo?'Viewing sample data':connected?data.connection.last_sync?`Last synced ${prettyDate(data.connection.last_sync)}`:'Connected · awaiting sync':'Not connected';
 $('#sync-btn').disabled=Boolean(data.connection?.sync?.running);
 $('#sync-btn').innerHTML=`<span class="rotatable">↻</span> Refresh view`;
 $('#main').innerHTML=({overview,records,physiology,trends,activities,insights,settings})[page]();
}
function setPage(next){if(!['overview','records','physiology','trends','activities','insights','settings'].includes(next))return;if(next==='settings'&&demo){demo=false;page=next;refresh();return}page=next;$$('.sidebar').forEach(x=>x.classList.remove('open'));if(next==='activities'&&!demo)loadActivities();else render();window.scrollTo({top:0,behavior:'smooth'});}
async function demoToggle(value){demo=value;if(value)toast('Sample mode: all displayed figures are fictional.');else toast('Back to your own workspace.');await refresh();}
async function changeSync(full){try{const r=await api('/api/sync?full='+String(full),{method:'POST'});toast(r.message);await refresh()}catch(e){toast(e.message,true)}}
async function showActivity(id){try{let act=await api('/api/activity/'+encodeURIComponent(id));let pts=act.samples||[];let sample=pts.filter((_,i)=>i%Math.max(1,Math.floor(pts.length/100))===0).filter(x=>x.hr).map(x=>({date:`${x.minute} min`,hr:x.hr}));
 $('#modal-root').innerHTML=`<div class="modal-cover" id="modal-cover"><div class="modal"><button class="modal-close" id="modal-close">✕</button><div class="eyebrow">ACTIVITY DETAIL</div><h3>${safe(act.name)}</h3><div class="mini-meta"><span>${prettyDate(act.date)}</span><span>${n(act.distance/1000,2)} km</span><span>${formatSec(act.duration)}</span><span>${act.avg_hr?Math.round(act.avg_hr)+' bpm':'No HR'}</span></div><div class="divider"></div><div class="section-heading">Recorded heart rate</div><div class="modal-canvas">${sample.length>1?lineChart(sample,'hr','date',{color:'#b8f56a'}):empty('Detailed HR stream not available','The FIT file may still be syncing or this was a summary-only activity.')}</div><p class="detail-line">Stream samples: ${n(pts.length)} · Data status: ${safe(act.detail_status)} · Source: ${safe(act.source)}. These details come from imported or Garmin activity records.</p></div></div>`;
 }catch(e){toast(e.message,true)}}
function parseTime(s){if(!s)return null;let parts=s.split(':').map(Number);if(parts.some(v=>!Number.isFinite(v)||v<0)||parts.length<2||parts.length>3)return null;if(parts.length===2)return parts[0]*60+parts[1];return parts[0]*3600+parts[1]*60+parts[2];}
async function submitSettings(form,which){let p={...(data.connection?.settings||{})};const f=new FormData(form);
 if(which==='phys'){
 for(let k of ['lthr','max_hr','rest_hr','threshold_pace'])p[k]=f.get(k)?Number(f.get(k)):null;
 p.zone_method=String(f.get('zone_method')||'auto');
 }else{
 p.goal_distance=Number(f.get('goal_distance'));
 p.goal_seconds=parseTime(String(f.get('goal_time')||''));
 if(f.get('goal_time')&&!p.goal_seconds)return toast('Use HH:MM:SS or MM:SS for your goal.',true);
 }
 try{await api('/api/settings',{method:'POST',body:JSON.stringify(p)});toast('Settings saved. Metrics recalculated.');await refresh()}catch(e){toast(e.message,true)}
}
// Event delegation handles rerenders, including dynamically created tables.
document.addEventListener('click',async e=>{
 const target=e.target.closest('button');if(!target)return;
 if(target.dataset.page){setPage(target.dataset.page);return}
 if(target.dataset.activity){showActivity(target.dataset.activity);return}
 if(target.dataset.action==='open-settings'){setPage('settings');return}
 if(target.dataset.action==='demo'){await demoToggle(true);return}
 if(target.dataset.action==='exit-demo'){await demoToggle(false);return}
 if(target.id==='mobile-nav'){$('.sidebar').classList.toggle('open');return}
 if(target.id==='settings-shortcut'){setPage('settings');return}
 if(target.id==='modal-close'){ $('#modal-root').innerHTML='';return}
 if(target.id==='sync-btn'){await refresh();toast('Showing the latest published data. Garmin synchronisation runs in GitHub Actions.');return}
 if(target.id==='prev-activities'){explorer.offset=Math.max(0,explorer.offset-explorer.limit);await loadActivities();return}
 if(target.id==='next-activities'){explorer.offset+=explorer.limit;await loadActivities();return}
 if(target.id==='sync-recent-btn'){await changeSync(false);return}
 if(target.id==='sync-full-btn'){await changeSync(true);return}
 if(target.id==='phys-refresh-btn'){target.disabled=true;target.textContent='Checking Garmin…';try{const result=await api('/api/physiology/refresh',{method:'POST'});await refresh();const fields=result.physiology_status?.available_fields||[];toast(fields.length?'Garmin reference values refreshed: '+fields.join(', '):'Garmin did not return supported physiology values. See diagnostics in Settings.',!fields.length)}catch(err){toast(err.message,true);target.disabled=false;target.textContent='↻ Refresh Garmin physiology'}return}
 if(target.id==='connect-btn'){
   let key=$('#garmin-key').value.trim();if(!key)return toast('Paste your Garmin Personal API key first.',true);
   target.disabled=true;target.textContent='Authenticating…';
   try{let result=await api('/api/connect',{method:'POST',body:JSON.stringify({key})});demo=false;$('#garmin-key').value='';toast(result.message);await refresh()}
   catch(err){const detail=$('#connect-error');if(detail){detail.textContent=err.message;detail.classList.remove('hidden');}toast('Garmin connection failed. See the explanation below the key field.',true);target.disabled=false;target.textContent='Connect Garmin account'}return;
 }
 if(target.id==='disconnect-btn'){
   if(!confirm('Disconnect Garmin? Your locally imported activity data will be retained.'))return;
   try{await api('/api/disconnect',{method:'POST'});toast('Key disconnected; local history retained.');await refresh()}catch(e){toast(e.message,true)}return;
 }
 if(target.id==='import-btn'){
   const el=$('#upload-file'),file=el.files?.[0];if(!file)return toast('Choose an activity file first.',true);
   target.disabled=true;target.textContent='Importing…';
   try{let out=await api('/api/import?filename='+encodeURIComponent(file.name),{method:'POST',body:await file.arrayBuffer(),headers:{'Content-Type':'application/octet-stream'}});toast(`${out.imported} activity file(s) imported.`);await refresh()}
   catch(err){toast(err.message,true)}finally{target.disabled=false;target.textContent='Import activity file'}return;
 }
});
document.addEventListener('change',e=>{if(e.target.id==='period-select'){period=e.target.value;render()}});
document.addEventListener('submit',async e=>{
 if(!['official-form','phys-form','goal-form','activity-search-form'].includes(e.target.id))return;e.preventDefault();const f=e.target;
 if(f.id==='activity-search-form'){explorer.q=String(new FormData(f).get('query')||'').trim();explorer.offset=0;await loadActivities();return}
 if(f.id==='phys-form'){if(demo)return toast('Exit sample mode before saving.',true);await submitSettings(f,'phys');return}
 if(f.id==='goal-form'){await submitSettings(f,'goal');return}
 if(demo)return toast('Exit sample mode before adding official results.',true);let form=new FormData(f),seconds=parseTime(String(form.get('time')));if(!seconds)return toast('Enter a valid finish time.',true);
 try{await api('/api/official-pb',{method:'POST',body:JSON.stringify({distance:Number(form.get('distance')),seconds,date:String(form.get('date')),description:'Official race result'})});toast('Official record saved.');await refresh()}catch(e){toast(e.message,true)}
});
let checkTimer=setInterval(async()=>{
 if(demo||!data?.connection?.connected)return;
 try{let status=await api('/api/sync-status');if(status.running){lastSyncRunning=true;if(page==='overview'||page==='settings')await refresh();}
 else if(lastSyncRunning){lastSyncRunning=false;toast(status.last_error?'Sync completed with errors.':'Garmin data refreshed.',!!status.last_error);await refresh();}}
 catch{}
},600000);
refresh();
