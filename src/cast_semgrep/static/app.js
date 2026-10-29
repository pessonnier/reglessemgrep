const $ = (id) => document.getElementById(id);
const state = {page: 1, pageSize: 30, total: 0, currentRule: null, currentMatch: null,
  mappingPage: 1, mappingPageSize: 20, mappingTotal: 0, view: 'correspondences', listOrigin: 'correspondences', comparisonReturn: 'correspondences'};
const levels = {unknown: 'Non évalué', low: 'Faible', medium: 'Moyen', high: 'Élevé'};
const uncertaintyLevels = {unknown: 'Non évaluée', low: 'Faible', medium: 'Moyenne', high: 'Élevée'};
const assessmentStatuses = {not_evaluated: 'À évaluer', stale: 'À réévaluer', expert_assessed: 'Avis expert enregistré'};
const decisions = {equivalent: 'Équivalent selon l’expert', partial: 'Partiellement équivalent selon l’expert',
  complementary: 'Complémentaire selon l’expert', related: 'Apparenté selon l’expert', no_match: 'Sans correspondance selon l’expert',
  not_comparable: 'Non comparable selon l’expert', indeterminate: 'Indéterminé selon l’expert'};

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
  state.view = view;
  if (['correspondences', 'explorer'].includes(view)) state.listOrigin = view;
  const path = {correspondences: '/correspondances', explorer: '/regles', dashboard: '/statistiques', manual: '/association'}[view];
  if (path && location.pathname !== path) history.replaceState(null, '', path);
  for (const id of ['correspondences', 'dashboard', 'explorer', 'detail', 'comparison', 'manual']) $(id).classList.toggle('hidden', id !== view);
  $('nav-manual').classList.toggle('nav-active', view === 'manual' || (view === 'comparison' && state.comparisonReturn === 'manual'));
  $('nav-dashboard').classList.toggle('nav-active', view === 'dashboard');
  const parent = view === 'comparison' && state.comparisonReturn === 'manual' ? 'manual' : ['detail', 'comparison'].includes(view) ? state.listOrigin : view;
  $('nav-explorer').classList.toggle('nav-active', parent === 'explorer');
  $('nav-correspondences').classList.toggle('nav-active', parent === 'correspondences');
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
  syncCatalogFilters();
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
  if (!data.items.length) {
    const row = node('tr'); const cell = node('td', 'Aucune règle pour ces filtres. Réinitialisez-les pour retrouver le catalogue complet.');
    cell.colSpan = 7; row.append(cell); body.append(row);
  }
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
    row.addEventListener('click', () => openRule(rule.rule_key).catch(handleError));
    row.addEventListener('keydown', event => {if (event.key === 'Enter') openRule(rule.rule_key).catch(handleError);});
    body.append(row);
  });
}

async function openRule(key) {
  const rule = await request(`/api/rule?${new URLSearchParams({key})}`);
  state.currentRule = rule;
  $('back-to-explorer').textContent = state.listOrigin === 'correspondences' ? '← Retour aux correspondances CAST → Semgrep' : '← Retour à l’explorateur';
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
    $('uncertainty-examples-editor').replaceChildren();
    const u = rule.uncertainty;
    if (u.status === 'expert_assessed') {
      for (const key of ['uncertainty_level', 'false_positive_risk', 'false_negative_risk', 'scope', 'rationale', 'evidence']) {
        $('uncertainty-form').elements[key].value = u[key] || '';
      }
      (u.code_examples || []).forEach(example => addCodeEditor('uncertainty-examples-editor', example));
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
      renderCodeExamples(entry, item.code_examples);
      history.append(entry);
    });
  }
  await loadMatches(key);
  $('other-results').replaceChildren();
  $('other-query').value = '';
  show('detail');
}

