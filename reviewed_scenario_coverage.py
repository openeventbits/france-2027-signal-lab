"""Manually invoked, read-only reviewed historical scenario coverage diagnostic.

The historical API and the separately selected current CLI review authenticate every input.
No fetching, extraction, ingestion, repinning, event-ID generation or file writes.
"""
from __future__ import annotations

import argparse
import collections
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
from html.parser import HTMLParser
import importlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

__all__ = ["assess_coverage", "CoverageDiagnosticError"]
_ROOT = Path(__file__).resolve().parent
_MANIFEST_PATH = _ROOT / "fr27_reviewed_scenario_manifest.json"
_PIN_PATH = _ROOT / "fr27_reviewed_scenario_pin.json"
_PIN_SHA256 = "beb40745a83348562dd1a75835a3865667fbad09560f9def4253166f8218f469"
SCHEMA = "fr27-reviewed-scenario-coverage/1"
ROUNDS = ("first_round", "second_round")
_CURRENT_REVIEW_PATH = _ROOT / 'fr27_commission_scenario_coverage_review_20261028.json'
_CURRENT_REVIEW_SHA256 = 'ab12b29dab779b33a9ce630b4f67d334b0ef3cc83423b1b3f6204e12faf93e7a'
_CURRENT_PUBLICATION_ROOT = _ROOT
_CURRENT_SCHEMA = 'fr27-commission-scenario-coverage-review/1'


class CoverageDiagnosticError(ValueError):
    """Authenticated assessment cannot proceed; inspect code before any claims."""
    def __init__(self, message, *, code="REVIEW_REQUIRED", details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read_json(path):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise CoverageDiagnosticError('Duplicate JSON key: ' + key)
            out[key] = value
        return out
    return json.loads(Path(path).read_text(encoding='utf8'), object_pairs_hook=unique,
                      parse_constant=lambda s: (_ for _ in ()).throw(CoverageDiagnosticError('Nonfinite JSON: ' + s)))


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int, Decimal)):
        raise CoverageDiagnosticError('Expected a finite numerical score')
    result = Decimal(str(value))
    if not result.is_finite() or not 0 <= result <= 100:
        raise CoverageDiagnosticError('Score outside 0..100')
    return result


def _require(condition, message):
    if not condition:
        raise CoverageDiagnosticError(message)


class _IdentityRules:
    """Use the existing finite rules, gated by this packet's authenticated scope."""
    def __init__(self):
        self.migration = importlib.import_module("poll_migration")
        contract = importlib.import_module("poll_contract")
        for module in (self.migration, contract):
            _require(Path(module.__file__).resolve().parent == _ROOT,
                     "Identity module loaded from another checkout")
        self.normalize = contract.normalize_identity

    def candidate(self, name):
        return self.migration.candidate_identity(name)

    def institute(self, label, survey, packet):
        reviews = packet['identity_rules']['institute_alias_reviews']
        allowed = [r for r in reviews if survey['survey_id'] in r['notice_ids']
                   and r['institute_id'] == survey['institute_id']
                   and label in r['labels']]
        if len(allowed) != 1:
            return None
        return self.migration.pollster_identity(label)


def _source_vector(scenario, rules):
    result = {}
    for row in scenario['rows']:
        try:
            key = rules.candidate(row['published_name'])
        except ValueError as exc:
            raise CoverageDiagnosticError(str(exc)) from exc
        _require(row['identity_id'] == key, 'Candidate identity mapping conflict')
        _require(key not in result, 'Duplicate canonical candidate/ballot option')
        published = row['result']
        kind, literal = published['kind'], published['literal']
        _require(isinstance(literal, str) and literal.strip(), 'Missing source literal')
        if kind == 'exact':
            _require(set(published) == {'kind', 'literal', 'percent'}, 'Exact result fields')
            value = _number(published['percent'])
            try:
                literal_value = Decimal(literal.strip().removesuffix('%').replace(',', '.'))
            except InvalidOperation as exc:
                raise CoverageDiagnosticError('Invalid exact source literal') from exc
            _require(value == literal_value, 'Exact literal/value contradiction')
            result[key] = value
        elif kind == 'strict_upper_bound':
            _require(set(published) == {'kind', 'literal', 'upper_percent'}, 'A bound must not carry an exact score')
            bound = _number(published['upper_percent'])
            _require(re.fullmatch(r'<\s*\d+(?:[.,]\d+)?\s*%?', literal) is not None, 'Invalid bound literal')
            _require(Decimal(literal.replace('<', '').replace('%', '').replace(',', '.').strip()) == bound,
                    'Bound literal/limit contradiction')
            result[key] = None
        elif kind in ('source_dash', 'not_published', 'not_tested'):
            fields = {'kind', 'literal', 'numeric_meaning'} if kind == 'source_dash' else {'kind', 'literal'}
            _require(set(published) == fields, 'Non-exact result cannot carry a _number')
            if kind == 'source_dash':
                _require(literal in ('-', '–', '—'), 'Invalid literal dash')
                _require(published['numeric_meaning'] == 'unconfirmed', 'Dash meaning must remain unconfirmed')
            result[key] = None
        else:
            raise CoverageDiagnosticError('Unreviewed result kind: ' + str(kind))
    _require(bool(result), 'Empty scenario')
    if scenario['round'] == 'second_round':
        _require(len(result) == 2, 'Runoff requires exactly two ballot options')
    return result


