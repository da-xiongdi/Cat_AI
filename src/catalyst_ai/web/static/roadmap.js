(() => {
  const panel = document.querySelector('#roadmap-canvas');
  if (!panel) return;
  const seed = panel.querySelector('.roadmap-seed');
  const stages = JSON.parse(seed.dataset.stages), nodes = JSON.parse(seed.dataset.nodes);
  const path = JSON.parse(seed.dataset.path), selected = path[path.length - 1];
  const expanded = new Set(stages.flatMap(s => s.root_ids));
  const loaded = new Set(expanded), viewport = panel.querySelector('.roadmap-viewport');
  const content = panel.querySelector('.roadmap-content'), progress = panel.querySelector('.roadmap-progress');
  let scale = 1, busy = false;
  function drawNode(id) {
    const n = nodes[id], box = document.createElement('div');
    box.className = 'roadmap-branch';
    const card = document.createElement('div'); card.className = 'roadmap-card';
    if (id === selected) { card.classList.add('selected'); card.setAttribute('aria-current', 'true'); }
    const link = document.createElement('a'); link.href = '/roadmap?node=' + encodeURIComponent(id);
    link.textContent = n.display_name; card.append(link);
    const summary = document.createElement('small');
    summary.textContent = `${id} · 已验收有效 ${n.summary.valid_completed}/${n.summary.valid_total}`;
    card.append(summary);
    if (n.child_ids.length) {
      const toggle = document.createElement('button'); toggle.type = 'button';
      toggle.textContent = expanded.has(id) ? '收起' : '展开';
      toggle.setAttribute('aria-expanded', String(expanded.has(id)));
      toggle.setAttribute('aria-label', `${toggle.textContent} ${n.display_name}`);
      toggle.addEventListener('click', async () => {
        if (expanded.has(id)) expanded.delete(id);
        else { if (!await load(id)) return; expanded.add(id); }
        draw();
      }); card.append(toggle);
    }
    box.append(card);
    if (expanded.has(id)) {
      const children = document.createElement('div'); children.className = 'roadmap-children';
      n.child_ids.filter(child => nodes[child]).forEach(child => children.append(drawNode(child)));
      box.append(children);
    }
    return box;
  }
  function draw() {
    content.replaceChildren();
    stages.forEach(stage => {
      const col = document.createElement('section'); col.className = 'roadmap-stage';
      const title = document.createElement('h3'); title.textContent = `${stage.stage} · ${stage.name}`; col.append(title);
      if (!stage.registered) { const p = document.createElement('p'); p.textContent = '尚未登记'; col.append(p); }
      stage.root_ids.forEach(id => col.append(drawNode(id))); content.append(col);
    });
    content.style.zoom = scale;
  }
  async function load(id) {
    if (loaded.has(id)) return true;
    try {
      const response = await fetch('/api/workbench/v1/roadmap/nodes/' + encodeURIComponent(id) + '/children');
      if (!response.ok) throw new Error(response.status);
      const result = await response.json(); result.items.forEach(n => { nodes[n.id] = n; });
      loaded.add(id); return true;
    } catch (_) { progress.textContent = `分支 ${id} 读取失败，请重试。`; return false; }
  }
  panel.querySelector('.roadmap-controls').addEventListener('click', async event => {
    const action = event.target.dataset.action; if (!action || busy) return;
    if (action === 'expand') {
      busy = true; let done = 0, failures = [];
      const queue = stages.flatMap(s => s.root_ids);
      while (queue.length) {
        const id = queue.shift(), n = nodes[id]; if (!n || !n.child_ids.length) continue;
        progress.textContent = `正在加载分支：已处理 ${done}，待处理 ${queue.length + 1}`;
        if (await load(id)) { expanded.add(id); queue.push(...n.child_ids); } else failures.push(id);
        done++; draw();
      }
      progress.textContent = failures.length ? `读取失败：${failures.join('、')}，可再次展开重试。` : `加载完成，已处理 ${done} 个分支。`;
      busy = false;
    } else if (action === 'collapse') { expanded.clear(); draw(); }
    else if (action === 'in' || action === 'out') { scale = Math.max(.3, Math.min(2, scale * (action === 'in' ? 1.2 : 1 / 1.2))); draw(); }
    else if (action === 'reset') { expanded.clear(); stages.flatMap(s => s.root_ids).forEach(id => expanded.add(id)); scale = 1; draw(); viewport.scrollTo(0, 0); }
    else if (action === 'fit') { scale = 1; draw(); scale = Math.min(1, Math.max(.3, viewport.clientWidth / content.scrollWidth)); draw(); viewport.scrollTo(0, 0); }
    else if (action === 'fullscreen') { try { if (document.fullscreenElement) await document.exitFullscreen(); else await panel.requestFullscreen(); } catch (_) { progress.textContent = '无法进入全屏。'; } }
  });
  let drag;
  viewport.addEventListener('pointerdown', e => { if (e.target.closest('a,button')) return; drag = [e.clientX, e.clientY, viewport.scrollLeft, viewport.scrollTop]; viewport.setPointerCapture(e.pointerId); });
  viewport.addEventListener('pointermove', e => { if (drag) { viewport.scrollLeft = drag[2] - (e.clientX - drag[0]); viewport.scrollTop = drag[3] - (e.clientY - drag[1]); } });
  viewport.addEventListener('pointerup', () => { drag = null; });
  viewport.addEventListener('pointercancel', () => { drag = null; });
  async function initialize() {
    panel.hidden = false;
    for (const id of path.slice(0, -1)) {
      if (!await load(id)) break;
      expanded.add(id);
    }
    draw();
    const target = content.querySelector('.roadmap-card.selected');
    if (target && seed.dataset.view !== 'tree' && !location.hash) {
      target.scrollIntoView({block: 'nearest', inline: 'center'});
    }
  }
  initialize();
})();