async function loadMatches(key, offset = 0) {
  const data = await request(`/api/matches?${new URLSearchParams({key, offset})}`);
  const target = $('matches');
  if (offset === 0) target.replaceChildren();
  else target.querySelector('.load-more')?.remove();
  if (!data.items.length) target.append(node('p', 'Aucun candidat identifié pour cette règle.', 'muted'));
  data.items.forEach(match => {
    const block = node('div', '', 'match'); block.tabIndex = 0;
    block.append(node('strong', match.other_title || match.other_id));
    block.append(node('div', `${match.other_id} · Classement ${match.score}/100 · ${decisions[match.expert_decision] || (match.manual_association ? 'Association manuelle · à examiner' : 'Candidat automatique · à examiner')}`, 'match-meta'));
    block.append(node('div', `${match.evidence_count} références sourcées`, 'match-meta'));
    const action = () => openMatch(match.cast_key, match.semgrep_key).catch(handleError);
    block.addEventListener('click', action);
    block.addEventListener('keydown', event => {if (event.key === 'Enter') action();});
    target.append(block);
  });
  const next = offset + data.items.length;
  if (next < data.total) {
    const more = node('button', `Afficher la suite (${next} sur ${data.total} paires)`, 'secondary load-more');
    more.addEventListener('click', () => loadMatches(key, next).catch(handleError));
    target.append(more);
  }
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
  for (const [label, key] of [['Correction', 'remediation'], ['Technologies', 'technologies'], ['Frameworks', 'frameworks'],
    ['Sévérité', 'severity'], ['Autres référentiels', 'standards'], ['OWASP d’origine', 'owasp_raw'],
    ['Origine de classification', 'classification_origin'], ['Version source', 'source_version'], ['Statut dans l’inventaire', 'status'],
    ['Empreinte de définition', 'definition_hash']]) field(target, label, rule[key]);
  const raw = node('details'); raw.append(node('summary', 'Contenu original archivé'), node('pre', rule.raw_content || 'Aucun contenu brut disponible.'));
  const all = node('details'); all.append(node('summary', 'Toutes les données et historiques disponibles'), node('pre', JSON.stringify(Object.fromEntries(Object.entries(rule).filter(([key]) => key !== 'raw_content')), null, 2)));
  target.append(raw, all);
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
  renderCodeExamples(target, u.code_examples);
  field(target, 'Confiance déclarée par Semgrep (métadonnée)', rule.source_confidence);
  target.append(node('p', 'La confiance déclarée par l’éditeur et les niveaux estimés ne sont pas des probabilités mesurées. Les tests de détection restent à mettre en place.', 'muted small'));
}

async function openMatch(castKey, semgrepKey) {
  if (state.view !== 'comparison') state.comparisonReturn = state.view;
  const data = await request(`/api/expert/comparison?${new URLSearchParams({cast_key: castKey, semgrep_key: semgrepKey})}`);
  const previous = state.currentMatch;
  if (!previous || previous.cast.rule_key !== castKey || previous.semgrep.rule_key !== semgrepKey) {
    $('review-form').reset();
    $('review-examples-editor').replaceChildren();
    $('review-status').textContent = '';
  }
  state.currentMatch = data;
  $('back-to-detail').textContent = state.comparisonReturn === 'manual' ? '← Modifier le choix des règles' : state.comparisonReturn === 'correspondences' ? '← Retour aux correspondances CAST → Semgrep' : '← Retour à la règle';
  const factors = data.candidate?.factors || {};
  $('manual-association').hidden = Boolean(data.candidate);
  $('review-form').hidden = !data.candidate;
  $('association-status').textContent = '';
  $('associate-pair').disabled = data.cast.status !== 'present' || data.semgrep.status !== 'present';
  const score = $('comparison-score'); score.replaceChildren();
  if (data.candidate) {
    if (factors.method === 'manual') {
      score.append(node('strong', 'Association manuelle · aucun classement automatique calculé'));
    } else {
      score.append(node('strong', `Score de classement ${data.candidate.score}/100 · ${factors.method || 'méthode inconnue'}`));
      score.append(node('div', `Langage ${factors.technical_compatibility ?? 0}/15 · Défaut référencé ${factors.defect_references ?? 0}/35 · Titre ${factors.title_similarity ?? 0}/20 · Description ${factors.description_similarity ?? 0}/20 · Catégorie ${factors.category_similarity ?? 0}/10`, 'small'));
      score.append(node('div', `Niveau de preuve : ${factors.evidence_level || 'inconnu'} · Préconditions : ${factors.precondition_alignment ?? 'non établies'} · Similarité sémantique : ${factors.semantic_similarity ?? 'non calculée'}`, 'small'));
      score.append(node('div', factors.limitations || '', 'small muted'));
    }
    if (factors.manual_association || factors.method === 'manual') score.append(node('p', 'Association manuelle · l’avis expert est enregistré séparément.', 'small'));
  } else score.append(node('strong', 'Comparaison libre · aucune association enregistrée'));
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
    block.append(node('strong', `${decisions[item.decision] || item.decision} · ${item.reviewer}`));
    block.append(node('div', item.created_at, 'small muted'));
    if (item.comment) block.append(node('p', item.comment));
    renderCodeExamples(block, item.code_examples);
    reviews.append(block);
  });
  show('comparison');
}

