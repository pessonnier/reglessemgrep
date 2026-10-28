const $ = (id) => document.getElementById(id);
const state = {page: 1, pageSize: 30, total: 0, currentRule: null, currentMatch: null};
const levels = {unknown: 'Non évalué', low: 'Faible', medium: 'Moyen', high: 'Élevé'};
const uncertaintyLevels = {unknown: 'Non évaluée', low: 'Faible', medium: 'Moyenne', high: 'Élevée'};
const assessmentStatuses = {not_evaluated: 'À évaluer', stale: 'À réévaluer', expert_assessed: 'Avis expert enregistré'};

function node(tag, text = '', className = '') {
  const element = document.createElement(tag);
  if (text !== null) element.textContent = String(text);
  if (className) element.className = className;
  return element;
}

async function request(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { const body = await response.json(); message = Array.isArray(body.detail) ? body.detail.map(item => `${item.loc?.slice(1).join('.') || 'Champ'} : ${item.msg}`).join('\n') : body.detail || message; } catch (_) {}
    throw new Error(message);
  }
  return response.json();
}

function show(view) {
  for (const id of ['dashboard', 'explorer', 'detail', 'comparison']) $(id).classList.toggle('hidden', id !== view);
  $('nav-dashboard').classList.toggle('nav-active', view === 'dashboard');
  $('nav-explorer').classList.toggle('nav-active', view !== 'dashboard');
  window.scrollTo({top: 0, behavior: 'instant'});
}

function field(target, label, value) {
  if (value === undefined || value === null || value === '' || (Array.isArray(value) && !value.length)) value = 'Non renseigné';
  const wrapper = node('dl', '', 'field');
  wrapper.append(node('dt', label));
  const description = node('dd');
  if (Array.isArray(value)) value.forEach(item => description.append(node('span', item, 'chip')));
  else description.textContent = String(value);
  wrapper.append(description);
  target.append(wrapper);
}

async function loadDashboard() {
  const data = await request('/api/summary');
  const metrics = $('metrics'); metrics.replaceChildren();
  for (const [label, count] of [
    ['Règles CAST', data.counts.CAST || 0], ['Règles Semgrep', data.counts.Semgrep || 0],
    ['Paires candidates', data.candidates], ['Paires revues', data.reviewed],
    ['CAST sans candidat', data.unmatched.CAST], ['Semgrep sans candidat', data.unmatched.Semgrep]
  ]) {
    const card = node('div', '', 'metric');
    card.append(node('span', label), node('strong', Number(count).toLocaleString('fr-FR')));
    metrics.append(card);
  }
  const snapshots = $('snapshots'); snapshots.replaceChildren();
  if (!data.snapshots.length) snapshots.append(node('p', 'Aucun import. Lancez les commandes indiquées dans le README.', 'muted'));
  data.snapshots.forEach(item => {
    const block = node('div', '', 'snapshot');
    block.append(node('strong', `${item.source} · ${item.status}`));
    block.append(node('span', `${item.collected_at} · version ${item.revision}`, 'small muted'));
    const stats = item.stats || {};
    block.append(node('div', Object.entries(stats).filter(([,v]) => typeof v !== 'object').map(([k,v]) => `${k}: ${v}`).join(' · '), 'small muted'));
    snapshots.append(block);
  });
  distribution('categories', data.categories, 'category');
  distribution('languages', data.languages, 'language');
  distribution('severities', data.severities, 'severity');
  const uncertainty = $('uncertainty-summary'); uncertainty.replaceChildren();
  data.uncertainty.forEach(item => {
    const button = node('button', `${assessmentStatuses[item.status]} · incertitude ${uncertaintyLevels[item.uncertainty_level].toLowerCase()} : ${item.count}`, 'uncertainty-filter');
    button.addEventListener('click', () => {
      $('filters').reset();
      $('filters').elements.source.value = 'Semgrep';
      $('filters').elements.assessment_status.value = item.status;
      $('filters').elements.uncertainty_level.value = item.uncertainty_level;
      state.page = 1;
      loadRules().then(() => show('explorer')).catch(handleError);
    });
    uncertainty.append(button);
  });
}