def _validate_manifest(packet, rules):
    _require(packet['schema_version'] == SCHEMA, 'Unsupported manifest schema')
    documents = {d['document_id']: d for d in packet['documents']}
    _require(len(documents) == len(packet['documents']), 'Duplicate document ID')
    survey_ids, scenario_ids, bindings = set(), set(), set()
    for d in documents.values():
        _require(re.fullmatch(r'[0-9a-f]{64}', d['sha256']) is not None, 'Invalid document hash')
        _require(Path(d['evidence_key']).name == d['evidence_key'] and '\\' not in d['evidence_key'], 'Evidence key must be a filename')
        _require(urlparse(d['url']).scheme in ('http', 'https'), 'Original source URL required')
        _require(d['reviewed'] is True, 'Document not reviewed')
    for survey in packet['surveys']:
        sid = survey['survey_id']
        _require(sid not in survey_ids, 'Duplicate survey ID')
        survey_ids.add(sid)
        d = documents[survey['document_id']]
        _require(d['official_notice_id'] == survey['official_notice_id'] == sid, 'Notice/source identity conflict')
        _require(rules.institute(survey['institute'], survey, packet) == survey['institute_id'], 'Unauthenticated institute mapping')
        _require(bool(survey['commissioner']) and bool(survey['population']['population_id']), 'Commissioner/population required')
        for value in survey['fieldwork'].values():
            _require(date.fromisoformat(value).isoformat() == value, 'Invalid fieldwork date')
        _require(survey['fieldwork']['start'] <= survey['fieldwork']['end'], 'Invalid fieldwork range')
        _require(d['url'] in survey['accepted_source_urls'], 'Official source relationship missing')
        for key, count in survey['respondent_bases'].items():
            _require(isinstance(count, int) and not isinstance(count, bool) and count > 0, 'Invalid respondent base: ' + key)
        bases = survey['respondent_bases']
        for child, parent in (('registered_voters', 'adults'), ('certain_to_vote', 'registered_voters'),
                              ('lgbt_adults', 'national_parent_adults'), ('registered_lgbt', 'lgbt_adults')):
            if child in bases and parent in bases:
                _require(bases[child] <= bases[parent], 'Contradictory respondent-base scopes')
        evidence = [survey['method_evidence']]
        for sc in survey['scenarios']:
            _require(sc['scenario_id'] not in scenario_ids, 'Duplicate scenario ID')
            scenario_ids.add(sc['scenario_id'])
            _require(sc['round'] in ROUNDS, 'Invalid round')
            _source_vector(sc, rules)
            evidence.append(sc['table_evidence'])
            for count in sc['respondent_bases'].values():
                _require(isinstance(count, int) and not isinstance(count, bool) and count > 0, 'Invalid scenario base')
                parent = bases.get('certain_to_vote', bases.get('registered_voters', bases.get('registered_lgbt')))
                _require(parent is not None and count <= parent, 'Scenario base exceeds its reviewed parent')
            binding = sc['reviewed_event_binding']
            if binding:
                _require(binding['event_id'] not in bindings, 'One observation cannot cover two source scenarios')
                bindings.add(binding['event_id'])
                for key in ('event_id', 'event_object_sha256'):
                    _require(re.fullmatch(r'[0-9a-f]{64}', binding[key]) is not None, 'Invalid reviewed binding')
                bridge = binding['legacy_metadata_bridge']
                _require(bridge['commissioner'] == survey['commissioner'], 'Bridge commissioner conflict')
                _require(bridge['population_id'] == survey['population']['population_id'], 'Bridge population conflict')
                _require(bridge['reported_sample_base'] in survey['respondent_bases'], 'Unreviewed sample scope bridge')
                _require(binding['source_url'] in survey['accepted_source_urls'], 'Binding source conflict')
                _require(bridge['evidence'] == [survey['method_evidence'], sc['table_evidence']], 'Bridge evidence conflict')
                _require(bool(bridge['rationale']), 'Bridge rationale required')
        for ref in evidence:
            _require(ref['document_id'] == survey['document_id'], 'Cross-survey evidence conflict')
            _require(isinstance(ref['page'], int) and not isinstance(ref['page'], bool) and ref['page'] > 0, 'Source page required')
        counts = collections.Counter(sc['round'] for sc in survey['scenarios'])
        if survey['inventory_review']['complete']:
            _require(all(counts[r] == survey['inventory_review']['expected_by_round'][r] for r in ROUNDS), 'Incomplete reviewed inventory')


