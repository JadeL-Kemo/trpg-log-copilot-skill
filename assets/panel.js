// === Panel Renderer v1.8 — API first, embedded DATA as offline fallback ===
(function(){
  function boot(D) { try { init(D); } catch(e) { bootFallback(e); } }
  function bootFallback(err) {
    var d = document.getElementById('dash');
    if (d && window.DATA) { try { init(window.DATA); return; } catch(e2) { if (d) d.textContent = 'Render error'; } }
    if (d) d.textContent = 'Data unavailable — start serve.py and refresh';
  }
  fetch('api/data').then(function(r){ return r.json(); }).then(boot).catch(function(){
    if (window.DATA) boot(window.DATA);
    else document.getElementById('dash').textContent = 'No data — run import_md.py or start serve.py';
  });
})();

function init(DATA) {
  if (!DATA || !DATA.clues) { var d = document.getElementById('dash'); if (d) d.textContent = 'No data'; return; }
  window.DATA = DATA;
  try { renderAll(); } catch(e) { var d = document.getElementById('dash'); if (d) d.textContent = 'Render error: ' + (e.message || e); }
}

function renderAll() {
  var DATA = window.DATA;

  // --- Render dash ---
var pc = DATA.chars.filter(function(c){return c.type==='pc'});
var dp = [];
for (var i=0;i<pc.length;i++){
  var ch=pc[i], parts=[ch.name];
  for(var k in ch.pools){var p=ch.pools[k]; parts.push(k.substr(0,4).toUpperCase()+' '+p.cur+'/'+p.max)}
  if(ch.loc!=='-') parts.push(ch.loc);
  if(ch.status!=='-') parts.push('['+ch.status+']');
  dp.push(parts.join(' · '))
}
document.getElementById('dash').textContent = dp.join('  |  ')||'No PC data';

// --- Render nav ---
var tabs = [
  {id:'clues',label:'线索'},{id:'npcs',label:'人物'},
  {id:'tl',label:'时间线'},{id:'chars',label:'角色'},{id:'todos',label:'待办'}
];
var nav = document.querySelector('nav');
nav.innerHTML = tabs.map(function(t,i){return '<button class="'+(i===0?'active':'')+'" data-panel="'+t.id+'">'+t.label+'</button>'}).join('');
nav.querySelectorAll('button').forEach(function(btn){ btn.addEventListener('click',function(){ S(this,this.dataset.panel); }); });

// --- Render ts ---
document.getElementById('ts').textContent = '更新于 '+new Date().toLocaleString('zh-CN')+' · v1.8';

// Tab switching
function S(btn, id) {
  var ps = document.querySelectorAll('.panel');
  for (var i = 0; i < ps.length; i++) ps[i].classList.remove('active');
  var bs = document.querySelectorAll('nav button');
  for (var i = 0; i < bs.length; i++) bs[i].classList.remove('active');
  var el = document.getElementById(id);
  if (el) el.classList.add('active');
  btn.classList.add('active');
  location.hash = '#' + id;
}
window.S = S;

// Refresh
function R() { fetch('api/data').then(function(r){return r.json()}).then(function(d){window.DATA=d;renderAll()}).catch(function(){location.reload()}); }
// Hash-based tab persistence
(function(){
  var hash = location.hash.replace('#','');
  if (hash && document.getElementById(hash)) {
    var btns = document.querySelectorAll('nav button');
    for (var i=0;i<btns.length;i++) {
      if (btns[i].textContent === ({clues:'clues',npcs:'npcs',tl:'tl',chars:'chars',todos:'todos'})[hash] || btns[i].onclick.toString().indexOf("S(this,'"+hash+"')")>=0) {
        S(btns[i], hash); break;
      }
    }
  }
})();

// Pull-to-refresh
(function() {
  var pEl = document.getElementById('pull'), SR = 0, pY = 0;
  if (!pEl) return;

  document.addEventListener('touchstart', function(e) {
    if (window.scrollY === 0) { SR = 1; pY = e.touches[0].clientY; }
  }, {passive: true});

  document.addEventListener('touchmove', function(e) {
    if (SR !== 1 || window.scrollY !== 0 || !pEl) return;
    var d = e.touches[0].clientY - pY;
    if (d > 0) {
      e.preventDefault();
      pEl.style.transform = 'translateY(' + Math.min(d, 64) + 'px)';
      pEl.textContent = d > 56 ? '释放刷新' : '下拉刷新';
    } else {
      SR = 0; pEl.style.transform = ''; pEl.textContent = '';
    }
  }, {passive: false});

  document.addEventListener('touchend', function(e) {
    if (SR !== 1) { SR = 0; return; }
    var d = e.changedTouches[0].clientY - pY;
    if (d > 56 && window.scrollY === 0) {
      pEl.textContent = '刷新中'; pEl.className = 'spin'; R();
    } else {
      pEl.style.transition = 'transform .2s'; pEl.style.transform = '';
      pEl.textContent = '';
      setTimeout(function() { pEl.style.transition = ''; }, 200);
    }
    SR = 0;
  });
})();

// Double-click dash to refresh
var dsh = document.getElementById('dash');
if (dsh) {
  dsh.addEventListener('click', function(e) { if (e.detail === 2) R(); });
  dsh.style.cursor = 'pointer';
  dsh.title = '双击刷新';
}

// === Data rendering ===
// (moved inside renderAll() called by init())

function vl(k) { return (window.DATA&&window.DATA.labels.verified[k]) || k; }
function cl(k) { return (window.DATA&&window.DATA.labels.confidence[k]) || k; }
function escAttr(s) { return (s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function renderContent(text) {
  if (!text) return '';
  // Strip Markdown bold/italic
  text = text.replace(/\*\*([^*]+)\*\*/g, '$1').replace(/\*([^*]+)\*/g, '$1');
  var m = text.match(/^img:(\S+\.(jpg|png|gif|webp|bmp|svg))\s*/i);
  if (!m) return text;
  var imgHtml = '<img src="images/' + m[1] + '" style="max-width:100%;max-height:160px;border-radius:4px;border:1px solid #2a3a5c;display:block;margin-bottom:4px" onerror="this.style.display=\'none\'" loading="lazy">';
  return imgHtml + text.replace(/^img:\S+\s*/, '');
}

// Clue cards — compact: ID + badges on top, content truncated below
try {
var ct = document.getElementById('ct');
if (ct && DATA.clues) {
  var h = '';
  for (var i = 0; i < DATA.clues.length; i++) {
    var c = DATA.clues[i];
    var cf = c.confidence || 'medium';
    var ctText = (c.content||'').replace(/^img:\S+\s*/,'');
    h += '<div class="wiki-card" onclick="openRelated(\'' + c.id + '\')">' +
      '<div style="margin-bottom:2px">' + c.id + ' <span class="v-confirmed" style="font-size:10px;margin-right:4px">已证实</span><span class="c-' + cf + '">' + cl(cf) + '</span></div>' +
      '<div class="wiki-body">' + ctText + '</div>' +
      '</div>';
  }
  ct.innerHTML = h;
}
} catch(e) { if (ct) ct.innerHTML = '<div style="color:#e94560">Clue render error</div>'; }

// NPC cards
var nt = document.getElementById('nt');
if (nt && DATA.npcs) {
  var h = '';
  for (var i = 0; i < DATA.npcs.length; i++) {
    var n = DATA.npcs[i];
    var facts = JSON.parse(n.key_facts || '[]');
    h += '<div class="wiki-card" onclick="openNpc(\'' + escAttr(n.id) + '\')">' +
      '<div style="margin-bottom:2px"><b>' + n.name + '</b> <span style="font-size:10px;color:#888">' + n.role + '</span></div>' +
      '<div class="wiki-body">' + (facts.join('; ') || n.stance) + '</div>' +
      '</div>';
  }
  nt.innerHTML = h;
}

// Chronicle timeline — special rendering
var chDiv = document.getElementById('chr');
if (chDiv && DATA.chronicles && DATA.chronicles.length) {
  var h = '';
  for (var i = 0; i < DATA.chronicles.length; i++) {
    var c = DATA.chronicles[i];
    var nps = JSON.parse(c.participants || '[]');
    var cls = JSON.parse(c.related_clues || '[]');
    var npTags = nps.map(function(n){return '<span class="tag-npc">'+n+'</span>';}).join(' ');
    var clTags = cls.map(function(id){return '<span class="drill-chip link" onclick="event.stopPropagation();openRelated(\''+id+'\')">'+id+'</span>';}).join('');
    h += '<div class="chr-item"><div class="chr-dot"></div><div class="chr-card wiki-card" onclick="openChronicle(\''+i+'\')"><div class="chr-date">'+c.event_date+'</div><div class="chr-title wiki-body">'+c.event+'</div></div></div>';
  }
  chDiv.innerHTML = h;
}

// Timeline cards
var tt = document.getElementById('tt');
if (tt && DATA.events) {
  var h = '';
  for (var i = 0; i < DATA.events.length; i++) {
    var e = DATA.events[i];
    var parts = JSON.parse(e.participants || '[]');
    var refs = JSON.parse(e.related_clues || '[]');
    var refText = refs.length ? ' · ' + refs.join(' ') : '';
    h += '<div class="wiki-card" onclick="openTimeline(' + i + ')">' +
      '<div style="margin-bottom:2px"><b>' + e.event_time + '</b></div>' +
      '<div class="wiki-body">' + e.event + refText + '</div>' +
      '</div>';
  }
  tt.innerHTML = h;
}
function openTimeline(idx) {
  var e = DATA.events[idx];
  if (!e) return;
  var parts = JSON.parse(e.participants || '[]');
  var refs = JSON.parse(e.related_clues || '[]');
  var sid = e.scene_id || '';
  var h = '<div style="padding:4px">';
  
  // Section 1: Detail
  h += '<div style="margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #2a3a5c">';
  h += '<div style="margin-bottom:4px"><b>' + e.event_time + '</b> ' + e.event + '</div>';
  if (e.created_at) h += '<div style="font-size:9px;color:#555;margin-bottom:4px">记录: ' + e.created_at + '</div>';
  if (e.notes) h += '<div style="font-size:12px;color:#ccc;line-height:1.6;margin-bottom:4px">' + e.notes + '</div>';
  h += '</div>';
  // Section 2: Scene log — always shown, text updated async
  h += '<div style="margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #1a2a30">';
  h += '<div style="font-size:11px;color:#888;margin-bottom:4px">详细日志</div>';
  h += '<div id="log'+idx+'" style="font-size:10px;color:#555">加载中...</div>';
  h += '</div>';
  
  // Section 3: Participants
  if (parts.length) {
    h += '<div style="margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #1a2a30">';
    h += '<div style="font-size:11px;color:#888;margin-bottom:4px">参与者 (' + parts.length + ')</div>';
    for (var i = 0; i < parts.length; i++) {
      h += '<span class="drill-chip npc" onclick="event.stopPropagation();openNpc(\'' + escAttr(parts[i]) + '\')">' + parts[i] + '</span>';
    }
    h += '</div>';
  }
  
  // Section 4: Related clues
  if (refs.length) {
    h += '<div style="margin-bottom:4px"><div style="font-size:11px;color:#888;margin-bottom:4px">关联线索 (' + refs.length + ')</div>';
    for (var i = 0; i < refs.length; i++) {
      var rc = findClue(refs[i]);
      if (!rc) continue;
      var rcf = rc.confidence || 'medium';
      h += '<div class="wiki-card" onclick="event.stopPropagation();openRelated(\'' + rc.id + '\')">' +
        '<div style="margin-bottom:2px">' + rc.id + ' <span class="v-confirmed" style="font-size:10px;margin-right:3px">已证实</span><span class="c-' + rcf + '">' + cl(rcf) + '</span></div>' +
        '<div class="wiki-body">' + rc.content + '</div></div>';
    }
    h += '</div>';
  }
  h += '</div>';
  drill([{html: h}], e.event_time);
  
  // Fetch scene log — always try, FTS5 content fallback
  (function(sid, idx, evDesc){setTimeout(function(){
    var p = document.getElementById('log'+idx);
    var done = false;
    // Timeout: if fetch hangs (no server), show after 3s
    setTimeout(function(){if(!done&&p){p.style.cssText='font-size:10px;color:#555';p.textContent='加载失败';}}, 3000);
    fetch('/api/scene?id=' + encodeURIComponent(sid) + '&q=' + encodeURIComponent(evDesc)).then(function(r){return r.text()}).then(function(tx){
      done = true;
      if (!p) return;
      tx = tx.replace(/<!--\s*scene:.*?-->/g, '').replace(/###\s*[^\n]+\n?/g, '').trim();
      if (tx && tx.indexOf('not found') < 0) {
        p.style.cssText = 'margin:0;padding:8px;background:#111827;border-radius:4px;font-size:11px;color:#aaa;line-height:1.5;white-space:pre-wrap;max-height:200px;overflow-y:auto';
        p.textContent = tx;
      } else {
        p.style.cssText = 'font-size:10px;color:#555';
        p.textContent = '（此场景无实际日志正文）';
      }
    }).catch(function(){done=true;if(p)p.textContent='加载失败';});
  }, 50);})(sid, idx, e.event);
}
window.openTimeline = openTimeline;

// Character cards
var cc = document.getElementById('cc');
if (cc && DATA.chars) {
  var h = '';
  for (var i = 0; i < DATA.chars.length; i++) {
    var c = DATA.chars[i];
    var t = c.type === 'pc' ? 'PC' : 'NPC';
    var pools = [];
    var keys = Object.keys(c.pools);
    for (var j = 0; j < keys.length; j++) {
      var k = keys[j], v = c.pools[k];
      pools.push(k + ' ' + v.cur + '/' + v.max);
    }
    h += '<div class="wiki-card" onclick="openChar(' + i + ')">' +
      '<div style="margin-bottom:2px"><b>' + c.name + '</b> <span class="tag-' + (c.type === 'pc' ? 'pc' : 'npc') + '">' + t + '</span></div>' +
      '<div class="wiki-body">' + pools.join(' · ') + '</div>' +
      '</div>';
  }
  cc.innerHTML = h;
}
function openChar(idx) {
  var c = DATA.chars[idx];
  if (!c) return;
  var h = '<div style="padding:4px"><div style="margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #2a3a5c">';
  h += '<div style="margin-bottom:4px"><b>' + c.name + '</b></div>';
  var keys = Object.keys(c.pools);
  for (var j = 0; j < keys.length; j++) {
    var k = keys[j], v = c.pools[k];
    h += '<div style="font-size:12px;margin:2px 0">' + k + ': <b>' + v.cur + '</b>/' + v.max + '</div>';
  }
  h += '<div style="font-size:11px;color:#888;margin-top:4px">位置: ' + c.loc + ' | 状态: ' + c.status + '</div>';
  h += '</div></div>';
  drill([{html: h}], c.name);
}
window.openChar = openChar;

// Todos — wiki-card style
var tl = document.getElementById('tlst');
if (tl && DATA.todos) {
  var h = '';
  for (var i = 0; i < DATA.todos.length; i++) {
    var t = DATA.todos[i];
    var reasonEsc = (t.reason || '').replace(/'/g, "\\'");
    h += '<div class="wiki-card" onclick="openTodo(' + i + ",'" + reasonEsc + "'" + ')">' +
      '<div class="wiki-body">' + t.priority + ' ' + t.task + '</div>' +
      '</div>';
  }
  tl.innerHTML = h;
}

} // end renderAll()

// === Drill-down popup ===
var drillStack = [];
function drill(items, title) {
  drillStack.push({items: items, title: title});
  renderDrill();
}
function drillBack() {
  if (drillStack.length > 1) { drillStack.pop(); renderDrill(); }
  else closeDrill();
}
function closeDrill() {
  drillStack = [];
  document.getElementById('drill').classList.remove('open');
}
window.closeDrill = closeDrill;
window.drillBack = drillBack;
function renderDrill() {
  if (!drillStack.length) return;
  var cur = drillStack[drillStack.length - 1];
  var d = document.getElementById('drill');
  var b = document.getElementById('drillBody');
  var t = document.getElementById('drillTitle');
  t.innerHTML = (drillStack.length > 1 ? '<span style="cursor:pointer;margin-right:8px" onclick="event.stopPropagation();drillBack()">←</span>' : '') + cur.title;
  var h = '';
  for (var i = 0; i < cur.items.length; i++) {
    h += buildItem(cur.items[i]);
  }
  b.innerHTML = h || '<div style="color:#666;padding:20px;text-align:center">无关联项</div>';
  d.classList.add('open');
}

function findClue(id) {
  for (var i = 0; i < DATA.clues.length; i++) {
    if (DATA.clues[i].id === id) return DATA.clues[i];
  }
  return null;
}
function openChronicle(idx) {
  var c = DATA.chronicles[idx];
  if (!c) return;
  var nps = JSON.parse(c.participants || '[]');
  var cls = JSON.parse(c.related_clues || '[]');
  var h = '<div style="padding:4px">';
  
  // Section 1: Chronicle detail
  h += '<div style="margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #2a3a5c">';
  h += '<div style="margin-bottom:4px"><b>' + c.event_date + '</b> ' + c.event + '</div>';
  if (c.notes) h += '<div style="font-size:12px;color:#ccc;line-height:1.6">' + c.notes + '</div>';
  h += '</div>';
  
  // Section 2: Related NPCs
  if (nps.length) {
    h += '<div style="margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #1a2a30">';
    h += '<div style="font-size:11px;color:#888;margin-bottom:4px">关联人物 (' + nps.length + ')</div>';
    for (var i = 0; i < nps.length; i++) {
      h += '<span class="drill-chip npc" onclick="event.stopPropagation();openNpc(\'' + escAttr(nps[i]) + '\')">' + nps[i] + '</span>';
    }
    h += '</div>';
  }
  
  // Section 3: Related clues
  if (cls.length) {
    h += '<div style="margin-bottom:4px"><div style="font-size:11px;color:#888;margin-bottom:4px">关联线索 (' + cls.length + ')</div>';
    for (var i = 0; i < cls.length; i++) {
      var rc = findClue(cls[i]);
      if (!rc) continue;
      var rcf = rc.confidence || 'medium';
      h += '<div class="wiki-card" onclick="event.stopPropagation();openRelated(\'' + rc.id + '\')">' +
        '<div style="margin-bottom:2px">' + rc.id + ' <span class="v-confirmed" style="font-size:10px;margin-right:3px">已证实</span><span class="c-' + rcf + '">' + cl(rcf) + '</span></div>' +
        '<div class="wiki-body">' + rc.content + '</div></div>';
    }
    h += '</div>';
  }
  h += '</div>';
  drill([{html: h}], c.event);
}
window.openChronicle = openChronicle;
function refsTo(id) {
  // Find ALL clues that link TO this id (reverse index)
  var r = [];
  for (var i = 0; i < DATA.clues.length; i++) {
    var linked = [];
    try { linked = JSON.parse(DATA.clues[i].linked_ids || '[]'); } catch(e) {}
    if (linked.indexOf(id) >= 0) r.push(DATA.clues[i]);
  }
  return r;
}
function buildItem(it) {
  if (it.html) return it.html;
  var linkIds = [];
  try { linkIds = JSON.parse(it.linked_ids || '[]'); } catch(e) {}
  var backRefs = refsTo(it.id);
  var relatedNpcs = [];
  for (var j = 0; j < DATA.npcs.length; j++) {
    var np = DATA.npcs[j];
    if (it.source === np.name || (it.content && it.content.indexOf(np.name) >= 0))
      if (relatedNpcs.indexOf(np.name) < 0) relatedNpcs.push(np.name);
  }
  var uid = 'd' + Math.random().toString(36).slice(2,8);
  // Surface: ID + confidence + content (compact, matching clue table)
  var h = '<div class="drill-item" onclick="event.stopPropagation();openRelated(\'' + it.id + '\')">';
  h += '<div style="margin-bottom:3px">' + it.id + ' <span class="c-' + (it.confidence || 'medium') + '">' + cl(it.confidence || 'medium') + '</span></div>';
  h += '<div>' + it.content + '</div>';
  // Detail toggle
  h += '<div style="margin-top:4px"><span onclick="event.stopPropagation();var e=document.getElementById(\''+uid+'\');e.style.display=e.style.display==\'none\'?\'block\':\'none\';this.textContent=e.style.display==\'block\'?\'▾ 收起\':\'▸ 详情\'" style="cursor:pointer;color:#888;font-size:10px">▸ 详情</span></div>';
  h += '<div id="' + uid + '" style="display:none;margin-top:4px;padding-top:4px;border-top:1px solid #2a3a5c">';
  h += '<div style="font-size:11px;color:#888">来源: ' + it.source + '</div>';
  if (linkIds.length) {
    h += '<div style="font-size:11px;margin-top:4px"><span style="color:#6ab;font-size:10px">关联线索 </span>' + linkIds.map(function(id){return '<span class="drill-chip link" onclick="event.stopPropagation();openRelated(\''+id+'\')">'+id+'</span>';}).join('') + '</div>';
  }
  if (backRefs.length) {
    var brIds = backRefs.map(function(b){return b.id;});
    h += '<div style="font-size:11px;margin-top:4px"><span style="color:#ff9800;font-size:10px">被引用 </span>' + brIds.map(function(id){return '<span class="drill-chip ref" onclick="event.stopPropagation();openRelated(\''+id+'\')">'+id+'</span>';}).join('') + '</div>';
  }
  if (relatedNpcs.length) {
    h += '<div style="font-size:11px;margin-top:4px"><span style="color:#e94560;font-size:10px">相关人物 </span>' + relatedNpcs.map(function(n){return '<span class="drill-chip npc" onclick="event.stopPropagation();openNpc(\''+escAttr(n)+'\')">'+n+'</span>';}).join('') + '</div>';
  }
  h += '</div></div>';
  return h;
}
function openNpc(name) {
  // Decode HTML entities in case onClick encoded them
  name = name.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>');
  var npc = null;
  // Search by ID first, then exact name, then loose match
  var allChars = (DATA.npcs||[]).concat((DATA.chars||[]).filter(function(c){return c.type==='pc';}).map(function(c){
    return {id:c.name,name:c.name,role:c.type==='pc'?'PC':'',stance:'',faction:'',key_facts:'[]',relationships:'[]'};
  }));
  var npc = null;
  // 1. ID match
  for (var i = 0; i < allChars.length; i++) {
    if (allChars[i].id === name) { npc = allChars[i]; break; }
  }
  // 2. Exact name match
  if (!npc) for (var i = 0; i < allChars.length; i++) {
    if (allChars[i].name === name) { npc = allChars[i]; break; }
  }
  // 3. Loose: strip parenthetical suffixes from both sides
  if (!npc) {
    var clean = name.replace(/\(.*?\)/g,'').trim();
    for (var i = 0; i < allChars.length; i++) {
      if (allChars[i].name.replace(/\(.*?\)/g,'').trim() === clean) { npc = allChars[i]; break; }
    }
  }
  // 4. Substring fallback
  if (!npc) for (var i = 0; i < allChars.length; i++) {
    if (allChars[i].name.indexOf(name) >= 0) { npc = allChars[i]; break; }
  }
  if (!npc) return;
  var facts = JSON.parse(npc.key_facts || '[]');
  var h = '<div style="padding:4px">';
  
  // Section 1: NPC detail
  h += '<div style="margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #2a3a5c">';
  h += '<div style="margin-bottom:4px"><b>' + npc.name + '</b> <span style="font-size:11px;color:#888">' + npc.role + '</span></div>';
  h += '<div style="font-size:11px;color:#888">势力: ' + (npc.faction || '-') + ' | 立场: ' + (npc.stance || '-') + '</div>';
  if (facts.length) h += '<div style="font-size:11px;color:#aaa;margin-top:3px">' + facts.join('; ') + '</div>';
  h += '</div>';
  
  // Section 2: Relations (from edge table)
  var outEdges = [];  // 我→别人
  var inEdges = [];   // 别人→我
  for (var i = 0; i < (DATA.relations || []).length; i++) {
    var r = DATA.relations[i];
    if (r.npc_a === name) outEdges.push(r);
    if (r.npc_b === name) inEdges.push(r);
  }
  // Deduplicate mutual: if both sides exist with same partner
  var seen = {};
  var mutualEdges = [];  // ↔ bidirectional
  var singleOut = [];    // 我→对方 (only I list them)
  var singleIn = [];     // 对方→我 (only they list me)
  for (var i = 0; i < outEdges.length; i++) {
    var key = outEdges[i].npc_a + '|' + outEdges[i].npc_b;
    seen[key] = outEdges[i];
  }
  for (var i = 0; i < inEdges.length; i++) {
    var rk = inEdges[i].npc_a + '|' + inEdges[i].npc_b;
    if (seen[rk]) {
      mutualEdges.push(seen[rk]);
      delete seen[rk];
    } else {
      singleIn.push(inEdges[i]);
    }
  }
  for (var k in seen) singleOut.push(seen[k]);
  
  var totalRels = mutualEdges.length + singleOut.length + singleIn.length;
  if (totalRels) {
    h += '<div style="margin-top:4px;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #1a2a30">';
    h += '<div style="font-size:11px;color:#888;margin-bottom:4px">关系 (' + totalRels + ')</div>';
    // Mutual (↔)
    for (var i = 0; i < mutualEdges.length; i++) {
      var r = mutualEdges[i];
      h += '<span class="drill-chip npc" onclick="event.stopPropagation();openNpc(\'' + escAttr(r.npc_b) + '\')">' + r.npc_b + ' (' + r.rel_type + ') ↔</span>';
    }
    // Outgoing (→)
    for (var i = 0; i < singleOut.length; i++) {
      var r = singleOut[i];
      h += '<span class="drill-chip npc" onclick="event.stopPropagation();openNpc(\'' + escAttr(r.npc_b) + '\')">' + r.npc_b + ' (' + r.rel_type + ') →</span>';
    }
    // Incoming (←)
    for (var i = 0; i < singleIn.length; i++) {
      var r = singleIn[i];
      h += '<span class="drill-chip npc" onclick="event.stopPropagation();openNpc(\'' + escAttr(r.npc_a) + '\')">' + r.npc_a + ' (' + r.rel_type + ') ←</span>';
    }
    h += '</div>';
  }
  
  // Section 3: Related clues as cards
  var npcClues = [];
  for (var i = 0; i < DATA.clues.length; i++) {
    var c = DATA.clues[i];
    if (c.source === npc.name || (c.content && c.content.indexOf(npc.name) >= 0)) npcClues.push(c);
  }
  if (npcClues.length) {
    h += '<div style="margin-bottom:4px"><div style="font-size:11px;color:#888;margin-bottom:4px">关联线索 (' + npcClues.length + ')</div>';
    for (var i = 0; i < npcClues.length; i++) {
      var nc = npcClues[i], ncf = nc.confidence || 'medium';
      h += '<div class="wiki-card" onclick="event.stopPropagation();openRelated(\'' + nc.id + '\')">' +
        '<div style="margin-bottom:2px">' + nc.id + ' <span class="v-confirmed" style="font-size:10px;margin-right:3px">已证实</span><span class="c-' + ncf + '">' + cl(ncf) + '</span></div>' +
        '<div class="wiki-body">' + nc.content + '</div></div>';
    }
    h += '</div>';
  }
  h += '</div>';
  drill([{html: h}], npc.name);
}
window.openNpc = openNpc;

function openTodo(idx, reason) {
  var t = DATA.todos[idx];
  if (!t) return;
  var refs = t.ref_ids || [];
  var h = '<div style="padding:4px">';
  
  // Section 1: Task detail
  h += '<div style="margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #2a3a5c">';
  h += '<div style="margin-bottom:4px">' + t.priority + ' <b>' + t.task + '</b></div>';
  if (reason) h += '<div style="font-size:12px;color:#aaa;line-height:1.6">' + reason + '</div>';
  h += '</div>';
  
  // Section 2: Related clues as cards
  var related = [];
  for (var i = 0; i < refs.length; i++) {
    var rc = findClue(refs[i]);
    if (rc) related.push(rc);
  }
  if (related.length) {
    h += '<div style="margin-bottom:4px"><div style="font-size:11px;color:#888;margin-bottom:4px">关联线索 (' + related.length + ')</div>';
    for (var i = 0; i < related.length; i++) {
      var rc = related[i], rcf = rc.confidence || 'medium';
      h += '<div class="wiki-card" onclick="event.stopPropagation();openRelated(\'' + rc.id + '\')">' +
        '<div style="margin-bottom:2px">' + rc.id + ' <span class="v-confirmed" style="font-size:10px;margin-right:3px">已证实</span><span class="c-' + rcf + '">' + cl(rcf) + '</span></div>' +
        '<div class="wiki-body">' + rc.content + '</div></div>';
    }
    h += '</div>';
  } else {
    h += '<div style="font-size:12px;color:#555">关联线索: ' + (refs.length ? '无（引用线索尚未证实）' : '无') + '</div>';
  }
  h += '</div>';
  drill([{html: h}], t.task.substring(0, 20));
}
window.openTodo = openTodo;

function currentDrillId() {
  if (!drillStack.length) return null;
  var cur = drillStack[drillStack.length - 1];
  return cur.items.length === 1 ? cur.items[0].id : null;
}
function openClue(id) {
  if (currentDrillId() === id) return;  // no self-drill
  var clue = findClue(id);
  if (!clue) return;
  drill([clue], id);
}
function allRelated(id) {
  // Union of linked + refsTo, deduplicated, excluding self
  var seen = {}, result = [];
  var clue = findClue(id);
  var linkIds = [];
  if (clue) try { linkIds = JSON.parse(clue.linked_ids || '[]'); } catch(e) {}
  var backRefs = refsTo(id);
  var allIds = linkIds.concat(backRefs.map(function(b){return b.id;}));
  for (var i = 0; i < allIds.length; i++) {
    var rid = allIds[i];
    if (rid === id || seen[rid]) continue;
    seen[rid] = true;
    var lc = findClue(rid);
    if (lc) result.push(lc);
  }
  return result;
}
function openRelated(id) {
  var clue = findClue(id);
  if (!clue) return;
  var linkIds = []; try { linkIds = JSON.parse(clue.linked_ids || '[]'); } catch(e) {}
  var backRefs = refsTo(id);
  var allRelatedIds = [];
  for (var i = 0; i < linkIds.length; i++) allRelatedIds.push(linkIds[i]);
  for (var i = 0; i < backRefs.length; i++) if (allRelatedIds.indexOf(backRefs[i].id) < 0) allRelatedIds.push(backRefs[i].id);

  var cf = clue.confidence || 'medium';
  var h = '<div style="padding:4px">';
  
  // Section 1: Header + detail
  h += '<div style="margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #2a3a5c">';
  h += '<div style="margin-bottom:4px"><b>' + clue.id + '</b> <span class="v-confirmed" style="font-size:10px;margin-right:3px">已证实</span><span class="c-' + cf + '">' + cl(cf) + '</span></div>';
  h += '<div style="font-size:12px;color:#ccc;line-height:1.6;margin-bottom:4px">' + renderContent(clue.content) + '</div>';
  h += '<div style="font-size:11px;color:#888">来源: ' + clue.source + '</div>';
  h += '</div>';
  
  // Section 2: Related NPCs (before timeline)
  var npcs = [];
  for (var i = 0; i < DATA.npcs.length; i++) {
    var np = DATA.npcs[i];
    if (clue.source === np.name || (clue.content && clue.content.indexOf(np.name) >= 0))
      if (npcs.indexOf(np) < 0) npcs.push(np);
  }
  if (npcs.length) {
    h += '<div style="margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #1a2a30">';
    h += '<div style="font-size:11px;color:#888;margin-bottom:4px">相关人物 (' + npcs.length + ')</div>';
    for (var i = 0; i < npcs.length; i++) {
      h += '<span class="drill-chip npc" onclick="event.stopPropagation();openNpc(\'' + escAttr(npcs[i].name) + '\')">' + npcs[i].name + '</span>';
    }
    h += '</div>';
  }
  
  // Section 3: Timeline events (clickable)
  var tlEvents = [];
  for (var i = 0; i < DATA.events.length; i++) {
    var ev = DATA.events[i];
    var relClues = [];
    try { relClues = JSON.parse(ev.related_clues || '[]'); } catch(e) {}
    if (relClues.indexOf(id) >= 0) tlEvents.push({ev: ev, idx: i});
  }
  if (tlEvents.length) {
    h += '<div style="margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #1a2a30">';
    h += '<div style="font-size:11px;color:#888;margin-bottom:4px">时间线 (' + tlEvents.length + ')</div>';
    for (var i = 0; i < tlEvents.length; i++) {
      h += '<div class="wiki-card" onclick="event.stopPropagation();openTimeline(' + tlEvents[i].idx + ')" style="cursor:pointer">' +
        '<div style="margin-bottom:1px"><b>' + tlEvents[i].ev.event_time + '</b></div>' +
        '<div class="wiki-body">' + tlEvents[i].ev.event + '</div></div>';
    }
    h += '</div>';
  }
  
  // Section 4: Related clues
  if (allRelatedIds.length) {
    h += '<div style="margin-bottom:4px">';
    h += '<div style="font-size:11px;color:#888;margin-bottom:4px">关联线索 (' + allRelatedIds.length + ')</div>';
    for (var i = 0; i < allRelatedIds.length; i++) {
      var rc = findClue(allRelatedIds[i]);
      if (!rc) continue;
      var rcf = rc.confidence || 'medium';
      h += '<div class="wiki-card" onclick="event.stopPropagation();openRelated(\'' + rc.id + '\')">' +
        '<div style="margin-bottom:2px">' + rc.id + ' <span class="v-confirmed" style="font-size:10px;margin-right:3px">已证实</span><span class="c-' + rcf + '">' + cl(rcf) + '</span></div>' +
        '<div class="wiki-body">' + rc.content + '</div></div>';
    }
    h += '</div>';
  } else {
    h += '<div style="font-size:12px;color:#555">关联线索: 无</div>';
  }
  
  h += '</div>';
  drill([{html: h}], clue.id);
}
window.openRelated = openRelated;