function distribution(targetId, items, key) {
  const target = $(targetId); target.replaceChildren();
  const top = items.slice(0, 12);
  const max = Math.max(1, ...top.map(item => item.count));
  top.forEach(item => {
    const row = node('div', '', 'bar-row'); row.tabIndex = 0;
    row.append(node('span', `${item[key]} · ${item.source}`, 'small'));
    const bg = node('div', '', 'bar-bg'); const fill = node('div', '', 'bar-fill');
    fill.style.width = `${Math.max(2, item.count / max * 100)}%`; bg.append(fill);
    row.append(bg, node('strong', item.count));
    const action = () => {
      $('filters').reset();
      $('filters').elements.source.value = item.source;
      $('filters').elements[key].value = item[key];
      state.page = 1;
      loadRules().then(() => show('explorer')).catch(handleError);
    };
    row.addEventListener('click', action);
    row.addEventListener('keydown', event => {if (event.key === 'Enter') action();});
    target.append(row);
  });
}

async function loadRules() {
  const params = new URLSearchParams(new FormData($('filters')));
  for (const [key, value] of [...params]) if (!String(value).trim()) params.delete(key);
  params.set('page', state.page); params.set('page_size', state.pageSize);
  const data = await request(`/api/rules?${params}`);
  state.total = data.total;
  $('result-count').textContent = `${Number(data.total).toLocaleString('fr-FR')} règles`;
  $('page-label').textContent = `Page ${data.page} / ${Math.max(1, Math.ceil(data.total / state.pageSize))}`;
  $('prev-page').disabled = data.page <= 1;
  $('next-page').disabled = data.page * state.pageSize >= data.total;
  const body = $('rules-body'); body.replaceChildren();
  data.items.forEach(rule => {
    const row = node('tr'); row.tabIndex = 0;
    const tag = node('span', rule.source, `tag ${rule.source.toLowerCase()}`);
    const source = node('td'); source.append(tag); row.append(source);
    for (const value of [rule.rule_id, rule.title || '—', rule.languages.join(', ') || '—', rule.categories.join(', ') || '—', rule.severity || '—']) row.append(node('td', value));
    const uncertainty = node('td', '', 'uncertainty-cell');
    const u = rule.uncertainty;
    if (u) {
      uncertainty.append(node('strong', uncertaintyLevels[u.uncertainty_level]), node('div', assessmentStatuses[u.status], 'small muted'));
      uncertainty.append(node('div', `Faux positifs : ${levels[u.false_positive_risk]}`, 'small'), node('div', `Non-détection : ${levels[u.false_negative_risk]}`, 'small'));
    } else uncertainty.textContent = '—';
    row.append(uncertainty);
    row.addEventListener('click', () => openRule(rule.rule_key));
    row.addEventListener('keydown', event => {if (event.key === 'Enter') openRule(rule.rule_key);});
    body.append(row);
  });
}