def _document_states(packet, evidence_root):
    states = {}
    for d in packet['documents']:
        try:
            actual = _file_sha256(Path(evidence_root) / d['evidence_key'])
            state = 'VERIFIED' if actual == d['sha256'] else 'HASH_MISMATCH'
        except OSError:
            actual, state = None, 'UNAVAILABLE'
        states[d['document_id']] = {'state': state, 'actual_sha256': actual, 'expected_sha256': d['sha256']}
    return states


def _inspect_candidate(packet, survey, scenario, event, rules):
    """Return all conflicts, including conflicts hidden by a legacy null bridge."""
    reasons = []
    if rules.institute(event.get('pollster'), survey, packet) != survey['institute_id']:
        reasons.append('INSTITUTE_IDENTITY_CONFLICT')
    if (event.get('fieldwork_start'), event.get('fieldwork_end')) != (survey['fieldwork']['start'], survey['fieldwork']['end']):
        reasons.append('FIELDWORK_CONFLICT')
    if event.get('round') != scenario['round']:
        reasons.append('ROUND_CONFLICT')
    if event.get('commissioner') is not None and rules.normalize(event['commissioner']) != rules.normalize(survey['commissioner']):
        reasons.append('COMMISSIONER_CONFLICT')
    if event.get('source_url') not in survey['accepted_source_urls']:
        reasons.append('SOURCE_RELATIONSHIP_CONFLICT')
    for key in ('official_notice_id', 'reviewed_notice_id'):
        if event.get(key) is not None and event[key] != survey['official_notice_id']:
            reasons.append('OFFICIAL_NOTICE_CONFLICT')
    if event.get('publication_date') is not None and survey['publication_date'] is not None and event['publication_date'] != survey['publication_date']:
        reasons.append('PUBLICATION_DATE_CONFLICT')
    if event.get('population_id') is not None and event['population_id'] != survey['population']['population_id']:
        reasons.append('POPULATION_CONFLICT')
    # A free-text population assertion is not silently normalized into this ID.
    if event.get('survey_population') is not None and event['survey_population'] != survey['population']['description']:
        reasons.append('POPULATION_CONFLICT')
    expected_bases = survey['respondent_bases'] | scenario['respondent_bases']
    supplied = event.get('respondent_bases')
    if supplied is not None:
        if not isinstance(supplied, dict) or any(key not in expected_bases or isinstance(count, bool) or count != expected_bases[key] for key, count in supplied.items()):
            reasons.append('RESPONDENT_BASE_CONFLICT')
    expected = _source_vector(scenario, rules)
    observed = {}
    try:
        for row in event['candidates']:
            key = rules.candidate(row['name'])
            if key in observed:
                reasons.append('DUPLICATE_CANDIDATE_IDENTITY')
            observed[key] = _number(row['score'])
    except (ValueError, KeyError, TypeError):
        reasons.append('INVALID_CANDIDATE_OR_SCORE')
    if set(expected) != set(observed):
        reasons.append('CANDIDATE_CONFIGURATION_CONFLICT')
    if any(value is None for value in expected.values()):
        reasons.append('NON_EXACT_SOURCE_CANNOT_VERIFY_NUMERIC_VECTOR')
    elif expected != observed:
        reasons.append('EXACT_SCORE_VECTOR_CONFLICT')
    binding = scenario['reviewed_event_binding']
    bound = binding and binding['event_id'] == event.get('event_id')
    if bound:
        bridge = binding['legacy_metadata_bridge']
        base = bridge['reported_sample_base']
        if event.get('sample_size') != survey['respondent_bases'][base]:
            reasons.append('RESPONDENT_BASE_CONFLICT')
        if event.get('sample_scope') not in ('reported', base):
            reasons.append('RESPONDENT_SCOPE_CONFLICT')
        if event.get('source_url') != binding['source_url']:
            reasons.append('REVIEWED_SOURCE_BINDING_CONFLICT')
        if _digest(event) != binding['event_object_sha256']:
            reasons.append('REVIEWED_OBJECT_CHANGED')
    else:
        reasons.append('REVIEWED_BINDING_REQUIRED')
        if event.get('sample_size') not in survey['respondent_bases'].values():
            reasons.append('RESPONDENT_BASE_CONFLICT')
    return sorted(set(reasons))


