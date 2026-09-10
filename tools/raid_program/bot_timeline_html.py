"""Self-contained HTML rendering for :mod:`bot_timeline`."""

from __future__ import annotations

import json
from typing import Any


def render_timeline_html(model: dict[str, Any]) -> str:
    def browser_safe(value: Any) -> Any:
        if isinstance(value, int) and not isinstance(value, bool) and abs(value) > 9_007_199_254_740_991:
            return str(value)
        if isinstance(value, dict):
            return {key: browser_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [browser_safe(item) for item in value]
        return value
    payload = json.dumps(browser_safe(model), separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Raid bot timeline</title><style>
:root{{--bg:#10151d;--panel:#18212c;--ink:#e8eef5;--muted:#93a4b7;--line:#314052;--accent:#65c4ff}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:14px system-ui,sans-serif}}
main{{max-width:1500px;margin:auto;padding:20px}} h1{{margin:0 0 6px}} .warning{{color:#ffd17a}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px;margin:12px 0}}
.filters{{display:flex;gap:10px;flex-wrap:wrap}} label{{color:var(--muted)}} select{{display:block;background:#0d131a;color:var(--ink);border:1px solid var(--line);padding:5px}}
.lane{{display:grid;grid-template-columns:180px 1fr;gap:10px;padding:7px 0;border-top:1px solid var(--line);cursor:pointer}}
.track{{position:relative;height:20px;background:#0d131a;border-radius:3px}} .mark{{position:absolute;top:4px;width:4px;height:12px;background:var(--accent)}}
.mark.landed{{background:#61d095}} .mark.native_submission{{background:#ffbb55}} .mark.idle_backoff{{background:#fa7272}}
table{{border-collapse:collapse;width:100%}} th,td{{padding:6px;text-align:left;border-bottom:1px solid var(--line)}} th{{position:sticky;top:0;background:var(--panel)}}
.scroll{{max-height:600px;overflow:auto}} code{{color:#b8dafa}} .muted{{color:var(--muted)}}
</style></head><body><main><h1>Raid bot timeline</h1><div id="identity" class="muted"></div><div id="warning" class="warning"></div>
<section class="card filters"><label>Actor<select id="actor"></select></label><label>Phase<select id="phase"></select></label><label>Target entry/GUID<select id="target"></select></label><label>Spell<select id="spell"></select></label><label>From pull (sec)<input id="from" type="number" step="0.1"></label><label>To (sec)<input id="to" type="number" step="0.1"></label></section>
<section class="card"><h2>Overview</h2><div id="lanes"></div></section>
<section class="card"><h2>Observed phase intervals</h2><div id="phaseWarning" class="warning"></div><div id="phases" class="scroll"></div></section>
<section class="card"><h2>Filtered events</h2><div><button id="prev">Previous</button> <button id="next">Next</button> <span id="count" class="muted"></span></div><div class="scroll"><table><thead><tr><th>Time</th><th>Actor</th><th>Kind</th><th>Phase</th><th>Target</th><th>Spell</th><th>Provenance</th><th>Detail</th></tr></thead><tbody id="events"></tbody></table></div></section>
<script id="model" type="application/json">{payload}</script><script>
const M=JSON.parse(document.getElementById('model').textContent), $=id=>document.getElementById(id), esc=x=>String(x??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c])); let page=0; const pageSize=500;
const actors=M.actors||{{}}, events=M.events||[], phaseIntervals=M.phase_intervals||[], w=M.window||{{}}, lo=w.first_hostile_at_ms||Math.min(...events.map(e=>e.at_ms),0), hi=w.native_boss_death_at_ms||Math.max(...events.map(e=>e.at_ms),lo+1), span=Math.max(1,hi-lo);
$('identity').textContent=[M.identity?.cohort_id,M.identity?.server_epoch,M.identity?.attempt_id].filter(x=>x!=null).join(' / ');
$('warning').textContent=[M.completeness?.legacy_historical_metadata_warning,(M.completeness?.missing_observations||[]).length?'Missing: '+M.completeness.missing_observations.join(', '):''].filter(Boolean).join(' · ');
function options(id,values){{const s=$(id);s.innerHTML='<option value="">All</option>'+[...new Set(values.filter(x=>x!==undefined&&x!==null&&x!==''))].sort().map(x=>`<option>${{esc(x)}}</option>`).join('')}}
$('actor').innerHTML='<option value="">All</option>'+Object.entries(actors).map(([g,v])=>`<option value="${{esc(g)}}">${{esc(v.name||'Unknown')}} · ${{esc(g)}}</option>`).join(''); options('phase',[...events.map(e=>e.phase),...phaseIntervals.map(e=>e.phase)]);
const targetOptions=new Map();events.forEach(e=>{{if(e.target_entry)targetOptions.set('e:'+e.target_entry,'entry '+e.target_entry);if(e.target_guid)targetOptions.set('g:'+e.target_guid,'GUID '+e.target_guid)}});$('target').innerHTML='<option value="">All</option>'+[...targetOptions].map(([v,l])=>`<option value="${{esc(v)}}">${{esc(l)}}</option>`).join('');options('spell',events.map(e=>e.spell_id));$('from').value='0';$('to').value=(span/1000).toFixed(3);
function render(){{const a=$('actor').value,p=$('phase').value,t=$('target').value,s=$('spell').value,from=lo+Number($('from').value||0)*1000,to=lo+Number($('to').value||span/1000)*1000;const targetMatch=e=>!t||(t[0]==='e'&&String(e.target_entry)===t.slice(2))||(t[0]==='g'&&String(e.target_guid)===t.slice(2));const visible=events.filter(e=>e.at_ms>=from&&e.at_ms<=to&&(!a||String(e.actor_guid)===a)&&(!p||String(e.phase)===p)&&targetMatch(e)&&(!s||String(e.spell_id)===s)); const pages=Math.max(1,Math.ceil(visible.length/pageSize));page=Math.min(page,pages-1);
const marks=guid=>{{const bins=new Map(),shownSpan=Math.max(1,to-from);visible.filter(e=>String(e.actor_guid)===guid).forEach(e=>{{const bin=Math.max(0,Math.min(799,Math.floor((e.at_ms-from)*800/shownSpan)));if(!bins.has(bin)||e.kind==='landed')bins.set(bin,e)}});return [...bins.entries()].map(([bin,e])=>`<i title="${{esc(e.kind)}}" class="mark ${{esc(e.kind)}}" style="left:${{bin*100/800}}%"></i>`).join('')}};
$('lanes').innerHTML=Object.entries(actors).filter(([g])=>!a||g===a).map(([g,v])=>`<div class="lane" data-guid="${{esc(g)}}"><div>${{esc(v.name||g)}} · ${{esc(g)}}<br><span class="muted">${{esc(v.role||'role unknown')}} · ${{Math.round(v.damage?.hostile_originated||0).toLocaleString()}} damage · ${{v.damage?.dps==null?'DPS unknown':Math.round(v.damage.dps).toLocaleString()+' DPS'}} · ${{Math.round(v.effective_healing||0).toLocaleString()}} healing · ${{v.effective_hps==null?'HPS unknown':Math.round(v.effective_hps).toLocaleString()+' HPS'}} · ${{v.activity?.active_seconds??'?'}} active sec</span></div><div class="track">${{marks(g)}}</div></div>`).join('')||'<span class="muted">No actor events available.</span>';
document.querySelectorAll('.lane').forEach(x=>x.onclick=()=>{{$('actor').value=x.dataset.guid;render()}});
$('phaseWarning').textContent=phaseIntervals.some(x=>x.conflict)?'Conflicting attributable phase observations are present.':'';
$('phases').innerHTML=phaseIntervals.filter(x=>(!a||String(x.actor_guid)===a)&&(!p||String(x.phase)===p)).map(x=>`<details><summary>${{esc(actors[x.actor_guid]?.name||x.actor_guid)}} · ${{esc(x.phase)}} · ${{((x.start_ms-lo)/1000).toFixed(3)}}s..${{((x.end_ms-lo)/1000).toFixed(3)}}s${{x.conflict?' · CONFLICT':''}}</summary><pre>${{esc(JSON.stringify(x,null,2))}}</pre></details>`).join('')||'<span class="muted">No attributable phase observations.</span>';
$('count').textContent=`${{visible.length}} matches · page ${{page+1}}/${{pages}}`;$('prev').disabled=page===0;$('next').disabled=page>=pages-1;
$('events').innerHTML=visible.slice(page*pageSize,(page+1)*pageSize).map(e=>`<tr><td>${{((e.at_ms-lo)/1000).toFixed(3)}}s</td><td>${{esc(actors[e.actor_guid]?.name||e.actor_guid)}}</td><td>${{esc(e.kind)}}</td><td>${{esc(e.phase)}}</td><td>${{esc(e.target_entry||e.target_guid)}}</td><td>${{esc(e.spell_name||e.spell_id)}}</td><td>${{esc(e.provenance)}}${{e.stale_relative_to_export?' · stale at export':''}}</td><td><details><summary>full event</summary><pre>${{esc(JSON.stringify(e,null,2))}}</pre></details></td></tr>`).join('');}}
document.querySelectorAll('select,input').forEach(x=>x.onchange=()=>{{page=0;render()}});$('prev').onclick=()=>{{page--;render()}};$('next').onclick=()=>{{page++;render()}};render();
</script></main></body></html>"""