async function openRule(key) {
  const rule = await request(`/api/rule?${new URLSearchParams({key})}`);
  state.currentRule = rule;
  $('detail-source').textContent = rule.source;
  $('detail-title').textContent = rule.title || rule.rule_id;
  $('detail-id').textContent = rule.rule_id;
  $('detail-url').href = rule.source_url;
  $('raw-content').textContent = rule.raw_content || 'Aucun contenu brut disponible.';
  const fields = $('detail-fields'); fields.replaceChildren();
  field(fields, 'Description', rule.description);
  field(fields, 'Raison / objectif', rule.rationale);
  field(fields, 'Correction', rule.remediation);
  field(fields, 'Langages', rule.languages);
  field(fields, 'Technologies / frameworks', [...new Set([...rule.technologies, ...rule.frameworks])]);
  field(fields, 'Catégories · origine', rule.categories.length ? `${rule.categories.join(', ')} · ${rule.classification_origin}` : null);
  field(fields, 'Sévérité', rule.severity);
  field(fields, 'CWE', rule.cwe);
  field(fields, 'OWASP', rule.owasp);
  field(fields, 'Autres référentiels', rule.standards);
  field(fields, 'Mode d’analyse documenté', rule.detection_method);
  field(fields, 'Version source', rule.source_version);
  $('uncertainty-panel').hidden = rule.source !== 'Semgrep';
  const uncertainty = $('uncertainty-detail'); uncertainty.replaceChildren();
  if (rule.uncertainty) {
    uncertaintyFields(uncertainty, rule);
    $('uncertainty-form').reset();
    const u = rule.uncertainty;
    if (u.status === 'expert_assessed') {
      for (const key of ['uncertainty_level', 'false_positive_risk', 'false_negative_risk', 'scope', 'rationale', 'evidence']) {
        $('uncertainty-form').elements[key].value = u[key] || '';
      }
    }
    $('save-uncertainty').disabled = !rule.definition_hash || rule.status !== 'present';
    $('uncertainty-form-status').textContent = rule.definition_hash ? '' : 'Réimportez les règles Semgrep locales pour identifier leur définition avant de les évaluer.';
    const history = $('uncertainty-history'); history.replaceChildren();
    if (!rule.uncertainty_history.length) history.append(node('p', 'Aucune évaluation enregistrée.', 'muted'));
    rule.uncertainty_history.forEach(item => {
      const entry = node('div', '', 'review-item');
      entry.append(node('strong', `${item.reviewer} · ${item.created_at}`));
      field(entry, 'Version évaluée', item.source_version);
      field(entry, 'Empreinte de la définition', item.definition_hash);
      field(entry, 'Incertitude', uncertaintyLevels[item.uncertainty_level]);
      field(entry, 'Faux positifs / non-détection', `${levels[item.false_positive_risk]} / ${levels[item.false_negative_risk]}`);
      field(entry, 'Périmètre', item.scope);
      field(entry, 'Justification', item.rationale);
      field(entry, 'Références déclarées par l’expert', item.evidence);
      history.append(entry);
    });
  }
  await loadMatches(key);
  $('other-results').replaceChildren();
  $('other-query').value = '';
  show('detail');
}

async function loadMatches(key) {
  const data = await request(`/api/matches?${new URLSearchParams({key})}`);
  const target = $('matches'); target.replaceChildren();
  if (!data.items.length) target.append(node('p', 'Aucun candidat identifié pour cette règle.', 'muted'));
  data.items.forEach(match => {
    const block = node('div', '', 'match'); block.tabIndex = 0;
    block.append(node('strong', match.other_title || match.other_id));
    block.append(node('div', `${match.other_id} · Score ${match.score}/100 · Avis : ${match.expert_decision || 'non revu'}`, 'match-meta'));
    block.append(node('div', `${match.evidence_count} références sourcées`, 'match-meta'));
    const action = () => openMatch(match.cast_key, match.semgrep_key);
    block.addEventListener('click', action);
    block.addEventListener('keydown', event => {if (event.key === 'Enter') action();});
    target.append(block);
  });
}

function comparisonFields(target, rule) {
  target.replaceChildren();
  field(target, 'Identifiant', rule.rule_id);
  field(target, 'Description', rule.description);
  field(target, 'Raison / objectif', rule.rationale);
  field(target, 'Langages', rule.languages);
  field(target, 'Catégories', rule.categories);
  field(target, 'CWE', rule.cwe);
  field(target, 'OWASP', rule.owasp);
  field(target, 'Portée / mode documenté', rule.detection_method);
  if (rule.uncertainty) {
    uncertaintyFields(target, rule);
    const edit = node('button', 'Évaluer l’incertitude de cette règle', 'text-button');
    edit.addEventListener('click', () => openRule(rule.rule_key).catch(handleError));
    target.append(edit);
  }
  const link = node('a', 'Voir la source ↗');
  link.href = rule.source_url; link.target = '_blank'; link.rel = 'noopener noreferrer';
  target.append(link);
}