def _reconcile(packet, events, states, rules):
    """Pure evaluation; event IDs are read and returned, never generated."""
    _validate_manifest(packet, rules)
    by_id = {e['event_id']: e for e in events}
    _require(len(by_id) == len(events), 'Duplicate existing event IDs')
    reviewed_objects = {sc['reviewed_event_binding']['event_id']: sc['reviewed_event_binding']['event_object_sha256']
                        for s in packet['surveys'] for sc in s['scenarios'] if sc['reviewed_event_binding']}
    studies = []
    for survey in sorted(packet['surveys'], key=lambda s: s['survey_id']):
        source_state = states[survey['document_id']]['state']
        scenarios = []
        for sc in sorted(survey['scenarios'], key=lambda s: s['scenario_id']):
            binding = sc['reviewed_event_binding']
            expected = _source_vector(sc, rules)
            rejected, plausible, verified = [], [], []
            for event in events:
                # Dates/institute select inspection candidates, never prove identity.
                seed = (rules.institute(event.get('pollster'), survey, packet) == survey['institute_id']
                        and event.get('fieldwork_start') == survey['fieldwork']['start']
                        and event.get('fieldwork_end') == survey['fieldwork']['end']
                        and event.get('round') == sc['round'])
                explicit = binding and event['event_id'] == binding['event_id']
                notice_claim = event.get('source_url') == next(d['url'] for d in packet['documents'] if d['document_id'] == survey['document_id'])
                if not (seed or explicit or (notice_claim and event.get('round') == sc['round'])):
                    continue
                reasons = _inspect_candidate(packet, survey, sc, event, rules)
                if not reasons:
                    verified.append(event['event_id'])
                else:
                    rejected.append({'event_id': event['event_id'], 'reasons': reasons})
                    # Unbound exact plausible source relationships _require review;
                    # same dates with another commissioning source do not count.
                    hard = set(reasons) - {'REVIEWED_BINDING_REQUIRED'}
                    if not hard or (event.get('source_url') in survey['accepted_source_urls']
                                    and not ({'INVALID_CANDIDATE_OR_SCORE', 'CANDIDATE_CONFIGURATION_CONFLICT'} & set(reasons))
                                    and 'NON_EXACT_SOURCE_CANNOT_VERIFY_NUMERIC_VECTOR' in reasons):
                        plausible.append(event['event_id'])
                    elif (event.get('source_url') in survey['accepted_source_urls']
                          and event['event_id'] not in survey['legacy_notice_event_claims']
                          and reviewed_objects.get(event['event_id']) != _digest(event)):
                        # An unexplained event claiming this source may be a
                        # damaged/partial representation. Do not turn it into
                        # a gap until the relationship has been reviewed.
                        plausible.append(event['event_id'])
            confidence = 'VERIFIED_PINNED_DOCUMENT'
            absence = False
            if source_state == 'UNAVAILABLE':
                status, rationale, confidence = 'UNVERIFIED', 'Original evidence or complete corpus inventory is unavailable/unpinned; no gap claim.', 'UNVERIFIED'
            elif source_state != 'VERIFIED':
                status, rationale, confidence = 'REVIEW_REQUIRED', 'Original source bytes contradict the reviewed document identity.', 'CONTRADICTED'
            elif binding:
                if verified == [binding['event_id']] and not plausible:
                    status, rationale = 'NUMERIC_VERIFIED', 'Full source configuration, exact vector and reviewed survey/event relationship verified.'
                else:
                    status, rationale = 'REVIEW_REQUIRED', 'A reviewed observation is absent, changed or contradicted; do not invent a replacement or gap.'
            elif plausible or not survey['inventory_review']['complete']:
                status, rationale = 'REVIEW_REQUIRED', 'Plausible unreviewed representation or incomplete source inventory; no confirmed gap.'
            else:
                # A misleading event claiming this very official source is kept
                # separate from a truly absent table, without double counting.
                wrong_claims = [r for r in rejected if r['event_id'] in survey['legacy_notice_event_claims']
                                and by_id[r['event_id']].get('source_url') in survey['accepted_source_urls']]
                status = 'MISATTRIBUTED' if wrong_claims else 'MISSING_CONFIRMED'
                absence = True
                rationale = 'Authenticated full table absent from the pinned complete numerical inventory.'
                if wrong_claims:
                    rationale += ' The retained notice-linked event has an incompatible configuration/vector.'
            scenarios.append({'scenario_id': sc['scenario_id'], 'round': sc['round'],
                              'source_page': sc['table_evidence']['page'], 'status': status,
                              'verified_event_id': verified[0] if status == 'NUMERIC_VERIFIED' else None,
                              'confirmed_absent_faithful_configuration': absence,
                              'source_identity_confidence': confidence,
                              'documentary_evidence_verified': source_state == 'VERIFIED',
                              'baseline_documentary_coverage': status == 'NUMERIC_VERIFIED',
                              'rationale': rationale,
                              'rejected_candidates': sorted(rejected, key=lambda r: r['event_id'])})
        claims = []
        for event_id in sorted(survey['legacy_notice_event_claims']):
            event = by_id.get(event_id)
            accepted = [s['scenario_id'] for s in scenarios if s['verified_event_id'] == event_id]
            diagnostics = sorted(set(reason for s in scenarios for r in s['rejected_candidates']
                                     if r['event_id'] == event_id for reason in r['reasons']))
            claim_state = ('UNVERIFIED' if source_state == 'UNAVAILABLE'
                           else 'REVIEW_REQUIRED' if source_state != 'VERIFIED'
                           else 'VERIFIED_SCENARIO_ONLY' if accepted
                           else 'REJECTED' if event else 'UNVERIFIED')
            claims.append({'event_id': event_id, 'state': claim_state,
                           'verified_scenario_ids': accepted, 'reasons': diagnostics})
        inventory_complete = survey['inventory_review']['complete']
        numeric = inventory_complete and all(s['status'] == 'NUMERIC_VERIFIED' for s in scenarios)
        studies.append({'survey_id': survey['survey_id'], 'commissioner': survey['commissioner'],
                        'source_identity_confidence': 'VERIFIED_PINNED_DOCUMENT' if source_state == 'VERIFIED' else source_state,
                        'numerically_complete': numeric,
                        'review_packet_documentary_complete': source_state == 'VERIFIED' and survey['inventory_review']['complete'],
                        'baseline_documentary_complete': inventory_complete and all(s['baseline_documentary_coverage'] for s in scenarios),
                        'coverage_state': 'COMPLETE' if numeric else 'INCOMPLETE_OR_REVIEW_REQUIRED',
                        'legacy_notice_claims': claims, 'scenarios': scenarios})
    flat = [s for study in studies for s in study['scenarios']]
    return {'schema_version': SCHEMA, 'review_id': packet['review_id'],
            'baseline_sha': packet['audited_baseline_sha'], 'manifest_sha256': _digest(packet),
            'corpus_authenticated': True, 'documents': states,
            'summary': {'surveys': len(studies), 'expected_scenarios': len(flat),
                        'status_counts': dict(sorted(collections.Counter(s['status'] for s in flat).items())),
                        'verified_by_round': {r: sum(s['round'] == r and s['status'] == 'NUMERIC_VERIFIED' for s in flat) for r in ROUNDS},
                        'confirmed_gaps_by_round': {r: sum(s['round'] == r and s['confirmed_absent_faithful_configuration'] for s in flat) for r in ROUNDS}},
            'surveys': studies}