function syncCatalogFilters() {
  const source = $('filters').elements.source.value;
  for (const label of document.querySelectorAll('.semgrep-filter')) {
    const select = label.querySelector('select');
    label.hidden = source !== 'Semgrep';
    select.disabled = source !== 'Semgrep';
    if (source !== 'Semgrep') select.value = '';
  }
  $('catalog-context').textContent = source === 'CAST' ? 'Catalogue CAST. Ouvrez une règle pour consulter ses candidats Semgrep, ou utilisez la vue CAST → Semgrep.' :
    source === 'Semgrep' ? 'Catalogue Semgrep. Les filtres d’incertitude s’appliquent à ces règles.' : 'Catalogues CAST et Semgrep. Sélectionnez Semgrep pour filtrer ses évaluations d’incertitude.';
}

async function openCatalog(source = 'CAST') {
  $('filters').reset();
  $('filters').elements.source.value = source;
  state.page = 1;
  await loadRules();
  show('explorer');
}

async function returnToList() {
  if (state.listOrigin === 'correspondences') {await loadCorrespondences(); show('correspondences');}
  else {await loadRules(); show('explorer');}
}

async function loadCorrespondences() {
  await loadUnmatched();
  const params = new URLSearchParams(new FormData($('correspondence-filters')));
  params.set('page', state.mappingPage); params.set('page_size', state.mappingPageSize);
  const data = await request(`/api/correspondences?${params}`);
  state.mappingTotal = data.total;
  if (state.mappingPage > 1 && !data.items.length) {
    state.mappingPage = Math.max(1, Math.ceil(data.total / state.mappingPageSize));
    return loadCorrespondences();
  }
  const summary = data.summary;
  const metrics = $('correspondence-metrics'); metrics.replaceChildren();
  for (const [label, count, filter] of [
    ['Règles CAST', summary.cast_count, ''], ['Avec candidats Semgrep', summary.with_candidates, 'with_candidates'],
    ['Sans candidat identifié', summary.without_candidates, 'without_candidates'],
    ['Avec avis expert « équivalent »', summary.with_expert_equivalent, 'expert_equivalent']
  ]) {
    const button = node('button', '', 'metric mapping-metric');
    button.append(node('span', label), node('strong', Number(count).toLocaleString('fr-FR')));
    button.addEventListener('click', () => {
      $('correspondence-filters').elements.status.value = filter;
      state.mappingPage = 1; loadCorrespondences().catch(handleError);
    });
    metrics.append(button);
  }
  $('correspondence-count').textContent = `${Number(data.total).toLocaleString('fr-FR')} règle${data.total === 1 ? '' : 's'} CAST · correspondances regroupées par règle`;
  $('correspondence-page').textContent = `Page ${data.page} / ${Math.max(1, Math.ceil(data.total/state.mappingPageSize))}`;
  $('correspondence-prev').disabled = data.page <= 1;
  $('correspondence-next').disabled = data.page * state.mappingPageSize >= data.total;
  const list = $('correspondence-list'); list.replaceChildren();
  if (!data.items.length) list.append(node('p', 'Aucune règle CAST pour ces critères. Réinitialisez la recherche ou le filtre de correspondance.', 'empty-mapping'));
  for (const cast of data.items) {
    const row = node('article', '', 'mapping-row');
    const left = node('div', '', 'mapping-cast');
    left.append(node('span', `CAST ${cast.rule_id}`, 'source-tag cast'), node('h2', cast.title || cast.rule_id));
    left.append(node('p', cast.languages.join(', ') || 'Langage non renseigné', 'small muted'));
    if (cast.cwe.length) left.append(node('p', cast.cwe.join(', '), 'small muted'));
    const open = node('button', cast.candidate_count ? `Ouvrir la règle et ses ${cast.candidate_count} paires` : 'Ouvrir la règle CAST', 'secondary');
    open.addEventListener('click', () => openRule(cast.rule_key).catch(handleError));
    left.append(open, manualLink({cast_key: cast.rule_key}));
    const right = node('div', '', 'mapping-semgrep');
    if (!cast.matches.length) {
      right.append(node('strong', 'Aucun candidat Semgrep identifié'), node('p', 'Vous pouvez ouvrir la règle CAST et ajouter une paire à examiner.', 'small muted'));
    }
    for (const match of cast.matches) {
      const card = node('div', '', 'mapping-pair');
      const title = node('button', match.title || match.rule_id, 'pair-title');
      title.addEventListener('click', () => openMatch(cast.rule_key, match.semgrep_key).catch(handleError));
      card.append(title);
      card.append(node('p', `${match.rule_id} · ${match.languages.join(', ') || 'Langage non renseigné'}`, 'small mono muted'));
      card.append(node('span', decisions[match.expert_decision] || (match.manual_association ? 'Association manuelle · à examiner' : 'Candidat automatique · à examiner'), `decision ${match.expert_decision === 'equivalent' ? 'expert-equivalent' : ''}`));
      card.append(node('p', `Classement ${match.score}/100 · Incertitude Semgrep : ${uncertaintyLevels[match.uncertainty_level] || 'Non évaluée'}`, 'small muted'));
      const compare = node('button', 'Comparer CAST et Semgrep', 'secondary');
      compare.addEventListener('click', () => openMatch(cast.rule_key, match.semgrep_key).catch(handleError));
      card.append(compare); right.append(card);
    }
    if (cast.candidate_count > cast.matches.length) right.append(node('p', `${cast.matches.length} paires affichées sur ${cast.candidate_count}. Ouvrez la règle CAST pour toutes les consulter.`, 'small muted'));
    row.append(left, right); list.append(row);
  }
}