function uncertaintyFields(target, rule) {
  const u = rule.uncertainty;
  field(target, 'Incertitude de l’évaluation', uncertaintyLevels[u.uncertainty_level]);
  field(target, 'Risque estimé de faux positifs', levels[u.false_positive_risk]);
  field(target, 'Risque estimé de non-détection', levels[u.false_negative_risk]);
  field(target, 'Statut / origine', `${assessmentStatuses[u.status]} · ${u.origin === 'expert_opinion' ? 'Avis expert' : 'Valeur par défaut, sans validation'}`);
  field(target, 'Justification et limites', u.rationale);
  if (u.scope) field(target, 'Périmètre de l’avis', u.scope);
  if (u.reviewer) field(target, 'Auteur / date', `${u.reviewer} · ${u.created_at}`);
  if (u.evidence) field(target, 'Références déclarées par l’expert', u.evidence);
  field(target, 'Confiance déclarée par Semgrep (métadonnée)', rule.source_confidence);
  target.append(node('p', 'La confiance déclarée par l’éditeur et les niveaux estimés ne sont pas des probabilités mesurées. Les tests de détection restent à mettre en place.', 'muted small'));
}

async function openMatch(castKey, semgrepKey) {
  const data = await request(`/api/match?${new URLSearchParams({cast_key: castKey, semgrep_key: semgrepKey})}`);
  state.currentMatch = data;
  const factors = data.candidate.factors;
  const score = $('comparison-score'); score.replaceChildren();
  score.append(node('strong', `Score de classement ${data.candidate.score}/100 · ${factors.method || 'méthode inconnue'}`));
  score.append(node('div', `Langage ${factors.technical_compatibility ?? 0}/15 · Défaut référencé ${factors.defect_references ?? 0}/35 · Titre ${factors.title_similarity ?? 0}/20 · Description ${factors.description_similarity ?? 0}/20 · Catégorie ${factors.category_similarity ?? 0}/10`, 'small'));
  score.append(node('div', `Niveau de preuve : ${factors.evidence_level || 'inconnu'} · Préconditions : ${factors.precondition_alignment ?? 'non établies'} · Similarité sémantique : ${factors.semantic_similarity ?? 'non calculée'}`, 'small'));
  score.append(node('div', factors.limitations || '', 'small muted'));
  $('compare-cast-title').textContent = data.cast.title || data.cast.rule_id;
  $('compare-semgrep-title').textContent = data.semgrep.title || data.semgrep.rule_id;
  comparisonFields($('compare-cast'), data.cast);
  comparisonFields($('compare-semgrep'), data.semgrep);
  const evidence = $('evidence'); evidence.replaceChildren();
  if (!data.sourced_evidence.length) evidence.append(node('p', 'Aucune preuve sourcée attachée.', 'muted'));
  data.sourced_evidence.forEach(item => {
    const block = node('div', '', 'evidence-item');
    block.append(node('strong', `${item.dimension} · ${item.origin}`));
    block.append(node('p', `${item.reference_field} : ${item.excerpt}`));
    const link = node('a', 'Ouvrir la référence ↗');
    link.href = item.reference_url; link.target = '_blank'; link.rel = 'noopener noreferrer';
    block.append(link); evidence.append(block);
  });
  const llm = $('llm-proposals'); llm.replaceChildren();
  if (!data.llm_proposals.length) llm.append(node('p', 'Aucune proposition LLM pour cette paire.', 'muted'));
  data.llm_proposals.forEach(item => {
    const block = node('div', '', 'review-item');
    block.append(node('strong', `${item.model} · ${item.created_at}`));
    block.append(node('pre', JSON.stringify(item.proposal, null, 2)));
    llm.append(block);
  });
  const reviews = $('expert-reviews'); reviews.replaceChildren();
  if (!data.expert_reviews.length) reviews.append(node('p', 'Aucun avis expert enregistré.', 'muted'));
  data.expert_reviews.forEach(item => {
    const block = node('div', '', 'review-item');
    block.append(node('strong', `${item.decision} · ${item.reviewer}`));
    block.append(node('div', item.created_at, 'small muted'));
    if (item.comment) block.append(node('p', item.comment));
    reviews.append(block);
  });
  show('comparison');
}

