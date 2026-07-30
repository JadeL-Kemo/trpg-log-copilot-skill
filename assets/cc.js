/* ============================================================
   Character Card v2.1 — Core Engine
   分类标签: 👤角色(PC+NPC) / 👾怪物(MONSTER)
   双视图: 紧凑小卡片(默认) → 点击展开速览卡 → 角色纸全页
   依赖: cc.css (样式), DATA (全局数据对象)
   ============================================================ */

const CC = (() => {
  'use strict';

  // ============ State ============
  let currentTab  = 'pc';        // 'pc' | 'npc' | 'monster' | 'other'
  let currentView = 'tile';      // 'tile' | 'sheet' — Grid 专用
  let modalView   = 'tile';      // 'tile' | 'sheet' — Modal 专用
  let entities    = [];
  let rootEl      = null;
  let modalEl     = null;        // modal overlay DOM

  // ============ 实体工厂 (unchanged from v2.0) ============

  function buildEntities() {
    const result = [];
    const seen = new Set();

    // --- PC from DATA.chars (type==='pc' only) ---
    if (Array.isArray(DATA.chars)) {
      DATA.chars.forEach((c, i) => {
        if (c.type !== 'pc') return;
        const id = c.id || `PC-${String(i+1).padStart(3,'0')}`;
        seen.add(id);
        let pools = c.derived_pools || {};
        if (!c.derived_pools && c.pools) pools = translatePools(c.pools);
        result.push(normalizeEntity({
          id, name: c.name,
          entity_type: 'pc',
          occupation: c.occupation || '',
          age: c.age || null,
          background: c.background || '',
          appearance: c.appearance || '',
          portrait: c.portrait || null,
          status: c.status || 'active',
          tags: c.tags || [],
          system: c.system || 'CoC',
          base_stats: c.base_stats || {},
          derived_pools: pools,
          skills: c.skills || {},
          weapons: c.weapons || [],
          armor: c.armor || {},
          scene_id: c.scene_id || null,
          notes: c.notes || '',
        }));
      });
    }

    // --- NPC + Monster from DATA.npcs ---
    if (Array.isArray(DATA.npcs)) {
      DATA.npcs.forEach(n => {
        const isMonster = detectMonster(n);
        const id = n.id || (isMonster
          ? `MON-${String(result.filter(e=>e.entity_type==='monster').length+1).padStart(3,'0')}`
          : `NPC-${String(result.filter(e=>e.entity_type==='npc').length+1).padStart(3,'0')}`);
        seen.add(id);

        let keyFacts = [];
        let relationships = [];
        try { keyFacts = JSON.parse(n.key_facts || '[]'); } catch { keyFacts = (n.key_facts||'').split(';').filter(Boolean); }
        try { relationships = JSON.parse(n.relationships || '[]'); } catch { relationships = []; }
        // Normalize: split semicolon-delimited blob strings into individual tokens
        relationships = parseRelBlob(relationships);

        result.push(normalizeEntity({
          id, name: n.name,
          entity_type: isMonster ? 'monster' : 'npc',
          role: n.role || '',
          faction: n.faction || '',
          stance: n.stance || 'unknown',
          appearance: n.appearance || '',
          portrait: null,
          status: n.status || 'active',
          tags: [],
          system: isMonster ? 'CoC' : null,
          sc_on_sight: n.sc_on_sight || null,
          sc_on_close: n.sc_on_close || null,
          attack_skills: n.attack_skills || [],
          defense: n.defense || null,
          abilities: n.abilities || [],
          behavior_pat: n.behavior_pat || [],
          weaknesses: n.weaknesses || [],
          monster_type: isMonster ? (n.monster_type || '') : null,
          movement: n.movement || null,
          monster_armor: n.monster_armor || {},
          hp_monster: n.hp_monster || null,
          key_facts: keyFacts,
          relationships: relationships,
          scene_id: n.scene_id || null,
          notes: n.notes || '',
        }));
      });
    }

    // --- Relations supplement ---
    if (Array.isArray(DATA.relations)) {
      result.forEach(e => {
        if (!e.relationships) e.relationships = [];
        DATA.relations.forEach(r => {
          const sName = (r.source_id || r.npc_a || '').toLowerCase();
          const tName = (r.target_id || r.npc_b || '').toLowerCase();
          if (e.name.toLowerCase() === sName) {
            e.relationships.push({ target: findName(result, r.npc_b), type: r.rel_type });
          }
          if (e.name.toLowerCase() === tName) {
            e.relationships.push({ target: findName(result, r.npc_a), type: r.rel_type });
          }
        });
      });
    }

    // --- Post-process: resolve IDs to names, separate clues ---
    result.forEach(e => {
      if (!e.relationships || !e.relationships.length) return;
      const chars = [];
      const clues = [];
      e.relationships.forEach(r => {
        if (r.isClue) {
          clues.push(r);
        } else if (typeof r === 'string') {
          chars.push({ target: findName(result, r), type: '关联' });
        } else if (r.target && typeof r.target === 'string' && r.target.match(/^(NPC|PC|MON)-\d+$/)) {
          chars.push({ target: findName(result, r.target), type: r.type || '关联' });
        } else {
          chars.push(r);
        }
      });
      e.relationships = chars;
      if (clues.length) e.clue_refs = clues;
    });

    // --- HP/SAN from char_state_log ---
    result.forEach(e => {
      if (e.entity_type === 'pc' && Array.isArray(DATA.char_state_log)) {
        const logs = DATA.char_state_log.filter(l => l.char_name === e.name);
        if (logs.length) {
          const latest = logs[logs.length-1];
          if (e.derived_pools.hp && latest.hp !== undefined) e.derived_pools.hp.current = latest.hp;
          if (e.derived_pools.san && latest.san !== undefined) e.derived_pools.san.current = latest.san;
          if (e.derived_pools.mp && latest.mp !== undefined) e.derived_pools.mp.current = latest.mp;
        }
      }
    });

    return result;
  }

  function detectMonster(n) {
    if (n.faction === '实体侧') return true;
    if (n.stance === '敌对') return true;
    if (typeof n.key_facts === 'string') {
      return ['火焰','怪物','实体','不可名状','异界','不死','深潜','神话'].some(k => n.key_facts.includes(k));
    }
    return false;
  }

  // Strip NPC name prefix from relation descriptions
  // "父亲" → "父亲", "玛莎，女友同学" → "女友同学", "李锐光，导师，oneway" → "导师"
  function cleanRelType(desc) {
    if (!desc) return '关联';
    var commas = [];
    for (var i = 0; i < desc.length; i++) { if (desc[i] === '，' || desc[i] === ',') commas.push(i); }
    if (commas.length === 0) return desc;
    // Multi-comma (name, type, direction): take middle segment
    if (commas.length >= 2) return desc.slice(commas[0] + 1, commas[commas.length - 1]).trim();
    // Single comma: text after comma
    return desc.slice(commas[0] + 1).trim();
  }

  // Parse relationship blob tokens like "NPC-008（父亲）; CL-068（描述）" into {target, type} + {clueId, desc}
  function parseRelBlob(rels) {
    if (!rels || !rels.length) return rels;
    const out = [];
    rels.forEach(r => {
      const raw = typeof r === 'string' ? r : (r.target || '');
      if (!raw.includes(';') && (raw.startsWith('NPC-') || raw.startsWith('PC-') || raw.startsWith('CL-') || raw.startsWith('MON-'))) {
        // Single reference — keep as-is but parse if needed
        const m = raw.match(/^((?:NPC|PC|MON|CL)-\d+)(?:（(.+)）)?$/);
        if (m) {
          const isClue = m[1].startsWith('CL');
          out.push({ target: m[1], type: isClue ? (m[2] || '') : cleanRelType(m[2] || '关联'), isClue: isClue, desc: m[2] || '' });
        } else {
          out.push(typeof r === 'string' ? { target: raw, type: '关联' } : r);
        }
        return;
      }
      const tokens = raw.split(';').filter(Boolean);
      tokens.forEach(tok => {
        const t = tok.trim();
        const m = t.match(/^((?:NPC|PC|MON|CL)-\d+)(?:（(.+)）)?$/);
        if (m) {
          const isClue = m[1].startsWith('CL');
          out.push({ target: m[1], type: isClue ? (m[2] || '') : cleanRelType(m[2] || '关联'), isClue: isClue, desc: m[2] || '' });
        }
      });
    });
    return out;
  }

  function translatePools(pools) {
    const km = { '生命值':'hp', '理智值':'san', '魔力值':'mp' };
    const r = {};
    Object.entries(pools || {}).forEach(([k,v]) => {
      const ek = km[k] || k;
      r[ek] = { max: v.max || v.max_hp || 0, current: v.cur || v.current || v.max || 0 };
    });
    return r;
  }

  function findName(arr, key) {
    const e = arr.find(x => x.id === key || x.name === key);
    return e ? e.name : key;
  }

  function findEntityByName(name) {
    const n = name.toLowerCase();
    return entities.find(e => e.name.toLowerCase() === n || e.id.toLowerCase() === n) || null;
  }

  function relLink(targetName) {
    const ent = findEntityByName(targetName);
    const displayName = ent ? ent.name : targetName;
    const a = doc('a', { class: 'cc-rel-link', text: displayName, href: '#' });
    if (ent) {
      a.addEventListener('click', function(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        showModal(ent);
      });
    } else {
      a.addEventListener('click', function(ev) { ev.preventDefault(); });
      a.classList.add('cc-rel-nolink');
    }
    return a;
  }

  function parseKeyFact(text) {
    const frag = document.createDocumentFragment();
    const re = /((?:NPC|PC|MON|CL)-\d+(?:（[^）]*）)?)/g;
    let lastIdx = 0, match;
    while ((match = re.exec(text)) !== null) {
      if (match.index > lastIdx) {
        frag.appendChild(doc('span', { text: text.slice(lastIdx, match.index) }));
      }
      const ref = match[1];
      const idMatch = ref.match(/^((?:NPC|PC|MON|CL)-\d+)/);
      const id = idMatch ? idMatch[1] : ref;
      const desc = ref.slice(id.length).replace(/[（）]/g, '');

      const chip = doc('span', { class: 'cc-ref-chip' });
      if (id.startsWith('CL')) {
        chip.classList.add('clue');
        chip.textContent = ref;
      } else {
        chip.appendChild(relLink(id));
        if (desc) chip.appendChild(doc('span', { text: ' (' + desc + ')', class: 'cc-ref-desc' }));
      }
      frag.appendChild(chip);
      lastIdx = match.index + match[0].length;
    }
    if (lastIdx < text.length) {
      frag.appendChild(doc('span', { text: text.slice(lastIdx) }));
    }
    return frag;
  }

  function normalizeEntity(raw) {
    const e = { ...raw };
    e.tags = Array.isArray(e.tags) ? e.tags : [];
    e.skills = e.skills && typeof e.skills === 'object' ? e.skills : {};
    e.weapons = Array.isArray(e.weapons) ? e.weapons : [];
    e.key_facts = Array.isArray(e.key_facts) ? e.key_facts : [];
    e.relationships = Array.isArray(e.relationships) ? e.relationships : [];
    e.attack_skills = Array.isArray(e.attack_skills) ? e.attack_skills : [];
    e.abilities = Array.isArray(e.abilities) ? e.abilities : [];
    e.behavior_pat = Array.isArray(e.behavior_pat) ? e.behavior_pat : [];
    e.weaknesses = Array.isArray(e.weaknesses) ? e.weaknesses : [];
    e.properties = Array.isArray(e.properties) ? e.properties : [];
    e.effects = Array.isArray(e.effects) ? e.effects : [];
    if (e.derived_pools && typeof e.derived_pools === 'object') {
      const dp = e.derived_pools;
      if (dp.hp && dp.hp.current === undefined) dp.hp.current = dp.hp.max || 0;
      if (dp.san && dp.san.current === undefined) dp.san.current = dp.san.max || 0;
      if (dp.mp && dp.mp.current === undefined) dp.mp.current = dp.mp.max || 0;
    }
    return e;
  }

  // ============ 实体分组 ============

  function getByType(type) { return entities.filter(e => e.entity_type === type); }

  // ============ 渲染入口 ============

  function init(containerSelector) {
    rootEl = typeof containerSelector === 'string'
      ? document.querySelector(containerSelector) : containerSelector;
    if (!rootEl) { console.warn('CC: container not found'); return; }

    entities = buildEntities();
    currentTab = 'pc';
    currentView = 'tile';
    modalView   = 'tile';

    // 创建全局模态层（挂到 body 级别避免被 tab 切换销毁）
    ensureModal();
    renderAll();
  }

  function ensureModal() {
    const existing = document.getElementById('cc-modal');
    if (existing) { modalEl = existing; return; }
    const overlay = document.createElement('div');
    overlay.id = 'cc-modal';
    overlay.className = 'cc-modal';
    overlay.innerHTML = '<div class="cc-modal-bd" id="cc-modal-bd"></div>';
    overlay.addEventListener('click', function(e) {
      if (e.target === overlay) closeModal();
    });
    document.body.appendChild(overlay);
    modalEl = overlay;
  }

  function renderAll() {
    window.__cc_rendering = true;
    rootEl.innerHTML = '';
    rootEl.appendChild(buildToolbar());
    const grid = doc('div', { id: 'cc-grid', class: 'cc-grid cols2' });
    rootEl.appendChild(grid);
    renderGrid(grid);
    closeModal(); // 切换 tab/view 时关闭弹窗
    // Defer via macrotask: observer fires as microtask after this tick.
    // setTimeout ensures flag stays true across the microtask checkpoint.
    setTimeout(() => { window.__cc_rendering = false; }, 0);
  }

  // ============ Toolbar ============

  function buildToolbar() {
    const bar = doc('div', { class: 'cc-toolbar' });

    // 4 类筛选标签
    const tabs = doc('div', { class: 'cc-tabs' });
    const tabDefs = [
      { key:'pc',      icon:'👤', label:'玩家(PC)' },
      { key:'npc',     icon:'🧑', label:'人物(NPC)' },
      { key:'monster', icon:'👾', label:'怪物' },
      { key:'other',   icon:'📦', label:'其它' },
    ];
    tabDefs.forEach(t => {
      const btn = doc('button', {
        class: 'cc-tab-btn' + (currentTab === t.key ? ' active' : ''),
        'data-tab': t.key,
        html: `${t.icon} ${t.label}`
      });
      btn.addEventListener('click', () => {
        if (currentTab === t.key) return;
        currentTab = t.key;
        closeModal();
        if (currentView === 'sheet') { currentView = 'tile'; }
        refreshToolbar();
        const grid = rootEl.querySelector('#cc-grid');
        if (grid) renderGrid(grid);
      });
      tabs.appendChild(btn);
    });
    bar.appendChild(tabs);

    return bar;
  }

  function refreshToolbar() {
    rootEl.querySelectorAll('.cc-tab-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.tab === currentTab);
    });
  }

  // ============ Grid Render ============

  function renderGrid(grid) {
    grid.innerHTML = '';
    const list = getByType(currentTab);

    if (currentView === 'sheet') {
      grid.className = 'cc-grid cols1';
      grid.style.gridTemplateColumns = '1fr';
      list.forEach(e => grid.appendChild(renderSheet(e)));
      return;
    }

    // Tile mode — 始终渲染紧凑小卡片，点击弹窗展开速览
    grid.className = 'cc-grid cols2';
    grid.style.gridTemplateColumns = '';

    const typeLabels = {pc:'玩家数据',npc:'人物数据',monster:'怪物数据',other:'其他数据'};

    if (!list.length) {
      grid.innerHTML = `<div class="cc-empty">暂无${typeLabels[currentTab]||'数据'}</div>`;
      return;
    }

    list.forEach(e => grid.appendChild(renderTile(e)));
  }

  // ============ 紧凑小卡片 (Tile) ============

  function renderTile(e) {
    const tile = doc('div', {
      class: 'cc-tile clickable',
      'data-id': e.id
    });
    tile.addEventListener('click', () => { showModal(e); });

    // Left avatar
    const av = doc('div', { class: 'cc-tile-av' });
    if (e.portrait) {
      av.innerHTML = `<img src="${esc(e.portrait)}" alt="${esc(e.name)}">`;
    } else {
      av.innerHTML = `<span class="cc-tile-icon">${entityIcon(e)}</span>`;
    }
    tile.appendChild(av);

    // Right body
    const body = doc('div', { class: 'cc-tile-body' });

    // Name row
    const nameRow = doc('div', { class: 'cc-tile-name' });
    nameRow.innerHTML = `${esc(e.name)} <span class="cc-badge ${e.entity_type}">${entityLabel(e.entity_type)}</span>`;
    body.appendChild(nameRow);

    // Subtitle
    const sub = e.occupation || e.role || e.monster_type || '';
    if (sub) {
      const s = doc('div', { class: 'cc-tile-sub', text: sub + (e.age ? ' · '+e.age+'岁' : '') });
      body.appendChild(s);
    }

    // Meta row
    const meta = doc('div', { class: 'cc-tile-meta' });

    if (e.entity_type === 'pc') {
      const dp = e.derived_pools || {};
      const hp = dp.hp || {};
      const san = dp.san || {};
      if (hp.max) meta.appendChild(miniBar('HP', hp.current || hp.max, hp.max, 'hp'));
      if (san.max) meta.appendChild(miniBar('SAN', san.current || san.max, san.max, 'san'));
    } else if (e.entity_type === 'npc') {
      const sMap = { friendly:'🟢', neutral:'🟡', hostile:'🔴', unknown:'⚪' };
      const stanceText = (sMap[e.stance]||'⚪') + (e.faction ? ' '+e.faction : '');
      if (stanceText) meta.innerHTML = `<span>${esc(stanceText)}</span>`;
    } else {
      if (e.faction) meta.textContent = e.faction;
    }

    body.appendChild(meta);

    if (e.tags.length) {
      const tags = doc('div', { class: 'cc-tile-tags' });
      e.tags.slice(0,3).forEach(t => {
        const sp = doc('span', { class: 'cc-chip', text: '#'+t });
        tags.appendChild(sp);
      });
      body.appendChild(tags);
    }

    tile.appendChild(body);

    // 展开箭头 — 所有实体可点击展开
    const arrow = doc('span', { class: 'cc-tile-x', text: '▸' });
    tile.appendChild(arrow);

    return tile;
  }

  function miniBar(label, cur, max, cls) {
    const pct = max > 0 ? Math.min(100, Math.round(cur/max*100)) : 0;
    const el = doc('div', { class: 'cc-mini' });
    el.innerHTML = `<span class="cc-mini-lbl">${label}</span>
      <span class="cc-mini-val">${cur}/${max}</span>
      <div class="cc-mini-bar"><div class="cc-mini-fill ${cls}" style="width:${pct}%"></div></div>`;
    return el;
  }

  // ============ 速览卡 (Card) — expanded from tile ============

  function renderCard(e) {
    const card = doc('div', { class: 'cc-card' });

    const hd = doc('div', { class: 'cc-card-hd' });

    const av = doc('div', { class: 'cc-card-avatar' });
    if (e.portrait) {
      av.innerHTML = `<img src="${esc(e.portrait)}" alt="${esc(e.name)}">`;
    } else {
      av.innerHTML = `<span class="cc-avatar-fb">${entityIcon(e)}</span>`;
    }
    hd.appendChild(av);

    const info = doc('div', { class: 'cc-card-info' });
    info.innerHTML = `
      <div class="cc-card-name">
        ${esc(e.name)}
        <span class="cc-badge ${e.entity_type}">${entityLabel(e.entity_type)}</span>
      </div>
      <div class="cc-card-sub">${e.occupation || e.role || e.monster_type || ''}${e.age ? ' &nbsp;|&nbsp; '+e.age+'岁' : ''}</div>
    `;
    if (e.tags.length) {
      const tags = doc('div', { class: 'cc-card-tags' });
      e.tags.forEach(t => { const s = doc('span', {class:'cc-rel', text:'#'+t}); tags.appendChild(s); });
      info.appendChild(tags);
    }
    if (e.stance) {
      const sMap = { friendly:'🟢 友善', neutral:'🟡 中立', hostile:'🔴 敌对', unknown:'⚪ 未知' };
      const div = doc('div', { style:'font-size:11px;color:var(--fg3);margin-top:2px;', text:(sMap[e.stance]||e.stance)+(e.faction?' · '+e.faction:'') });
      info.appendChild(div);
    }
    hd.appendChild(info);
    card.appendChild(hd);

    // Body
    const body = doc('div', { class:'cc-card-body' });
    switch (e.entity_type) {
      case 'pc':     renderPCCardBody(body, e); break;
      case 'npc':    renderNPCCardBody(body, e); break;
      case 'monster':renderMonsterCardBody(body, e); break;
      case 'other':  renderOtherCardBody(body, e); break;
    }
    card.appendChild(body);

    // Footer
    if (e.scene_id || e.id) {
      const ft = doc('div', { class:'cc-card-ft' });
      ft.innerHTML = `<span>${esc(e.id)}</span>${e.scene_id ? '<span>登场: '+esc(e.scene_id)+'</span>' : ''}`;
      card.appendChild(ft);
    }

    return card;
  }

  // --- PC Card Body (unchanged) ---
  function renderPCCardBody(body, e) {
    if (e.appearance) addSection(body, '外貌', `<div class="cc-fact">${esc(e.appearance)}</div>`);
    const st = e.base_stats;
    if (st && Object.keys(st).length) {
      const sec = addSection(body, '基础属性', '');
      const row = doc('div', {class:'cc-stats-row'});
      const labels = e.system === 'DND'
        ? ['STR','DEX','CON','INT','WIS','CHA']
        : ['STR','CON','DEX','APP','POW','SIZ','INT','EDU','LUCK'];
      labels.forEach(l => {
        if (st[l] !== undefined) {
          const stat = doc('div', {class:'cc-stat'});
          stat.innerHTML = `<div class="cc-stat-val">${esc(st[l])}</div><div class="cc-stat-lbl">${l}</div>`;
          row.appendChild(stat);
        }
      });
      sec.appendChild(row);
    }
    const pools = e.derived_pools || {};
    if (Object.keys(pools).length) {
      const sec = addSection(body, '状态', '');
      [{key:'hp',label:'HP',css:'hp'},{key:'san',label:'SAN',css:'san'},{key:'mp',label:'MP',css:'mp'}].forEach(p => {
        const val = pools[p.key]; if (!val) return;
        const max = typeof val==='object' ? (val.max||0) : val;
        const cur = typeof val==='object' ? (val.current!==undefined?val.current:max) : val;
        const pct = max>0 ? Math.min(100,Math.round(cur/max*100)) : 0;
        sec.appendChild(renderPoolBar(p.label, cur, max, pct, p.css));
      });
    }
    const skills = e.skills;
    if (skills && Object.keys(skills).length) {
      const sec = addSection(body, '技能', '');
      const list = doc('div', {class:'cc-skill-list'});
      Object.entries(skills).sort((a,b)=>b[1]-a[1]).slice(0,8).forEach(([k,v]) => {
        list.innerHTML += `<div class="cc-skill"><span class="cc-skill-name">${esc(skillLabel(k))}</span><span class="cc-skill-val">${esc(v)}</span></div>`;
      });
      sec.appendChild(list);
    }
    if (e.weapons.length) {
      const sec = addSection(body, '武器', '');
      e.weapons.forEach(w => {
        const wpn = doc('div', {class:'cc-wpn'});
        wpn.innerHTML = `<div class="cc-wpn-name">${esc(w.name)}</div>
          <div class="cc-wpn-detail">${esc(w.skill||'')} ${w.value||''} · ${esc(w.damage||'')} · ${w.ammo!==undefined?w.ammo+'/'+(w.capacity||'?'):'—'}</div>`;
        sec.appendChild(wpn);
      });
    }
  }

  // --- NPC Card Body (unchanged) ---
  function renderNPCCardBody(body, e) {
    if (e.appearance) addSection(body, '外貌', `<div class="cc-fact">${esc(e.appearance)}</div>`);
    if (e.key_facts && e.key_facts.length) {
      const sec = addSection(body, '关键事实', '');
      e.key_facts.forEach(f => {
        if (f && typeof f === 'string') {
          const div = doc('div', { class: 'cc-fact' });
          div.appendChild(parseKeyFact(f));
          sec.appendChild(div);
        }
      });
    }
    if (e.relationships && e.relationships.length) {
      const sec = addSection(body, '人物关系', '');
      e.relationships.forEach(r => {
        const chip = doc('span', {class:'cc-rel'});
        chip.appendChild(relLink(r.target || ''));
        chip.appendChild(doc('strong', {text:' '+esc(r.type||'related')}));
        sec.appendChild(chip);
      });
    }
    if (e.clue_refs && e.clue_refs.length) {
      const sec = addSection(body, '关联线索', '');
      e.clue_refs.forEach(cr => {
        const chip = doc('span', {class:'cc-rel clue'});
        const id = typeof cr === 'string' ? cr : (cr.target || '');
        const desc = cr.desc ? ': '+cr.desc : '';
        chip.textContent = id + desc;
        sec.appendChild(chip);
      });
    }
    if (e.weapons && e.weapons.length) {
      const sec = addSection(body, '武器', '');
      e.weapons.forEach(w => {
        const wpn = doc('div', {class:'cc-wpn'});
        wpn.innerHTML = `<div class="cc-wpn-name">${esc(w.name)}</div><div class="cc-wpn-detail">${esc(w.damage||'')} · ${esc(w.type||'')}</div>`;
        sec.appendChild(wpn);
      });
    }
  }

  // --- Monster Card Body (unchanged) ---
  function renderMonsterCardBody(body, e) {
    if (e.sc_on_sight || e.sc_on_close) {
      const sec = addSection(body, 'Sanity Check', '');
      const sc = doc('div', {class:'cc-sc'});
      if (e.sc_on_sight) sc.innerHTML += `<div class="cc-sc-item"><span class="cc-sc-lbl">初见 SC</span><span class="cc-sc-val">${esc(e.sc_on_sight)}</span></div>`;
      if (e.sc_on_close) sc.innerHTML += `<div class="cc-sc-item"><span class="cc-sc-lbl">近距 SC</span><span class="cc-sc-val">${esc(e.sc_on_close)}</span></div>`;
      sec.appendChild(sc);
    }
    if (e.appearance) addSection(body, '外貌', `<div class="cc-fact">${esc(e.appearance)}</div>`);
    if (e.attack_skills && e.attack_skills.length) {
      const sec = addSection(body, '攻击方式', '');
      e.attack_skills.forEach(a => {
        const atk = doc('div', {class:'cc-atk'});
        const hits = a.hits > 1 ? ` ×${a.hits}` : '';
        atk.innerHTML = `<div class="cc-atk-row">
          <span class="cc-atk-name">${esc(a.name)}${hits}</span>
          <span class="cc-atk-stat">${esc(a.skill||'')} ${esc(a.value||'')} · ${esc(a.damage||'')}<span class="cc-atk-dmgtype ${a.type||''}">${esc(a.type||'')}</span></span>
        </div>`;
        if (a.notes) atk.innerHTML += `<div style="font-size:10px;color:var(--fg3);margin-top:2px;">${esc(a.notes)}</div>`;
        sec.appendChild(atk);
      });
    }
    if (e.defense) {
      var d = e.defense;
      if (typeof d === 'string') { try { d = JSON.parse(d); } catch(_) { d = {}; } }
      addSection(body, '防御', `${esc(d.type||'')}: ${esc(d.value||'')}`);
    }
    if (e.abilities && e.abilities.length) {
      const sec = addSection(body, '能力', '');
      e.abilities.forEach(a => {
        const ab = doc('div', {class:'cc-fact'});
        ab.innerHTML = `<strong>${esc(a.name||'')}</strong>${a.description?' — '+esc(a.description):''}`;
        sec.appendChild(ab);
      });
    }
    if (e.behavior_pat && e.behavior_pat.length) {
      const sec = addSection(body, '行为模式', '');
      e.behavior_pat.forEach(b => { sec.appendChild(doc('div',{class:'cc-fact',text:`${b.trigger||''} → ${b.action||''}`})); });
    }
    if (e.weaknesses && e.weaknesses.length) {
      const sec = addSection(body, '弱点', '');
      e.weaknesses.forEach(w => { sec.appendChild(doc('div',{class:'cc-fact',text:`${w.name||''}: ${w.description||''}`})); });
    }
    if (e.hp_monster) {
      var hp = e.hp_monster;
      if (typeof hp === 'string') { try { hp = JSON.parse(hp); } catch(_) { hp = {}; } }
      if (hp.max) body.appendChild(renderPoolBar('HP', hp.current||hp.max, hp.max, Math.round((hp.current||hp.max)/hp.max*100), 'hp'));
    }
    if (e.movement || (e.monster_armor && e.monster_armor.value)) {
      let extra = '';
      if (e.movement) extra += `移动: ${e.movement}`;
      if (e.monster_armor && e.monster_armor.value) extra += ` · 护甲: ${e.monster_armor.value} (${e.monster_armor.type||''})`;
      addSection(body, '', extra);
    }
  }

  // --- Other Card Body (unchanged) ---
  function renderOtherCardBody(body, e) {
    if (e.appearance) addSection(body, '描述', `<div class="cc-fact">${esc(e.appearance)}</div>`);
    if (e.properties && e.properties.length) {
      const sec = addSection(body, '属性', '');
      e.properties.forEach(p => {
        sec.appendChild(doc('div',{class:'cc-prop',html:`<span class="cc-prop-key">${esc(p.name)}:</span><span class="cc-prop-val">${esc(p.value)}</span>`}));
      });
    }
    if (e.effects && e.effects.length) {
      const sec = addSection(body, '效果', '');
      e.effects.forEach(ef => { sec.appendChild(doc('div',{class:'cc-fact',text:`${ef.trigger||''}: ${ef.effect||''}`})); });
    }
    if (e.owner_id) addSection(body, '归属', esc(e.owner_id));
  }

  // ============ 角色纸 (Sheet) ============

  function renderSheet(e) {
    const sysClass = e.system === 'DND' ? 'system-dnd'
      : e.system === 'CoC' ? 'system-coc' : 'system-archive';

    const sheet = doc('div', { class: `cc-sheet ${sysClass}` });

    if (e.entity_type === 'monster') {
      const stamp = doc('div', { class:'cc-sheet-stamp', text:'■■■ CLASSIFIED ■■■' });
      sheet.appendChild(stamp);
    }

    const hd = doc('div', { class:'cc-sheet-hd' });
    hd.innerHTML = `
      <div class="cc-sheet-photo">${e.portrait ? `<img src="${esc(e.portrait)}" alt="${esc(e.name)}">` : entityIcon(e)}</div>
      <div class="cc-sheet-meta">
        <div class="cc-sheet-title">${esc(e.name)}</div>
        <div class="cc-sheet-sub">${e.occupation || e.role || e.monster_type || ''} · ${entityLabel(e.entity_type)}</div>
        <div class="cc-sheet-row">
          ${e.age ? `<span><label>年龄</label>${e.age}</span>` : ''}
          ${e.system ? `<span><label>系统</label>${e.system}</span>` : ''}
          ${e.faction ? `<span><label>阵营</label>${esc(e.faction)}</span>` : ''}
          ${e.stance ? `<span><label>立场</label>${esc(e.stance)}</span>` : ''}
        </div>
      </div>`;
    sheet.appendChild(hd);

    if (e.appearance) sheet.appendChild(sheetSection('外貌描写', `<div class="cc-sheet-bottom">${esc(e.appearance)}</div>`));

    switch (e.entity_type) {
      case 'pc':     renderPCSheet(sheet, e); break;
      case 'npc':    renderNPCSheet(sheet, e); break;
      case 'monster':renderMonsterSheet(sheet, e); break;
      case 'other':  renderOtherSheet(sheet, e); break;
    }

    const ft = doc('div', { class:'cc-sheet-ft', text:`${e.id} · ${new Date().toISOString().slice(0,10)} · ${e.system||'N/A'}` });
    sheet.appendChild(ft);
    return sheet;
  }

  function renderPCSheet(sheet, e) {
    const st = e.base_stats || {};
    const stLabels = e.system === 'DND' ? ['STR','DEX','CON','INT','WIS','CHA'] : ['STR','CON','DEX','APP','POW','SIZ','INT','EDU','LUCK'];
    if (Object.keys(st).length) {
      let html = '<div class="cc-sheet-stats">';
      stLabels.forEach(l => {
        if (st[l] !== undefined) {
          html += `<div class="cc-sheet-stat"><span class="cc-sheet-stat-label">${l}</span><div class="cc-sheet-stat-bar"><div class="cc-sheet-pool-fill" style="width:${st[l]}%"></div></div><span class="cc-sheet-stat-val">${st[l]}</span></div>`;
        }
      });
      html += '</div>';
      sheet.appendChild(sheetSection('属性', html));
    }
    const pools = e.derived_pools || {};
    if (Object.keys(pools).length) {
      const poolDiv = doc('div', {class:'cc-sheet-pools'});
      const pds = e.system === 'DND' ? [{key:'hp',label:'HP'},{key:'ac',label:'AC'},{key:'initiative',label:'INIT'}]
        : [{key:'hp',label:'HP'},{key:'san',label:'SAN'},{key:'mp',label:'MP'}];
      pds.forEach(p => {
        const val = pools[p.key]; if (!val) return;
        const max = typeof val==='object'?(val.max||val):val;
        const cur = typeof val==='object'?(val.current!==undefined?val.current:max):val;
        const pct = max>0?Math.min(100,Math.round(cur/max*100)):0;
        poolDiv.innerHTML += `<div class="cc-sheet-pool"><div class="cc-sheet-pool-label">${p.label}</div><div class="cc-sheet-pool-val">${cur}/${max}</div><div class="cc-sheet-pool-bar"><div class="cc-sheet-pool-fill" style="width:${pct}%"></div></div></div>`;
      });
      if (poolDiv.children.length) sheet.appendChild(sheetSection('状态', ''));
      const lastSec = sheet.querySelector('.cc-sheet-sec:last-child .cc-sheet-sec-body');
      if (lastSec) lastSec.appendChild(poolDiv);
    }
    const ext = [];
    const dp = e.derived_pools || {};
    if (dp.db !== undefined) ext.push(`DB: ${dp.db}`);
    if (dp.build !== undefined) ext.push(`Build: ${dp.build}`);
    if (dp.mov !== undefined) ext.push(`MOV: ${dp.mov}`);
    const dodge = e.skills?.dodge || (e.base_stats?.DEX ? Math.floor(e.base_stats.DEX/2) : null);
    if (dodge) ext.push(`闪避: ${dodge}%`);
    if (ext.length) addSheetRow(sheet, ext.join(' · '));

    const skills = e.skills || {};
    if (Object.keys(skills).length) {
      const sorted = Object.entries(skills).sort((a,b)=>b[1]-a[1]);
      let html = '<div class="cc-sheet-skills-2col">';
      sorted.forEach(([k,v]) => {
        html += `<div class="cc-sheet-skill"><span class="cc-sheet-skill-name">${esc(skillLabel(k))}</span><span class="cc-sheet-skill-val">${v}</span><div class="cc-sheet-skill-bar"><div class="cc-sheet-pool-fill" style="width:${v}%"></div></div></div>`;
      });
      html += '</div>';
      sheet.appendChild(sheetSection('技能', html));
    }
    if (e.weapons.length) {
      let html = '';
      e.weapons.forEach(w => {
        html += `<div class="cc-sheet-wpn"><span class="cc-sheet-wpn-name">${esc(w.name)}</span><span>${esc(w.skill||'')} ${w.value||''}</span><span>${esc(w.damage||'')}</span><span>${w.ammo!==undefined?w.ammo+'/'+(w.capacity||'?'):'—'}</span></div>`;
      });
      sheet.appendChild(sheetSection('武器', html));
    }
    if (e.background) sheet.appendChild(sheetSection('背景', `<div class="cc-sheet-bottom">${esc(e.background)}</div>`));
  }

  function renderNPCSheet(sheet, e) {
    if (e.key_facts && e.key_facts.length) {
      const sec = sheetSection('关键事实', '');
      e.key_facts.forEach((f,i) => {
        if (f && typeof f === 'string') {
          const div = doc('div', {class:'cc-fact'});
          div.style.cssText = 'border:none;padding:2px 0;';
          div.appendChild(doc('span', {text:(i+1)+'. '}));
          div.appendChild(parseKeyFact(f));
          sec.appendChild(div);
        }
      });
      sheet.appendChild(sec);
    }
    if (e.relationships && e.relationships.length) {
      const sec = sheetSection('人物关系', '');
      e.relationships.forEach(r => {
        const div = doc('div', {class:'cc-fact'});
        div.style.cssText = 'border:none;padding:2px 0;';
        div.appendChild(doc('span', {text:'→ '}));
        div.appendChild(relLink(r.target || ''));
        div.appendChild(doc('span', {html:': '+esc(r.type||'关系')}));
        sec.appendChild(div);
      });
      sheet.appendChild(sec);
    }
    if (e.clue_refs && e.clue_refs.length) {
      const sec = sheetSection('关联线索', '');
      e.clue_refs.forEach(cr => {
        const div = doc('div', {class:'cc-fact'});
        div.style.cssText = 'border:none;padding:2px 0;';
        const id = typeof cr === 'string' ? cr : (cr.target || '');
        const desc = cr.desc ? ': '+cr.desc : '';
        div.textContent = '→ ' + id + desc;
        sec.appendChild(div);
      });
      sheet.appendChild(sec);
    }
    if (e.weapons && e.weapons.length) {
      let html = '';
      e.weapons.forEach(w => { html += `<div class="cc-sheet-wpn"><span class="cc-sheet-wpn-name">${esc(w.name)}</span><span>${esc(w.damage||'')}</span></div>`; });
      sheet.appendChild(sheetSection('装备', html));
    }
    if (e.background) sheet.appendChild(sheetSection('概要', `<div class="cc-sheet-bottom">${esc(e.background)}</div>`));
  }

  function renderMonsterSheet(sheet, e) {
    if (e.sc_on_sight || e.sc_on_close) {
      let html = '';
      if (e.sc_on_sight) html += `<div class="cc-sheet-skill"><span>初见 SC</span><span class="cc-sheet-stat-val" style="color:#a00;">${esc(e.sc_on_sight)}</span></div>`;
      if (e.sc_on_close) html += `<div class="cc-sheet-skill"><span>近距 SC</span><span class="cc-sheet-stat-val" style="color:#a00;">${esc(e.sc_on_close)}</span></div>`;
      sheet.appendChild(sheetSection('Sanity Check', html));
    }
    if (e.hp_monster) {
      var hp_m = e.hp_monster;
      if (typeof hp_m === 'string') { try { hp_m = JSON.parse(hp_m); } catch(_) { hp_m = {}; } }
      if (hp_m.max) sheet.appendChild(sheetSection('生命值', `${hp_m.current||hp_m.max}/${hp_m.max}${hp_m.formula?' ('+hp_m.formula+')':''}`));
    }
    if (e.attack_skills && e.attack_skills.length) {
      let html = '';
      e.attack_skills.forEach(a => {
        const hits = a.hits>1?` ×${a.hits}`:'';
        html += `<div class="cc-sheet-atk"><span style="font-weight:700;min-width:100px;">${esc(a.name)}${hits}</span><span>${esc(a.skill||'')} ${esc(a.value||'')}</span><span>${esc(a.damage||'')}</span><span style="color:var(--fg3);">${esc(a.type||'')} ${esc(a.reach||'')}</span></div>`;
        if (a.notes) html += `<div style="font-size:10px;margin-left:100px;opacity:.7;">${esc(a.notes)}</div>`;
      });
      sheet.appendChild(sheetSection('攻击方式', html));
    }
    if (e.defense) {
      var d2 = e.defense;
      if (typeof d2 === 'string') { try { d2 = JSON.parse(d2); } catch(_) { d2 = {}; } }
      addSheetRow(sheet, `防御: ${d2.type||''} ${d2.value||''}`);
    }
    if (e.abilities && e.abilities.length) {
      let html = '';
      e.abilities.forEach(a => { html += `<div class="cc-sheet-ability"><strong>${esc(a.name||'')}</strong>${a.description?': '+esc(a.description):''}</div>`; });
      sheet.appendChild(sheetSection('能力', html));
    }
    if (e.behavior_pat && e.behavior_pat.length) {
      let html = '';
      e.behavior_pat.forEach(b => { html += `<div class="cc-sheet-ability">${esc(b.trigger||'')} → ${esc(b.action||'')}</div>`; });
      sheet.appendChild(sheetSection('行为模式', html));
    }
    if (e.weaknesses && e.weaknesses.length) {
      let html = '';
      e.weaknesses.forEach(w => { html += `<div class="cc-sheet-weakness"><strong>${esc(w.name||'')}</strong>: ${esc(w.description||'')}</div>`; });
      sheet.appendChild(sheetSection('弱点', html));
    }
    if (e.movement || (e.monster_armor && e.monster_armor.value)) {
      const lines = [];
      if (e.movement) lines.push(`移动: ${e.movement}`);
      if (e.monster_armor && e.monster_armor.value) lines.push(`护甲: ${e.monster_armor.value} (${e.monster_armor.type||'—'})`);
      addSheetRow(sheet, lines.join(' · '));
    }
  }

  function renderOtherSheet(sheet, e) {
    if (e.properties && e.properties.length) {
      let html = '';
      e.properties.forEach(p => { html += `<div class="cc-prop"><span class="cc-prop-key">${esc(p.name)}:</span><span class="cc-prop-val">${esc(p.value)}</span></div>`; });
      sheet.appendChild(sheetSection('属性', html));
    }
    if (e.effects && e.effects.length) {
      let html = '';
      e.effects.forEach(ef => { html += `<div class="cc-sheet-ability">${esc(ef.trigger||'')}: ${esc(ef.effect||'')}</div>`; });
      sheet.appendChild(sheetSection('效果', html));
    }
    if (e.owner_id) addSheetRow(sheet, `归属: ${esc(e.owner_id)}`);
  }

  // ============ 工具函数 ============

  function addSection(body, title, content) {
    const sec = doc('div', {class:'cc-card-sec'});
    if (title) sec.appendChild(doc('div', {class:'cc-card-sec-title', text:title}));
    if (typeof content === 'string') { const d = doc('div'); d.innerHTML = content; sec.appendChild(d); }
    body.appendChild(sec);
    return sec;
  }

  function sheetSection(title, content) {
    const sec = doc('div', {class:'cc-sheet-sec'});
    if (title) sec.appendChild(doc('div', {class:'cc-sheet-sec-hd', text:title}));
    const bd = doc('div', {class:'cc-sheet-sec-body'});
    if (typeof content === 'string') bd.innerHTML = content;
    else if (content instanceof Node) bd.appendChild(content);
    sec.appendChild(bd);
    return sec;
  }

  function addSheetRow(sheet, text) {
    const sec = doc('div', {class:'cc-sheet-sec'});
    sec.appendChild(doc('div', {class:'cc-sheet-sec-body', html:`<div style="font-size:12px;">${esc(text)}</div>`}));
    sheet.appendChild(sec);
  }

  function renderPoolBar(label, cur, max, pct, cssClass) {
    const div = doc('div', {class:'cc-pool'});
    div.innerHTML = `<div class="cc-pool-info"><span class="cc-pool-name">${label}</span><span class="cc-pool-val">${cur} / ${max}</span></div>
    <div class="cc-pool-bar"><div class="cc-pool-bar-fill ${cssClass}" style="width:${pct}%"></div></div>`;
    return div;
  }

  function entityIcon(e) {
    return {pc:'👤',npc:'🧑',monster:'👾',other:'📦'}[e.entity_type] || '❓';
  }

  function entityLabel(type) {
    return {pc:'PC',npc:'NPC',monster:'MONSTER',other:'OTHER'}[type] || type.toUpperCase();
  }

  function skillLabel(key) {
    const map = {
      spot_hidden:'知觉',firearms:'火器',dodge:'闪避',psychology:'心理',
      persuade:'说服',intimidate:'恐吓',drive_auto:'驾驶',listen:'聆听',
      law:'法律',cr:'信用',first_aid:'急救',stealth:'潜行',
      library_use:'图书馆',occult:'神秘学',locksmith:'锁匠',
      climb:'攀爬',jump:'跳跃',swim:'游泳',throw:'投掷',
      accounting:'会计',anthropology:'人类学',archaeology:'考古',
      charm:'魅惑',history:'历史',medicine:'医学',nature:'自然',
      perception:'察觉',investigation:'调查',survival:'生存',
      athletics:'运动',acrobatics:'特技',sleight_of_hand:'巧手',
      arcana:'奥秘',religion:'宗教',insight:'洞悉',performance:'表演',
      deception:'欺瞒',animal_handling:'驯兽',
    };
    return map[key] || key;
  }

  function esc(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

  function doc(tag, attrs) {
    const el = document.createElement(tag);
    if (attrs) {
      Object.entries(attrs).forEach(([k,v]) => {
        if (k === 'class') el.className = v;
        else if (k === 'text') el.textContent = v;
        else if (k === 'html') el.innerHTML = v;
        else if (k === 'style') { if (typeof v === 'string') el.style.cssText = v; else Object.assign(el.style, v); }
        else el.setAttribute(k, v);
      });
    }
    return el;
  }

  // ============ Modal ============

  function showModal(entity) {
    if (!modalEl) ensureModal();
    const bd = document.getElementById('cc-modal-bd');
    if (!bd) return;
    bd.innerHTML = '';

    // 顶部：选项卡 + 关闭
    const topBar = doc('div', { class: 'cc-modal-top' });
    const tabs = doc('div', { class: 'cc-modal-tabs' });

    const cardTab = doc('button', {
      class: 'cc-tab' + (modalView !== 'sheet' ? ' active' : ''),
      text: '📋 速览卡'
    });
    cardTab.addEventListener('click', () => {
      if (modalView !== 'tile') { modalView = 'tile'; showModal(entity); }
    });
    tabs.appendChild(cardTab);

    const sheetTab = doc('button', {
      class: 'cc-tab' + (modalView === 'sheet' ? ' active' : ''),
      text: '📜 角色纸'
    });
    sheetTab.addEventListener('click', () => {
      if (modalView !== 'sheet') { modalView = 'sheet'; showModal(entity); }
    });
    tabs.appendChild(sheetTab);

    topBar.appendChild(tabs);

    const closeBtn = doc('button', { class:'cc-modal-close', text:'✕' });
    closeBtn.addEventListener('click', closeModal);
    topBar.appendChild(closeBtn);

    bd.appendChild(topBar);
    bd.appendChild(modalView === 'sheet' ? renderSheet(entity) : renderCard(entity));
    modalEl.classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  function closeModal() {
    if (modalEl) {
      modalEl.classList.remove('open');
      document.body.style.overflow = '';
    }
  }

  // ============ API ============

  return {
    init, buildEntities, getEntities: () => entities,
    getTab: () => currentTab, getView: () => currentView,
  };

})();