def _load_review():
    pin = _read_json(_PIN_PATH)
    _require(_digest(pin) == _PIN_SHA256, "Reviewed authentication pin changed; explicit review required")
    _require(pin['schema_version'] == 'fr27-reviewed-scenario-pin/1', "Unsupported authentication pin")
    packet = _read_json(_MANIFEST_PATH)
    _require(_digest(packet) == pin['manifest_sha256'], "Reviewed scenario manifest changed; explicit review required")
    _require(packet['review_id'] == pin['review_id'] and packet['audited_baseline_sha'] == pin['baseline_sha'],
             "Reviewed source/baseline identity conflict")
    return packet, pin


def _corpus_identity(first, second):
    _require(isinstance(first, list) and isinstance(second, list), "Polling arrays required")
    ids = []
    for events, round_name in ((first, 'first_round'), (second, 'second_round')):
        for event in events:
            _require(isinstance(event, dict) and isinstance(event.get('event_id'), str)
                     and re.fullmatch(r'[0-9a-f]{64}', event['event_id']) is not None,
                     "Invalid historical event ID")
            _require(event.get('round') == round_name, "Polling collection/round conflict")
            ids.append(event['event_id'])
    _require(len(ids) == len(set(ids)), "Duplicate historical event ID")
    return {name: {'count': len(events), 'sha256': _digest(sorted(events, key=lambda e: e['event_id']))}
            for name, events in (('polls.json', first), ('second_round_polls.json', second))}


def _authenticate_corpus(directory, pin):
    first = _read_json(directory / 'polls.json')
    second = _read_json(directory / 'second_round_polls.json')['events']
    actual = _corpus_identity(first, second)
    if actual != pin['corpora']:
        raise CoverageDiagnosticError(
            "Historical coverage baseline attestation is stale; review the changed corpus. No coverage or absence claims emitted.",
            code='BASELINE_STALE', details={'reviewed_baseline_sha': pin['baseline_sha'],
                                          'expected_corpora': pin['corpora'], 'observed_corpora': actual})
    return first + second