function handleError(error) { window.alert(error.message || String(error)); }

$('nav-dashboard').addEventListener('click', () => {loadDashboard().then(() => show('dashboard')).catch(handleError);});
$('nav-explorer').addEventListener('click', () => {loadRules().then(() => show('explorer')).catch(handleError);});
$('back-to-explorer').addEventListener('click', () => {loadRules().then(() => show('explorer')).catch(handleError);});
$('back-to-detail').addEventListener('click', () => show('detail'));
$('filters').addEventListener('submit', event => {event.preventDefault(); state.page = 1; loadRules().catch(handleError);});
$('prev-page').addEventListener('click', () => {if (state.page > 1) {state.page--; loadRules().catch(handleError);}});
$('next-page').addEventListener('click', () => {if (state.page * state.pageSize < state.total) {state.page++; loadRules().catch(handleError);}});
$('other-search').addEventListener('click', async () => {
  try {
    const source = state.currentRule.source === 'CAST' ? 'Semgrep' : 'CAST';
    const q = $('other-query').value.trim();
    if (!q) return;
    const data = await request(`/api/rules?${new URLSearchParams({source, q, page_size: 20})}`);
    const select = $('other-results'); select.replaceChildren();
    data.items.forEach(rule => {const option = node('option', `${rule.rule_id} — ${rule.title || ''}`); option.value = rule.rule_key; select.append(option);});
  } catch (error) {handleError(error);}
});
$('add-pair').addEventListener('click', async () => {
  try {
    const other = $('other-results').value;
    if (!other) return;
    const cast_key = state.currentRule.source === 'CAST' ? state.currentRule.rule_key : other;
    const semgrep_key = state.currentRule.source === 'Semgrep' ? state.currentRule.rule_key : other;
    await request('/api/candidates', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({cast_key, semgrep_key})});
    await loadMatches(state.currentRule.rule_key);
    await openMatch(cast_key, semgrep_key);
  } catch (error) {handleError(error);}
});
$('review-form').addEventListener('submit', async event => {
  event.preventDefault();
  try {
    const form = new FormData(event.target);
    const data = state.currentMatch;
    await request('/api/reviews', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
      cast_key: data.cast.rule_key, semgrep_key: data.semgrep.rule_key,
      reviewer: form.get('reviewer'), decision: form.get('decision'), comment: form.get('comment')
    })});
    event.target.reset();
    await openMatch(data.cast.rule_key, data.semgrep.rule_key);
  } catch (error) {handleError(error);}
});

$('uncertainty-form').addEventListener('submit', async event => {
  event.preventDefault();
  const rule = state.currentRule;
  const form = event.target;
  $('save-uncertainty').disabled = true;
  try {
    const payload = Object.fromEntries(new FormData(form));
    Object.assign(payload, {rule_key: rule.rule_key, source_version: rule.source_version, definition_hash: rule.definition_hash});
    await request('/api/uncertainty-assessments', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
    await openRule(rule.rule_key);
    $('uncertainty-form-status').textContent = 'Évaluation enregistrée dans l’historique.';
  } catch (error) {handleError(error);}
  finally {$('save-uncertainty').disabled = !state.currentRule.definition_hash || state.currentRule.status !== 'present';}
});

loadDashboard().catch(handleError);