const exampleKinds = {vulnerable: 'Vulnérable / non conforme', safe: 'Corrigé / conforme', boundary: 'Cas limite', other: 'Autre exemple'};

function addCodeEditor(containerId, example = {}) {
  const container = $(containerId);
  if (container.children.length >= 10) {handleError(new Error('Maximum 10 exemples par avis.')); return;}
  const block = node('fieldset', '', 'code-editor');
  block.append(node('legend', 'Exemple de code'));
  for (const [key, labelText, tag, max] of [
    ['title', 'Titre de l’exemple', 'input', 160], ['language', 'Langage', 'input', 80],
    ['kind', 'Type de cas', 'select', 0], ['code', 'Code', 'textarea', 20000],
    ['explanation', 'Résultat attendu et justification', 'textarea', 3000]
  ]) {
    const label = node('label', labelText);
    const input = node(tag, null);
    input.dataset.field = key;
    if (max) input.maxLength = max;
    if (key === 'kind') {
      for (const [value, text] of Object.entries(exampleKinds)) {
        const option = node('option', text); option.value = value; input.append(option);
      }
    }
    if (key === 'code') {input.required = true; input.rows = 9; input.spellcheck = false; input.className = 'code-input';}
    if (key === 'explanation') input.rows = 3;
    input.value = example[key] || (key === 'kind' ? 'other' : '');
    label.append(input); block.append(label);
  }
  const remove = node('button', 'Retirer cet exemple', 'secondary'); remove.type = 'button';
  remove.addEventListener('click', () => block.remove());
  block.append(remove); container.append(block);
}

function readCodeExamples(containerId) {
  return [...$(containerId).children].map(block => Object.fromEntries(
    [...block.querySelectorAll('[data-field]')].map(input => [input.dataset.field, input.value])
  ));
}

function renderCodeExamples(target, examples = []) {
  if (!examples.length) return;
  const section = node('div', '', 'code-examples');
  section.append(node('h3', 'Exemples de code de l’expert'));
  section.append(node('p', 'Illustrations déclarées par l’expert · non exécutées', 'small muted'));
  examples.forEach((example, index) => {
    const block = node('section', '', 'code-example');
    block.append(node('h4', example.title || `Exemple ${index + 1}`));
    block.append(node('p', `${exampleKinds[example.kind] || 'Autre exemple'} · ${example.language || 'Langage non précisé'}`, 'small muted'));
    const pre = node('pre', null); pre.append(node('code', example.code)); block.append(pre);
    if (example.explanation) block.append(node('p', example.explanation));
    section.append(block);
  });
  target.append(section);
}

function handleError(error) { window.alert(error.message || String(error)); }