def assess_coverage(evidence_dir, *, corpus_dir=None):
    """Authenticate reviewed inputs and assess only this historical five-study scope.

    Evidence bytes come from the operator's external cache; corpus_dir selects
    only data files, never code or review pins. No caller-supplied manifest,
    bypass flag, event array or pre-authenticated state is accepted. A changed
    corpus raises BASELINE_STALE before any coverage claim. Missing/changed PDF
    bytes return UNVERIFIED/REVIEW_REQUIRED for the affected study, never a gap.
    This function performs no writes, network access or automatic repinning.
    """
    try:
        packet, pin = _load_review()
        for name, expected in pin['identity_source_sha256'].items():
            source = (_ROOT / name).read_bytes().replace(b'\r\n', b'\n')
            _require(hashlib.sha256(source).hexdigest() == expected,
                     'Reviewed identity implementation changed: ' + name)
        events = _authenticate_corpus(_ROOT if corpus_dir is None else Path(corpus_dir), pin)
        rules = _IdentityRules()
        _validate_manifest(packet, rules)
        states = _document_states(packet, Path(evidence_dir))
        report = _reconcile(packet, events, states, rules)
        report['result'] = ('REVIEW_REQUIRED' if any(
            sc['status'] in ('UNVERIFIED', 'REVIEW_REQUIRED')
            for survey in report['surveys'] for sc in survey['scenarios']) else 'ASSESSED')
        report['corpus_attestation'] = pin['corpora']
        return report
    except CoverageDiagnosticError:
        raise
    except (OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
        raise CoverageDiagnosticError('Unavailable or invalid diagnostic input: ' + str(exc)) from exc


class _DocumentaryPage(HTMLParser):
    """Inspect the reviewed publication, without importing a builder or fetching."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.language = None
        self.canonicals, self.rows, self.links = [], [], []
        self.states, self.cards = set(), []
        self.cell, self.name, self.score, self.literal = None, '', '', None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'html':
            self.language = attrs.get('lang')
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonicals.append(attrs.get('href'))
        if tag == 'a':
            self.links.append(attrs.get('href'))
        if 'data-coverage-state' in attrs:
            self.states.add(attrs['data-coverage-state'])
        if tag == 'details' and str(attrs.get('id', '')).startswith(('source-table-', 'scenario-')):
            self.cards.append(attrs.get('id'))
        if tag == 'tr':
            self.name, self.score, self.literal = '', '', None
        if tag == 'th' and attrs.get('scope') == 'row':
            self.cell = 'name'
        if tag == 'td' and 'data-published-literal' in attrs:
            self.cell, self.literal = 'score', attrs['data-published-literal']

    def handle_data(self, data):
        if self.cell == 'name':
            self.name += data
        elif self.cell == 'score':
            self.score += data

    def handle_endtag(self, tag):
        if tag in ('th', 'td'):
            self.cell = None
        if tag == 'tr' and self.literal is not None:
            self.rows.append((self.name.strip(), self.score.strip(), self.literal))


def _load_current_review():
    review = _read_json(_CURRENT_REVIEW_PATH)
    _require(_digest(review) == _CURRENT_REVIEW_SHA256,
             'Current review overlay changed; explicit review required')
    _require(review['schema_version'] == _CURRENT_SCHEMA
             and review['scope'] == ['commission:10333'], 'Current review scope changed')
    packet, historical_pin = _load_review()
    _require(_digest(packet) == review['manifest_sha256']
             and _digest(historical_pin) == review['historical_pin_sha256'],
             'Current/historical review relationship changed')
    _require(set(review['identity_source_sha256']) == set(historical_pin['identity_source_sha256']),
             'Incomplete current identity dependency inventory')
    for name, expected in review['identity_source_sha256'].items():
        actual = hashlib.sha256((_ROOT / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        _require(actual == expected, 'Current identity implementation changed: ' + name)
    surveys = [s for s in packet['surveys'] if s['survey_id'] == 'commission:10333']
    documents = [d for d in packet['documents'] if d['document_id'] == '10333']
    _require(len(surveys) == len(documents) == 1, 'Current review requires one exact study')
    survey, document = surveys[0], documents[0]
    _require(_digest(survey) == review['survey_sha256'] and document == review['document'],
             'Reviewed study/document identity changed')
    scoped = dict(packet, surveys=surveys, documents=documents)
    rules = _IdentityRules()
    _validate_manifest(scoped, rules)
    expected = review['scenarios']
    _require(len(expected) == 4 and len({s['scenario_id'] for s in expected}) == 4,
             'Current review requires four distinct scenario assignments')
    _require(survey['inventory_review'] == {'complete': True, 'expected_by_round': review['expected_by_round']}
             and review['expected_by_round'] == {'first_round': 1, 'second_round': 3},
             'Current scenario inventory is incomplete')
    actual = [{'scenario_id': sc['scenario_id'], 'round': sc['round'],
               'pdf_page': sc['table_evidence']['page'], 'published_column': sc['published_column'],
               'candidate_ids': [row['identity_id'] for row in sc['rows']],
               'rows_sha256': _digest(sc['rows']), 'respondent_bases': sc['respondent_bases'],
               'reviewed_event_binding': sc['reviewed_event_binding']} for sc in survey['scenarios']]
    _require(sorted(actual, key=lambda s: s['scenario_id']) == sorted(expected, key=lambda s: s['scenario_id']),
             'Current scenario configuration, evidence or binding changed')
    notices = _read_json(_CURRENT_PUBLICATION_ROOT / 'commission_notice_registry.json')['notices']
    matching = [n for n in notices if n['notice_id'] == 'commission:10333']
    _require(matching == [review['notice_identity']], 'Current Commission notice identity changed')
    _require(review['notice_identity']['content_sha256'] == document['sha256'],
             'Commission notice/document hash conflict')
    return review, scoped, rules


def _authenticate_current_documentary(review, packet, rules):
    """Join frozen literals, explicit route registration and both actual HTML files."""
    proof = review['documentary']
    survey, document = packet['surveys'][0], packet['documents'][0]
    assigned = [sc for sc in survey['scenarios'] if sc['scenario_id'] == proof['scenario_id']]
    _require(len(assigned) == 1, 'Unknown documentary scenario assignment')
    scenario = assigned[0]
    _require(scenario['round'] == 'first_round' and scenario['reviewed_event_binding'] is None,
             'Documentary assignment must retain the unbound first round')
    source = _read_json(_CURRENT_PUBLICATION_ROOT / 'poll_source_tables.json')
    _require(_digest(source) == proof['source_tables_sha256'], 'Documentary collection changed')
    entry = source['tables']['10333']
    table = entry['table']
    _require(_digest(table) == entry['record_sha256'] == proof['record_sha256'],
             'Documentary record changed')
    _require(table['source_table_id'] == proof['source_table_id']
             and table['reviewed_scenario_id'] == scenario['scenario_id']
             and table['notice']['notice_id'] == survey['survey_id'], 'Documentary source binding conflict')
    _require(table['source']['pdf_url'] == document['url']
             and table['source']['pdf_sha256'] == document['sha256']
             and table['source']['pdf_page'] == scenario['table_evidence']['page']
             and table['source']['table_locator'] == scenario['scenario_id']
             and table['source']['published_column'] == scenario['published_column'],
             'Documentary PDF/page/column conflict')
    _require(table['rows'] == scenario['rows'] and len(table['rows']) == 13,
             'Documentary candidate literals changed')
    _require(table['round'] == scenario['round']
             and rules.institute(table['institute'], survey, packet) == survey['institute_id']
             and rules.normalize(table['commissioner']) == rules.normalize(survey['commissioner'])
             and table['fieldwork_start'] == survey['fieldwork']['start']
             and table['fieldwork_end'] == survey['fieldwork']['end']
             and table['publication_date'] == survey['publication_date']
             and table['population'] == survey['population'], 'Documentary study identity conflict')
    bases = table['respondent_bases']
    _require(len({b['scope'] for b in bases}) == len(bases)
             and {b['scope']: b['count'] for b in bases} == survey['respondent_bases'] | scenario['respondent_bases'],
             'Documentary respondent-base conflict')
    _require(table['numerical_comparisons'] == 'excluded_whole_table', 'Documentary numeric eligibility changed')
    registration = proof['registration']
    _require(registration == dict(source['standalone_pages']['10333'], notice_id='10333'),
             'Documentary route association changed')
    registered = _read_json(_CURRENT_PUBLICATION_ROOT / 'poll_pages_manifest.json')['source_pages']
    relevant = [r for r in registered if r.get('notice_id') == '10333'
                or any(r.get('page_path_' + lang) == registration['page_path_' + lang] for lang in ('fr', 'en'))]
    _require(relevant == [registration], 'Missing, changed or duplicate documentary registration')
    _require(set(proof['pages']) == {'fr', 'en'}, 'Both documentary languages required')
    page_hashes = {}
    for lang, page in sorted(proof['pages'].items()):
        route = registration['page_path_' + lang]
        relative = route.lstrip('/') + 'index.html'
        path = (_CURRENT_PUBLICATION_ROOT / relative).resolve()
        _require(page['relative_path'] == relative and _CURRENT_PUBLICATION_ROOT.resolve() in path.parents,
                 'Documentary page escaped its registered route')
        raw = path.read_bytes().replace(b'\r\n', b'\n')
        actual = hashlib.sha256(raw).hexdigest()
        _require(actual == page['sha256_lf'], 'Documentary page changed: ' + lang)
        html = _DocumentaryPage()
        html.feed(raw.decode('utf8'))
        expected_rows = [(r['published_name'], r['result']['literal'], r['result']['literal']) for r in table['rows']]
        _require(html.language == lang and html.canonicals == ['https://france2027.app' + route]
                 and html.rows == expected_rows and html.cards == ['source-table-10333']
                 and html.states == {'SOURCE_DOCUMENT_VERIFIED', 'DOCUMENTARY_COVERAGE_PUBLISHED', 'NUMERICAL_OBSERVATION_ABSENT'}
                 and document['url'] + '#page=' + str(scenario['table_evidence']['page']) in html.links,
                 'Documentary page semantics conflict: ' + lang)
        page_hashes[lang] = actual
    return {'state': 'published', 'reason': None, 'source_table_id': proof['source_table_id'],
            'record_sha256': proof['record_sha256'], 'registration': registration, 'page_sha256_lf': page_hashes}


def _assess_current_coverage(evidence_dir, *, corpus_dir=None):
    """CLI-only current review; no injectable events, pins, approval flags or writes."""
    try:
        review, packet, rules = _load_current_review()
        events = _authenticate_corpus(_ROOT if corpus_dir is None else Path(corpus_dir), review)
        states = _document_states(packet, Path(evidence_dir))
        source = states['10333']
        source_state = {'VERIFIED': 'verified', 'UNAVAILABLE': 'unavailable', 'HASH_MISMATCH': 'changed'}[source['state']]
        try:
            documentary = _authenticate_current_documentary(review, packet, rules)
        except (OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
            documentary = {'state': 'unverified', 'reason': str(exc)}
        historical = _reconcile(packet, events, states, rules)
        scenarios = []
        definitions = {sc['scenario_id']: sc for sc in packet['surveys'][0]['scenarios']}
        for assessed in historical['surveys'][0]['scenarios']:
            sc = definitions[assessed['scenario_id']]
            first = sc['round'] == 'first_round'
            doc = documentary if first else {'state': 'reviewed-only' if source_state == 'verified' else 'unverified', 'reason': None}
            status = assessed['status']
            if source_state != 'verified' or (first and doc['state'] != 'published'):
                numeric, reason = 'unverified', 'required_evidence_unverified'
            elif status == 'NUMERIC_VERIFIED':
                numeric, reason = 'verified', None
            elif status == 'MISSING_CONFIRMED':
                numeric = 'absent'
                reason = ('non_exact_source_values' if any(v is None for v in _source_vector(sc, rules).values())
                          else 'no_faithful_numerical_configuration')
            else:
                numeric, reason = 'conflicting', 'reviewed_binding_missing_or_conflicting'
            scenarios.append({'scenario_id': sc['scenario_id'], 'round': sc['round'],
                              'source_authentication': source_state, 'pdf_page': sc['table_evidence']['page'],
                              'published_column': sc['published_column'], 'rows': sc['rows'],
                              'respondent_bases': packet['surveys'][0]['respondent_bases'] | sc['respondent_bases'],
                              'numerical_coverage': {'state': numeric, 'reason': reason,
                                                     'event_binding': sc['reviewed_event_binding'] if numeric == 'verified' else None},
                              'documentary_coverage': doc, 'rejected_candidates': assessed['rejected_candidates']})
        complete = all(sc['numerical_coverage']['state'] in ('verified', 'absent') for sc in scenarios)
        verified = sum(sc['numerical_coverage']['state'] == 'verified' for sc in scenarios)
        summary = {'expected_configurations': len(scenarios), 'verified_numerical_configurations': verified,
                   'published_documentary_only_configurations': sum(sc['numerical_coverage']['state'] == 'absent'
                       and sc['documentary_coverage']['state'] == 'published' for sc in scenarios) if complete else None,
                   'configurations_without_either_representation': sum(sc['numerical_coverage']['state'] != 'verified'
                       and sc['documentary_coverage']['state'] != 'published' for sc in scenarios) if complete else None,
                   'configurations_lacking_faithful_numerical_representation': len(scenarios) - verified if complete else None,
                   'numerically_complete': verified == len(scenarios) if complete else None}
        return {'schema_version': _CURRENT_SCHEMA, 'review_id': review['review_id'],
                'result': 'ASSESSED' if complete else 'REVIEW_REQUIRED', 'notice_id': 'commission:10333',
                'review_sha256': _digest(review), 'baseline_sha': review['baseline_sha'],
                'manifest_sha256': review['manifest_sha256'], 'historical_pin_sha256': review['historical_pin_sha256'],
                'corpus_attestation': review['corpora'], 'identity_source_sha256': review['identity_source_sha256'],
                'source_authentication': dict(source, state=source_state),
                'production_notice_coverage': review['notice_identity']['coverage'],
                'summary': summary, 'scenarios': scenarios}
    except CoverageDiagnosticError:
        raise
    except (OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
        raise CoverageDiagnosticError('Unavailable or invalid current review input: ' + str(exc)) from exc


def _main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir', required=True, type=Path,
                        help='External directory containing the five original reviewed PDFs')
    parser.add_argument('--corpus-dir', type=Path, default=None,
                        help='Directory containing both numerical JSON files (default: this checkout)')
    parser.add_argument('--review', choices=('historical', '10333-20261028'), default='historical',
                        help='Explicit reviewed assessment; historical behavior remains the default')
    args = parser.parse_args(argv)
    try:
        assessor = assess_coverage if args.review == 'historical' else _assess_current_coverage
        report = assessor(args.evidence_dir, corpus_dir=args.corpus_dir)
    except CoverageDiagnosticError as exc:
        print(json.dumps({'result': exc.code, 'message': str(exc), 'details': exc.details}, sort_keys=True))
        return 2
    print(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False))
    return 0 if report['result'] == 'ASSESSED' else 2


if __name__ == '__main__':
    raise SystemExit(_main())
