"""Cosine retrieval over current vectors of one explicitly identified model."""
from __future__ import annotations

import json
import math

import numpy as np


class SemanticIndex:
    def __init__(self, conn, cast, semgrep, model_key=None):
        self.model = None
        self.hashes = {}
        self.cosines = {}
        self.invalid_vectors = 0
        self.coverage = {'CAST': 0, 'Semgrep': 0}
        if model_key:
            row = conn.execute('SELECT * FROM semantic_models WHERE model_key=?', (model_key,)).fetchone()
            if row is None:
                raise ValueError('Modèle sémantique inconnu ; consultez comparator semantic-status.')
        else:
            # Prefer the largest complete coverage in BOTH catalogues, with stable tie breaks.
            row = conn.execute('''SELECT m.* FROM semantic_models m JOIN (
                SELECT e.model_key,
                  SUM(d.source='CAST' AND e.title_vector_json IS NOT NULL AND e.description_vector_json IS NOT NULL) c,
                  SUM(d.source='Semgrep' AND e.title_vector_json IS NOT NULL AND e.description_vector_json IS NOT NULL) s,
                  SUM(d.source='CAST') any_c,SUM(d.source='Semgrep') any_s
                FROM semantic_embeddings e JOIN semantic_current_documents d
                  ON d.rule_key=e.rule_key AND d.content_hash=e.content_hash
                GROUP BY e.model_key
              ) cov ON cov.model_key=m.model_key WHERE cov.any_c>0 AND cov.any_s>0
              ORDER BY MIN(cov.c,cov.s) DESC,(cov.c+cov.s) DESC,m.model_key LIMIT 1''').fetchone()
        if row is None:
            return
        self.model = dict(row)
        dims = self.model['dimensions']
        catalogues = {'CAST': cast, 'Semgrep': semgrep}
        positions = {source: {r['rule_key']: i for i, r in enumerate(rules)} for source, rules in catalogues.items()}
        matrices = {field: {source: np.zeros((len(rules), dims), dtype=np.float32) for source, rules in catalogues.items()}
                    for field in ('title', 'description')}
        masks = {field: {source: np.zeros(len(rules), dtype=bool) for source, rules in catalogues.items()}
                 for field in matrices}
        rows = conn.execute('''SELECT e.*,d.source,d.has_title,d.has_description FROM semantic_embeddings e
            JOIN semantic_current_documents d ON d.rule_key=e.rule_key AND d.content_hash=e.content_hash
            WHERE e.model_key=?''', (self.model['model_key'],))
        for row in rows:
            source, key = row['source'], row['rule_key']
            if key not in positions.get(source, {}):
                continue
            index = positions[source][key]
            self.hashes[key] = row['content_hash']
            for field in matrices:
                raw = row[field + '_vector_json']
                if raw is None or not row['has_' + field]:
                    continue
                try:
                    values = json.loads(raw)
                    if not isinstance(values, list) or len(values) != dims or any(type(x) not in (int, float) or not math.isfinite(x) for x in values):
                        raise ValueError()
                    vector = np.asarray(values, dtype=np.float64)
                    scale = np.max(np.abs(vector))
                    if scale == 0:
                        raise ValueError()
                    vector /= scale
                    vector /= np.linalg.norm(vector)
                except (TypeError, ValueError, OverflowError):
                    self.invalid_vectors += 1
                    continue
                matrices[field][source][index] = vector
                masks[field][source][index] = True
        for field in matrices:
            cosine = np.clip(matrices[field]['CAST'] @ matrices[field]['Semgrep'].T, -1, 1)
            cosine[~masks[field]['CAST'], :] = np.nan
            cosine[:, ~masks[field]['Semgrep']] = np.nan
            self.cosines[field] = np.round(cosine, 6)
        self.coverage = {source: int(np.count_nonzero(masks['title'][source] & masks['description'][source]))
                         for source in catalogues}

    def pair(self, cast_index, semgrep_index, cast_key, semgrep_key):
        if not self.model:
            return None
        values = {field: round(float(matrix[cast_index, semgrep_index]), 6) for field, matrix in self.cosines.items()}
        values = {field: value for field, value in values.items() if math.isfinite(value)}
        if not values:
            return None
        weights = {'title': .4, 'description': .6}
        return {
            'origin': 'embedding_similarity', 'model_key': self.model['model_key'],
            'provider': self.model['provider'], 'model_name': self.model['model_name'],
            'model_revision': self.model['model_revision'], 'dimensions': self.model['dimensions'],
            'preprocessing': self.model['preprocessing'],
            'cast_content_hash': self.hashes[cast_key], 'semgrep_content_hash': self.hashes[semgrep_key],
            'title_cosine': values.get('title'), 'description_cosine': values.get('description'),
            'combined_cosine': round(sum(weights[f] * v for f, v in values.items()) / sum(weights[f] for f in values), 6),
            'complete': len(values) == 2,
        }

    def neighbors(self, cast_index, compatible, *, top_k, threshold, field_floor=.60):
        if not self.model:
            return set()
        titles, descriptions = self.cosines['title'][cast_index], self.cosines['description'][cast_index]
        combined = .4 * titles + .6 * descriptions
        eligible = np.flatnonzero(np.asarray(compatible) & (titles >= field_floor) & (descriptions >= field_floor)
                                 & (np.round(combined, 6) >= threshold))
        # Catalogue order is rule_key order, also providing deterministic tie breaks.
        ranked = sorted(eligible.tolist(), key=lambda i: (-round(float(combined[i]), 6), i))
        return set(ranked[:top_k])


def apply_semantic_score(score, factors, details, *, threshold=.75):
    if details is None:
        return score, factors
    factors = dict(factors)
    factors['baseline_score'] = score
    factors['semantic_details'] = details
    factors['semantic_similarity'] = details['combined_cosine']
    factors['semantic_threshold'] = threshold
    factors['semantic_field_floor'] = .60
    factors['method'] = 'hybrid-v3-semantic'
    factors['semantic_points'] = 0
    factors['lexical_points'] = 0
    for field in ('title', 'description'):
        old = factors[field + '_similarity']
        factors['lexical_' + field + '_similarity'] = old
        cosine = details[field + '_cosine']
        if cosine is None:
            factors['lexical_points'] += old
            continue
        # Preserve the 20-point text slot: half lexical, half semantic above a 0.5 floor.
        lexical = round(old / 2)
        semantic = round(10 * max(0, min(1, (cosine - .5) / .5)))
        factors[field + '_similarity'] = lexical + semantic
        factors['semantic_points'] += semantic
        factors['lexical_points'] += lexical
    factors['semantic_admission'] = bool(details['complete'] and details['combined_cosine'] >= threshold
        and details['title_cosine'] >= .60 and details['description_cosine'] >= .60)
    factors['limitations'] = 'Embedding proximity is an automatic hypothesis, not a probability or evidence of equivalent detection. Thresholds require expert calibration.'
    return min(100, sum(factors[k] for k in ('technical_compatibility', 'defect_references',
        'title_similarity', 'description_similarity', 'category_similarity'))), factors