$('back-to-explorer').addEventListener('click', () => returnToList().catch(handleError));
$('back-to-detail').addEventListener('click', () => {
  if (state.comparisonReturn === 'manual') show('manual');
  else if (state.comparisonReturn === 'correspondences') loadCorrespondences().then(() => show('correspondences')).catch(handleError);
  else if (state.currentRule) openRule(state.currentRule.rule_key).catch(handleError);
  else returnToList().catch(handleError);
});
$('add-review-example').addEventListener('click', () => addCodeEditor('review-examples-editor'));
$('add-uncertainty-example').addEventListener('click', () => addCodeEditor('uncertainty-examples-editor'));
$('filters').elements.source.addEventListener('change', () => {
  openCatalog($('filters').elements.source.value).catch(handleError);
});
$('reset-catalog').addEventListener('click', () => openCatalog($('filters').elements.source.value).catch(handleError));
$('correspondence-filters').addEventListener('submit', event => {event.preventDefault(); state.mappingPage = 1; loadCorrespondences().catch(handleError);});
$('reset-correspondences').addEventListener('click', () => {$('correspondence-filters').reset(); state.mappingPage = 1; loadCorrespondences().catch(handleError);});
$('correspondence-prev').addEventListener('click', () => {if (state.mappingPage > 1) {state.mappingPage--; loadCorrespondences().catch(handleError);}});
$('correspondence-next').addEventListener('click', () => {if (state.mappingPage * state.mappingPageSize < state.mappingTotal) {state.mappingPage++; loadCorrespondences().catch(handleError);}});
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
  $('save-review').disabled = true;
  try {
    const form = new FormData(event.target);
    const data = state.currentMatch;
    await request('/api/reviews', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
      cast_key: data.cast.rule_key, semgrep_key: data.semgrep.rule_key,
      reviewer: form.get('reviewer'), decision: form.get('decision'), comment: form.get('comment'),
      code_examples: readCodeExamples('review-examples-editor')
    })});
    event.target.reset();
    $('review-examples-editor').replaceChildren();
    await openMatch(data.cast.rule_key, data.semgrep.rule_key);
    $('review-status').textContent = 'Avis et exemples de code enregistrés.';
  } catch (error) {handleError(error);}
  finally {$('save-review').disabled = false;}
});

