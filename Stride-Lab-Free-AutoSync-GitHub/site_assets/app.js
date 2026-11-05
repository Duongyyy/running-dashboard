/* Stride Lab public read-only dashboard. Uses only published aggregated data.json. */
'use strict';
let DATA = null;
let TAB = 'overview';
const $ = q => document.querySelector(q);
const esc = v => String(v ?? '—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const n = (x, d=1) => Number.isFinite(Number(x)) ? Number(x).toFixed(d) : '—';
const fmtDate = s => { if (!s) return 'Not available'; let d=new Date(`${String(s).slice(0,10)}T12:00:00`); return isNaN(+d) ? 'Not available' : new Intl.DateTimeFormat('en-AU',{day:'numeric',month:'short',year:'numeric'}).format(d); };
const count = x => Number(x||0).toLocaleString('en-AU');
const dateStamp = s => { if(!s)return 'Not synced'; let d = new Date(s); return isNaN(+d) ? 'Not synced' : d.toLocaleString('en-AU',{day:'numeric',month:'short',hour:'numeric',minute:'2-digit',timeZone:'Australia/Melbourne'}); };
const title = (label,desc) => `<div class="eyebrow">RUNNING PERFORMANCE / ${esc(label.toUpperCase())}</div><h1 class="heading">${esc(label)}</h1><p class="lead">${esc(desc)}</p>`;
const card = (label, value, detail) => `<div class="stat"><div class="k">${esc(label)}</div><div class="v">${esc(value ?? '—')}</div><div class="s">${esc(detail ?? '')}</div></div>`;
const box = (name,subtitle,inner) => `<section class="card"><h3>${esc(name)}</h3>${subtitle?`<p class="sub">${esc(subtitle)}</p>`:''}${inner}</section>`;
const pb = d => DATA?.pbs?.find(v => String(v.name).toLowerCase()===String(d).toLowerCase()) || {};
const numbers = arr => (arr||[]).map(v => Number(v)||0);
const zoneColors=['#7f96a5','#4a9be0','#4bbd8e','#f4b847','#f47c6f'];
function plotBars(series,labelKey,valueKey){
  const values = series.map(a => Math.max(0,Number(a[valueKey])||0));
  if(!values.length)return '<div class="empty">No data yet.</div>';
  const W=650,H=225,top=20,bottom=37,left=34,right=10,max=Math.max(1,...values)*1.15;
  const innerW=W-left-right,innerH=H-top-bottom, step=innerW/values.length,bw=Math.max(3,step*.63);
  let axes=[0,.25,.5,.75,1].map(k=>{let y=top+(1-k)*innerH; return `<line class="gridline" x1="${left}" y1="${y}" x2="${W-right}" y2="${y}"/><text x="4" y="${y+4}" class="chartlabel">${Math.round(k*max)}</text>`}).join('');
  let bars=values.map((v,i)=>{let bh=v/max*innerH,x=left+i*step+(step-bw)/2,y=top+innerH-bh;let label=String(series[i][labelKey]||'');return `<rect class="bar" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(0,bh).toFixed(1)}" rx="3"><title>${esc(label)}: ${n(v)} km</title></rect>`}).join('');
  let labels=series.map((v,i)=>i%(Math.max(1,Math.ceil(values.length/6)))===0?`<text class="chartlabel" x="${(left+i*step+step/2).toFixed(1)}" y="${H-8}" text-anchor="middle">${esc(v[labelKey])}</text>`:'').join('');
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(valueKey)} by ${esc(labelKey)}">${axes}${bars}${labels}</svg>`;
}
function plotLine(series,xKey,yKey,asPace=false){
  const pts=(series||[]).filter(x=>Number.isFinite(Number(x[yKey])) && Number(x[yKey])>0).map(v=>({...v,value:Number(v[yKey])}));
  if(pts.length<2)return '<div class="empty">Not enough data for a trend yet.</div>';
  const W=650,H=225,L=60,R=14,T=15,B=38;
  const lo=Math.min(...pts.map(x=>x.value)),hi=Math.max(...pts.map(x=>x.value));
  const span=Math.max(1,hi-lo), pad=span*.12;
  const xy=pts.map((v,i)=>[L+i*(W-L-R)/(pts.length-1),T+(1-(v.value-(lo-pad))/(span+2*pad))*(H-T-B)]);
  const path=xy.map(([x,y],i)=>`${i?'L':'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const ticks=[0,.25,.5,.75,1].map(k=>{let value=lo-pad+k*(span+2*pad),y=T+(1-k)*(H-T-B);return `<line class="gridline" x1="${L}" y1="${y}" x2="${W-R}" y2="${y}"/><text x="5" y="${y+4}" class="chartlabel">${asPace?pace(value):n(value,0)}</text>`}).join('');
  const labels=[0,Math.floor((pts.length-1)/2),pts.length-1].map(i=>`<text x="${xy[i][0]}" y="${H-9}" text-anchor="middle" class="chartlabel">${esc(String(pts[i][xKey]).slice(0,10))}</text>`).join('');
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Running progression">${ticks}<path class="line" d="${path}"/>${xy.map(([x,y],i)=>`<circle cx="${x}" cy="${y}" r="3.5" fill="#b8f86d"><title>${esc(pts[i][xKey])}: ${asPace?pace(pts[i].value):n(pts[i].value)}</title></circle>`).join('')}${labels}</svg>`;
}
function pace(s){if(!Number.isFinite(Number(s))||Number(s)<1)return '—';let v=Math.round(Number(s));return `${Math.floor(v/60)}:${String(v%60).padStart(2,'0')}`;}
function status(){const s=DATA?.sync||{};const hasPending=s.fits_pending>0;return `<div class="note">Last successful Garmin sync: <b>${esc(dateStamp(s.garmin_last_success))}</b> · ${count(DATA?.overview?.runs)} runs · ${count(s.fits_available)} detailed FIT recordings${hasPending?` · <b>${count(s.fits_pending)} detailed files still downloading</b>`:''}. ${s.historical_archive_complete===false?'Historical archive is not yet confirmed complete.':''} The website checks for new published data every 15 minutes.</div>`;}
function insights(){return (DATA?.insights||[]).map(x=>`<div class="signal"><h4>${esc(x.title)}</h4><p>${esc(x.body)}</p></div>`).join('')||'<div class="empty">More activities needed.</div>';}
function advice(){return (DATA?.upcoming_guidance||[]).map(x=>`<div class="signal"><h4>${esc(x.title)}</h4><p>${esc(x.text)}</p></div>`).join('')||'<div class="empty">No guidance yet.</div>';}
function showOverview(){const o=DATA?.overview||{},w=DATA?.weeks||[];
 return title('Performance overview','Your running progress, refreshed automatically from Garmin.') + status() + `<div class="hero"><div><div class="eyebrow">THE LONG GAME. IN FOCUS.</div><h2>Every kilometre tells a story.</h2><p>A public look at consistency, personal records and your training progression. No private activity routes or Garmin credentials are shared.</p></div><div class="hero-number">${count(o.runs)}<small>RUNS</small></div></div>` +
 `<div class="grid">${['5 km','10 km','Half marathon','Marathon'].map(t=>{let r=pb(t);return card(`${t} personal best`,r.time||'—',`${fmtDate(r.date)} · ${r.pace||'—'}`)}).join('')}</div>`+
 `<div class="columns">${box('Weekly running volume','Recorded kilometres per week',plotBars(w.slice(-16),'label','km'))}${box('Training snapshot','Rolling volume and consistency',`<div class="two-col">${[['Last 28 days',n(o.last_28_km)+' km'],['This week',n(o.this_week_km)+' km'],['This year',n(o.year_km)+' km'],['Active weeks / 12',String(o.active_weeks_12??'—')]].map(([a,b])=>`<div class="note"><div class="muted">${esc(a)}</div><div class="big">${esc(b)}</div></div>`).join('')}</div>`)}</div>`+
 `<div class="columns equal">${box('What the data says','Objective observations',insights())}${box('Focus for upcoming training','Evidence-based guidance, not a training prescription',advice())}</div>`;
}
function showRecords(){return title('Personal bests','Verified race results and fastest recorded Garmin efforts are distinguished where possible.')+status()+
 box('All tracked running distances','Detailed FIT records improve the accuracy of in-run personal bests',`<div class="table-wrap"><table><thead><tr><th>Distance</th><th>Best</th><th>Pace</th><th>Date</th><th>Source</th></tr></thead><tbody>${(DATA?.pbs||[]).map(r=>`<tr><td><strong>${esc(r.name)}</strong></td><td><strong>${esc(r.time)}</strong></td><td>${esc(r.pace)}</td><td>${esc(fmtDate(r.date))}</td><td>${esc(r.source)}</td></tr>`).join('')}</tbody></table></div><p class="tip">Runs without detailed FIT streams may not contain their fastest continuous efforts yet. Official event chip timing can differ from GPS estimates.</p>`) +
 `<div class="columns equal">${box('5 km best-effort progression','A lower completion time is better',plotLine(DATA?.pb_trend_5k||[],'date','seconds',true))}${box('Record coverage','How complete is the underlying analysis?',`<div class="big">${esc(DATA?.coverage?.percent ?? 0)}%</div><p class="tip">${count(DATA?.coverage?.detailed)} of ${count(DATA?.coverage?.activities)} running activities have detailed data. Coverage does not guarantee every GPS record is accurate.</p>`)}</div>`;
}
function showPhysiology(){let z=DATA?.zones||{}, t=DATA?.threshold||{};
if(!DATA?.physiology_shared)return title('Heart rate & lactate threshold','Your private physiological measurements are not published by default.')+box('Private measurements are protected','You can choose to publish HR metrics by setting the repository variable PUBLISH_PHYSIOLOGY to true.','<p class="note">The public view currently shares PBs and aggregated running volume only. Your Garmin account and private data remain outside the website.</p>');
if(!z.available)return title('Heart rate & lactate threshold','Your measurements, where Garmin makes them available.')+box('Reference not available','Garmin has not supplied a supported HR reference.', '<div class="empty">No valid LTHR or maximum HR reference detected.</div>');
return title('Heart rate & lactate threshold','Reference values and selected heart-rate zoning model, not laboratory measurements.')+`<div class="grid">${card('Lactate threshold HR',t.lthr?t.lthr+' bpm':'—',t.source||'Unavailable')}${card('Threshold pace',t.pace||'—',t.note||'')}${card('Easy running zone',z.easy?z.easy.join('–')+' bpm':'—',z.selected||'')}${card('Zone method',String(z.selected||'—').toUpperCase(),'Use RPE and context too')}</div>`+
 `<div class="columns equal">${box('Heart-rate zones','Calculated training ranges',`<div class="zone">${zoneColors.map(c=>`<span style="flex:1;background:${c}"></span>`).join('')}</div><div class="table-wrap"><table><thead><tr><th>Zone</th><th>Range</th><th>Purpose</th></tr></thead><tbody>${(z.zones||[]).map((v,i)=>`<tr><td><b style="color:${zoneColors[i]}">${esc(v.name)}</b></td><td>${esc(v.low)}–${esc(v.high)} bpm</td><td>${esc(v.purpose)}</td></tr>`).join('')}</tbody></table></div><p class="tip">${esc(z.method||'')}</p>`)}${box('Recorded time in zone','Only usable time-stamped HR samples are included',`<div class="pills">${(DATA.time_in_zone||[]).map((sec,i)=>`<span class="pill" style="background:${zoneColors[i]}28;color:${zoneColors[i]}">Z${i+1}: ${n(sec/3600,1)} h</span>`).join('')}</div><p class="tip">Training zones derived from LTHR alone do not establish individual LT1/VT1 accurately.</p>`)}</div>`;
}
function showTrends(){let weeks=DATA?.weeks||[],months=DATA?.months||[], longs=DATA?.long_runs||[];
return title('Training trends','Monitor your endurance foundation, consistency and development over time.')+status()+`<div class="grid">${card('Lifetime kilometres',n(DATA?.overview?.all_km)+' km','All imported runs')}${card('Current week',n(DATA?.overview?.this_week_km)+' km','Monday–Sunday')}${card('Last 28 days',n(DATA?.overview?.last_28_km)+' km','Rolling total')}${card('Average runs / week',n(DATA?.overview?.runs_week_average_12),'Last 12 weeks')}</div>`+`<div class="columns equal">${box('Weekly distance','Recent 20 weeks',plotBars(weeks,'label','km'))}${box('Longest run each week','Progression across recent weeks',plotBars(longs,'label','km'))}</div>`+`<div class="columns equal">${box('Monthly running distance','Recent 12 months',plotBars(months,'label','km'))}${box('Training consistency','You are building a useful history',`<div class="big">${count(DATA?.overview?.active_weeks_12)}<span class="muted"> / 12 weeks</span></div><p class="tip">Weeks with at least one recorded run. Use alongside total load, recovery and training intention.</p>`)}</div>`;
}
function showInsights(){const compare=DATA?.efficiency_comparison||{};
return title('Training insights','Interpret progress and decide what matters next. These are data-based observations, not medical advice.')+status()+
 `<div class="columns equal">${box('Patterns in your running','Based on imported Garmin activity records',insights())}${box('Guidance for upcoming training','Context matters: terrain, fatigue, recovery and race goals',advice())}</div>`+
 box('Pace at a similar heart rate','A useful trend but not a direct fitness measurement',compare.hr_band?`<p class="note">For runs in the ${esc(compare.hr_band[0])}–${esc(compare.hr_band[1])} bpm range, the most recent average pace is ${esc(pace(compare.recent_pace))}/km versus ${esc(pace(compare.early_pace))}/km in the earlier sample. ${esc(compare.caution||'')}</p>`:'<div class="empty">More comparable HR records are required.</div>')+
 (DATA?.race_projection?.time?box('Race-performance projection','Exploratory estimate, not a prediction',`<div class="big">${esc(DATA.race_projection.time)}</div><p class="tip">From ${esc(DATA.race_projection.source_distance)}. ${esc(DATA.race_projection.note)}</p>`):'');
}
const pages={overview:showOverview,records:showRecords,physiology:showPhysiology,trends:showTrends,insights:showInsights};
function render(){const names={overview:'Overview',records:'Personal bests',physiology:'Heart rate & LT',trends:'Training trends',insights:'Training insights'};$('#crumb').textContent=names[TAB]||'Overview';document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.tab===TAB));$('#main').innerHTML=DATA?pages[TAB]():`<div class="note">Waiting for Garmin data…</div>`;}
async function fetchData(){try{const response=await fetch('./data.json?reload='+Date.now(),{cache:'no-store'});if(!response.ok)throw new Error(`HTTP ${response.status}`);const payload=await response.json();if(payload.schema_version!==1||!payload.overview)throw new Error('Unexpected public statistics format');if(payload.sample)throw new Error('This is demo data, not your synced Garmin history');DATA=payload;render();}catch(e){if(!DATA)$('#main').innerHTML=`<div class="note">Unable to load running statistics. This is normal before the first successful GitHub Actions sync. <small>${esc(e.message)}</small></div>`;}}
document.querySelectorAll('#nav button').forEach(b=>b.addEventListener('click',()=>{TAB=b.dataset.tab;render();window.scrollTo({top:0,behavior:'smooth'});}));
fetchData();setInterval(fetchData,15*60*1000);