$('uncertainty-form').addEventListener('submit', async event => {
  event.preventDefault();
  const rule = state.currentRule;
  const form = event.target;
  $('save-uncertainty').disabled = true;
  try {
    const payload = Object.fromEntries(new FormData(form));
    payload.code_examples = readCodeExamples('uncertainty-examples-editor');
    Object.assign(payload, {rule_key: rule.rule_key, source_version: rule.source_version, definition_hash: rule.definition_hash});
    await request('/api/uncertainty-assessments', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
    await openRule(rule.rule_key);
    $('uncertainty-form-status').textContent = 'Évaluation enregistrée dans l’historique.';
  } catch (error) {handleError(error);}
  finally {$('save-uncertainty').disabled = !state.currentRule.definition_hash || state.currentRule.status !== 'present';}
});

const manualState = {cast: {page: 1, key: ''}, semgrep: {page: 1, key: ''}};
let unmatchedPage = 1;
function manualLink(params) {
  const link = node('a', 'Choisir une paire manuellement →', 'manual-link');
  link.href = `/association?${new URLSearchParams(params)}`;
  return link;
}
async function loadUnmatched() {
  const params = new URLSearchParams(new FormData($('unmatched-filters')));
  params.set('page', unmatchedPage); params.set('page_size', 20);
  const data = await request(`/api/expert/semgrep-unmatched?${params}`);
  if (unmatchedPage > 1 && !data.items.length) {unmatchedPage = Math.max(1, Math.ceil(data.total / 20)); return loadUnmatched();}
  $('unmatched-count').textContent = `${data.total.toLocaleString('fr-FR')} règles Semgrep sans candidat CAST`;
  $('unmatched-page').textContent = `Page ${data.page} / ${Math.max(1, Math.ceil(data.total / 20))}`;
  $('unmatched-prev').disabled = data.page <= 1;
  $('unmatched-next').disabled = data.page * 20 >= data.total;
  const list = $('unmatched-list'); list.replaceChildren();
  if (!data.items.length) list.append(node('p', 'Aucune règle Semgrep sans candidat pour ces critères.', 'muted'));
  for (const rule of data.items) {
    const card = node('article', '', 'mapping-pair');
    card.append(node('h3', rule.title || rule.rule_id), node('p', `${rule.rule_id} · ${rule.languages.join(', ')}`, 'small mono'));
    card.append(node('p', `Incertitude : ${uncertaintyLevels[rule.uncertainty.uncertainty_level]}`, 'small'));
    const open = node('button', 'Ouvrir la règle Semgrep', 'secondary');
    open.addEventListener('click', () => openRule(rule.rule_key).catch(handleError));
    card.append(open, manualLink({semgrep_key: rule.rule_key})); list.append(card);
  }
}
function syncManualPreview() {
  $('manual-preview').disabled = !manualState.cast.key || !manualState.semgrep.key;
}
async function searchManual(side) {
  const selection = manualState[side];
  const revision = selection.revision = (selection.revision || 0) + 1;
  $(`manual-${side}-select`).replaceChildren();
  selection.key = ''; syncManualPreview();
  $(`manual-${side}-selected`).textContent = '';
  const params = new URLSearchParams(new FormData($(`manual-${side}-search`)));
  params.set('source', side === 'cast' ? 'CAST' : 'Semgrep');
  params.set('page', selection.page); params.set('page_size', 20);
  const data = await request(`/api/expert/rules?${params}`);
  if (selection.revision !== revision) return;
  const select = $(`manual-${side}-select`); select.replaceChildren();
  for (const rule of data.items) {const option = node('option', `${rule.rule_id} — ${rule.title || ''}`); option.value = rule.rule_key; select.append(option);}
  select.selectedIndex = -1;
  $(`manual-${side}-count`).textContent = `${data.total} règles · page ${data.page} / ${Math.max(1, Math.ceil(data.total/20))}`;
  $(`manual-${side}-prev`).disabled = data.page <= 1;
  $(`manual-${side}-next`).disabled = data.page * 20 >= data.total;
}
async function initManual() {
  show('manual');
  const params = new URLSearchParams(location.search);
  for (const side of ['cast', 'semgrep']) {
    await searchManual(side);
    const key = params.get(`${side}_key`);
    if (key) {
      const rule = await request(`/api/expert/rule?${new URLSearchParams({key})}`);
      if (rule.source !== (side === 'cast' ? 'CAST' : 'Semgrep') || rule.status !== 'present') throw new Error('La règle présélectionnée n’est pas disponible. Choisissez une règle du catalogue.');
      const select = $(`manual-${side}-select`);
      if (![...select.options].some(option => option.value === key)) {const option = node('option', `${rule.rule_id} — ${rule.title || ''}`); option.value = key; select.prepend(option);}
      select.value = key; manualState[side].key = key;
      $(`manual-${side}-selected`).textContent = `Sélection : ${rule.rule_id} — ${rule.title || ''}`;
    }
  }
  syncManualPreview();
}
for (const side of ['cast', 'semgrep']) {
  $(`manual-${side}-search`).addEventListener('submit', event => {event.preventDefault(); manualState[side].page = 1; searchManual(side).catch(handleError);});
  for (const [action, delta] of [['prev', -1], ['next', 1]]) $(`manual-${side}-${action}`).addEventListener('click', () => {
    manualState[side].page += delta; searchManual(side).catch(handleError);
  });
  $(`manual-${side}-select`).addEventListener('change', event => {
    manualState[side].key = event.target.value;
    $(`manual-${side}-selected`).textContent = `Sélection : ${event.target.selectedOptions[0]?.textContent || ''}`;
    syncManualPreview();
  });
}
$('manual-preview').addEventListener('click', () => openMatch(manualState.cast.key, manualState.semgrep.key).catch(handleError));
$('associate-pair').addEventListener('click', async () => {
  $('associate-pair').disabled = true;
  try {
    const pair = {cast_key: state.currentMatch.cast.rule_key, semgrep_key: state.currentMatch.semgrep.rule_key};
    await request('/api/expert/associations', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(pair)});
    await openMatch(pair.cast_key, pair.semgrep_key);
    $('review-status').textContent = 'Association enregistrée. Vous pouvez ajouter votre avis expert ci-dessus.';
    $('review-form').scrollIntoView({behavior: 'smooth', block: 'center'});
  } catch (error) {handleError(error);}
  finally {$('associate-pair').disabled = false;}
});
$('unmatched-filters').addEventListener('submit', event => {event.preventDefault(); unmatchedPage = 1; loadUnmatched().catch(handleError);});
$('unmatched-reset').addEventListener('click', () => {$('unmatched-filters').reset(); unmatchedPage = 1; loadUnmatched().catch(handleError);});
$('unmatched-prev').addEventListener('click', () => {unmatchedPage--; loadUnmatched().catch(handleError);});
$('unmatched-next').addEventListener('click', () => {unmatchedPage++; loadUnmatched().catch(handleError);});

if (location.pathname === '/association') initManual().catch(handleError);
else if (location.pathname === '/regles') openCatalog('CAST').catch(handleError);
else if (location.pathname === '/statistiques') loadDashboard().then(() => show('dashboard')).catch(handleError);
else loadCorrespondences().then(() => show('correspondences')).catch(handleError);
