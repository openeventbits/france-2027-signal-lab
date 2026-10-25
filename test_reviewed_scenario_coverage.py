"""Controlled offline fixtures: no live poll files, original PDFs or audit paths.

Reference IDs identify the reviewed associations, but fixture observations and
PDF bytes are deliberately synthetic. The real historical corpus is assessed
only by an operator, never as a mutable CI fixture. Every behavioral test goes
through the public authentication entry point with a test-only trust anchor.
"""
import contextlib
import copy
import hashlib
import inspect
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import reviewed_scenario_coverage as coverage

ROOT = Path(__file__).resolve().parent


def flatten(report):
    return {sc['scenario_id']: sc for study in report['surveys'] for sc in study['scenarios']}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf8')


class ReviewedScenarioCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        original, reviewed_pin = coverage._load_review()
        cls.packet = copy.deepcopy(original)
        cls.pdf_bytes = {d['document_id']: ('%PDF-controlled-fixture-' + d['document_id']).encode()
                         for d in cls.packet['documents']}
        for d in cls.packet['documents']:
            d['sha256'] = hashlib.sha256(cls.pdf_bytes[d['document_id']]).hexdigest()
        cls.events = []
        for survey in cls.packet['surveys']:
            for sc in survey['scenarios']:
                binding = sc['reviewed_event_binding']
                if not binding:
                    continue
                event = {
                    'event_id': binding['event_id'],
                    'pollster': 'Harris' if survey['institute_id'] == 'harris-interactive' else survey['institute'],
                    'commissioner': None, 'publication_date': None,
                    'fieldwork_start': survey['fieldwork']['start'], 'fieldwork_end': survey['fieldwork']['end'],
                    'sample_size': survey['respondent_bases'][binding['legacy_metadata_bridge']['reported_sample_base']],
                    'sample_scope': 'reported', 'round': sc['round'], 'source_url': binding['source_url'],
                    'candidates': [{'name': r['published_name'], 'score': r['result']['percent']} for r in sc['rows']],
                }
                binding['event_object_sha256'] = coverage._digest(event)
                cls.events.append(event)
        # Two deliberately contradictory representations; these are controlled
        # examples, not copied snapshots of retained numerical observations.
        for notice, excluded in [('10319', {'Gabriel Attal', 'Karim Bouamrane', 'David Lisnard'}),
                                 ('10141', {'François Ruffin'})]:
            survey = next(s for s in cls.packet['surveys'] if s['survey_id'] == 'commission:' + notice)
            sc = survey['scenarios'][0]
            event = {'event_id': survey['legacy_notice_event_claims'][0], 'pollster': survey['institute'],
                     'commissioner': 'Les Échos et Radio Classique' if notice == '10319' else None,
                     'fieldwork_start': survey['fieldwork']['start'], 'fieldwork_end': survey['fieldwork']['end'],
                     'round': 'first_round', 'sample_size': 978 if notice == '10319' else 1137,
                     'sample_scope': 'reported',
                     'source_url': 'https://controlled.invalid/presitrack' if notice == '10319' else survey['accepted_source_urls'][0],
                     'candidates': [{'name': r['published_name'], 'score': r['result']['percent']}
                                    for r in sc['rows'] if r['published_name'] not in excluded]}
            if notice == '10141':
                for row in event['candidates']:
                    row['score'] = {'Jean-Luc Mélenchon': 13, 'Jordan Bardella': 36}.get(row['name'], row['score'])
            cls.events.append(event)
        cls.pin_template = reviewed_pin
        # Test trust anchors describe controlled fixtures, not live code/data pins.
        cls.pin_template['identity_source_sha256'] = {
            name: hashlib.sha256((ROOT / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            for name in reviewed_pin['identity_source_sha256']}

    def scenario(self, notice='10332', index=0, packet=None):
        return next(s for s in (packet or self.packet)['surveys'] if s['survey_id'] == 'commission:' + notice)['scenarios'][index]

    @contextlib.contextmanager
    def fixture(self, packet=None, events=None, unavailable=(), changed=()):
        packet = copy.deepcopy(packet if packet is not None else self.packet)
        events = copy.deepcopy(events if events is not None else self.events)
        with tempfile.TemporaryDirectory(prefix='fr27-coverage-controlled-') as directory:
            root = Path(directory)
            cache, corpus = root / 'evidence', root / 'corpus'
            cache.mkdir()
            corpus.mkdir()
            for d in packet['documents']:
                if d['document_id'] not in unavailable:
                    (cache / d['evidence_key']).write_bytes(b'changed' if d['document_id'] in changed else self.pdf_bytes[d['document_id']])
            first = [e for e in events if e['round'] == 'first_round']
            second = [e for e in events if e['round'] == 'second_round']
            write_json(corpus / 'polls.json', first)
            write_json(corpus / 'second_round_polls.json', {'events': second, 'generated_at': 'controlled'})
            manifest_path, pin_path = root / 'manifest.json', root / 'pin.json'
            pin = copy.deepcopy(self.pin_template)
            pin['manifest_sha256'] = coverage._digest(packet)
            # Controlled changes are explicitly authorized here to exercise the
            # matcher; stale-baseline tests mutate files AFTER this attestation.
            # Duplicate-ID cases use a raw fingerprint to reach the loader guard.
            pin['corpora'] = {name: {'count': len(rows), 'sha256': coverage._digest(sorted(rows, key=lambda e: e['event_id']))}
                              for name, rows in [('polls.json', first), ('second_round_polls.json', second)]}
            write_json(manifest_path, packet)
            write_json(pin_path, pin)
            with patch.object(coverage, '_MANIFEST_PATH', manifest_path), \
                 patch.object(coverage, '_PIN_PATH', pin_path), \
                 patch.object(coverage, '_PIN_SHA256', coverage._digest(pin)):
                yield cache, corpus, manifest_path, pin_path

    def assess(self, packet=None, events=None, **kwargs):
        with self.fixture(packet, events, **kwargs) as (cache, corpus, *_):
            return coverage.assess_coverage(cache, corpus_dir=corpus)

    def mutate_bound(self, change):
        events = copy.deepcopy(self.events)
        sc = self.scenario()
        event = next(e for e in events if e['event_id'] == sc['reviewed_event_binding']['event_id'])
        change(event)
        return flatten(self.assess(events=events))[sc['scenario_id']]

    def reasons(self, result):
        return {reason for row in result['rejected_candidates'] for reason in row['reasons']}

    def fake_source_event(self, notice, *, invented=0.5):
        survey = next(s for s in self.packet['surveys'] if s['survey_id'] == 'commission:' + notice)
        sc = survey['scenarios'][0]
        return {'event_id': 'f' * 64, 'pollster': survey['institute'], 'commissioner': survey['commissioner'],
                'fieldwork_start': survey['fieldwork']['start'], 'fieldwork_end': survey['fieldwork']['end'],
                'round': 'first_round', 'source_url': survey['accepted_source_urls'][0],
                'sample_size': survey['respondent_bases']['registered_voters'],
                'candidates': [{'name': r['published_name'], 'score': r['result'].get('percent', invented)} for r in sc['rows']]}

    def test_01_reference_21_scenario_result(self):
        result = self.assess()
        self.assertEqual(result['summary']['expected_scenarios'], 21)
        self.assertEqual(result['summary']['status_counts'], {'NUMERIC_VERIFIED': 14, 'MISSING_CONFIRMED': 6, 'MISATTRIBUTED': 1})
        self.assertEqual(result['summary']['verified_by_round'], {'first_round': 5, 'second_round': 9})
        self.assertEqual(result['summary']['confirmed_gaps_by_round'], {'first_round': 7, 'second_round': 0})

    def test_02_cnews_false_presitrack_claim_rejected(self):
        study = next(s for s in self.assess()['surveys'] if s['survey_id'] == 'commission:10319')
        claim = study['legacy_notice_claims'][0]
        self.assertEqual(claim['event_id'], '7c7bb3a59970c61e70ba91e474b2ed4a6386645d2b258b8d6c3aa9e4f7aecf03')
        self.assertEqual(claim['state'], 'REJECTED')
        self.assertTrue({'SOURCE_RELATIONSHIP_CONFLICT', 'COMMISSIONER_CONFLICT', 'CANDIDATE_CONFIGURATION_CONFLICT'} <= set(claim['reasons']))

    def test_03_cnews_missing_first_rounds_keep_every_bound(self):
        result = flatten(self.assess())
        for notice, count in [('10319', 1), ('10333', 2)]:
            sc = self.scenario(notice)
            self.assertEqual(result[sc['scenario_id']]['status'], 'MISSING_CONFIRMED')
            bounds = [r['result'] for r in sc['rows'] if r['result']['kind'] == 'strict_upper_bound']
            self.assertEqual(len(bounds), count)
            self.assertTrue(all(b == {'kind': 'strict_upper_bound', 'literal': '<1%', 'upper_percent': 1} for b in bounds))

    def test_04_six_cnews_runoffs_verified(self):
        rows = [sc for s in self.assess()['surveys'] if s['survey_id'] in ('commission:10319', 'commission:10333')
                for sc in s['scenarios'] if sc['round'] == 'second_round']
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(sc['status'] == 'NUMERIC_VERIFIED' for sc in rows))
        self.assertEqual(len({sc['verified_event_id'] for sc in rows}), 6)

    def test_05_harris_complete_without_new_events(self):
        study = next(s for s in self.assess()['surveys'] if s['survey_id'] == 'commission:10332')
        self.assertEqual(len(study['scenarios']), 8)
        self.assertTrue(study['numerically_complete'] and study['baseline_documentary_complete'])

    def test_06_ifop_wrong_claim_retained_without_mutation(self):
        before = coverage._digest(self.events)
        sc = flatten(self.assess())[self.scenario('10141')['scenario_id']]
        self.assertEqual(sc['status'], 'MISATTRIBUTED')
        self.assertIsNone(sc['verified_event_id'])
        self.assertTrue(sc['confirmed_absent_faithful_configuration'])
        self.assertIn('EXACT_SCORE_VECTOR_CONFLICT', self.reasons(sc))
        self.assertEqual(before, coverage._digest(self.events))

    def test_07_four_pollitics_tables_missing(self):
        study = next(s for s in self.assess()['surveys'] if s['survey_id'] == 'commission:10166a')
        self.assertEqual(study['commissioner'], 'POLLITICS')
        self.assertEqual(len(study['scenarios']), 4)
        self.assertTrue(all(s['status'] == 'MISSING_CONFIRMED' for s in study['scenarios']))

    def test_08_conflicts_are_not_hidden_by_null_metadata_bridges(self):
        changes = [('commissioner', 'CNews', 'COMMISSIONER_CONFLICT'),
                   ('population_id', 'national_adults', 'POPULATION_CONFLICT'),
                   ('survey_population', 'All French adults', 'POPULATION_CONFLICT'),
                   ('respondent_bases', {'registered_voters': 2500}, 'RESPONDENT_BASE_CONFLICT'),
                   ('respondent_bases', {'unknown': 2094}, 'RESPONDENT_BASE_CONFLICT'),
                   ('sample_size', 2500, 'RESPONDENT_BASE_CONFLICT'),
                   ('sample_scope', 'adults', 'RESPONDENT_SCOPE_CONFLICT'),
                   ('source_url', 'https://controlled.invalid/wrong-source', 'SOURCE_RELATIONSHIP_CONFLICT'),
                   ('official_notice_id', 'commission:10319', 'OFFICIAL_NOTICE_CONFLICT'),
                   ('publication_date', '2026-01-01', 'PUBLICATION_DATE_CONFLICT'),
                   ('fieldwork_start', '2026-10-18', 'FIELDWORK_CONFLICT'),
                   ('round', 'second_round', 'ROUND_CONFLICT'), ('pollster', 'OpinionWay', 'INSTITUTE_IDENTITY_CONFLICT')]
        for key, value, reason in changes:
            with self.subTest(field=key, value=value):
                row = self.mutate_bound(lambda e: e.update({key: value}))
                self.assertEqual(row['status'], 'REVIEW_REQUIRED')
                self.assertIsNone(row['verified_event_id'])
                self.assertFalse(row['confirmed_absent_faithful_configuration'])
                self.assertIn(reason, self.reasons(row))

    def test_09_wrong_score(self):
        row = self.mutate_bound(lambda e: e['candidates'][0].update(score=1.5))
        self.assertEqual(row['status'], 'REVIEW_REQUIRED')
        self.assertIn('EXACT_SCORE_VECTOR_CONFLICT', self.reasons(row))

    def test_10_removed_candidate(self):
        row = self.mutate_bound(lambda e: e['candidates'].pop())
        self.assertEqual(row['status'], 'REVIEW_REQUIRED')
        self.assertIn('CANDIDATE_CONFIGURATION_CONFLICT', self.reasons(row))

    def test_11_unknown_candidate(self):
        row = self.mutate_bound(lambda e: e['candidates'][0].update(name='Unreviewed Person'))
        self.assertEqual(row['status'], 'REVIEW_REQUIRED')
        self.assertIn('INVALID_CANDIDATE_OR_SCORE', self.reasons(row))

    def test_12_harris_alias_requires_scoped_review(self):
        packet = copy.deepcopy(self.packet)
        next(a for a in packet['identity_rules']['institute_alias_reviews'] if a['institute_id'] == 'harris-interactive')['labels'] = ['Harris Interactive']
        study = next(s for s in self.assess(packet=packet)['surveys'] if s['survey_id'] == 'commission:10332')
        self.assertTrue(all(s['status'] == 'REVIEW_REQUIRED' for s in study['scenarios']))

    def test_13_missing_evidence_never_confirms_a_gap(self):
        result = self.assess(unavailable=self.pdf_bytes)
        self.assertEqual(result['result'], 'REVIEW_REQUIRED')
        self.assertEqual(result['summary']['status_counts'], {'UNVERIFIED': 21})
        self.assertEqual(result['summary']['confirmed_gaps_by_round']['first_round'], 0)
        self.assertTrue(all(c['state'] == 'UNVERIFIED' for s in result['surveys'] for c in s['legacy_notice_claims']))

    def test_14_changed_evidence_fails_closed(self):
        study = next(s for s in self.assess(changed=('10319',))['surveys'] if s['survey_id'] == 'commission:10319')
        self.assertTrue(all(s['status'] == 'REVIEW_REQUIRED' for s in study['scenarios']))
        self.assertFalse(any(s['confirmed_absent_faithful_configuration'] for s in study['scenarios']))

    def test_15_controlled_inputs_unchanged(self):
        before = coverage._digest((self.packet, self.events))
        self.assess()
        self.assertEqual(before, coverage._digest((self.packet, self.events)))
        self.assertEqual(len(self.events), 16)

    def test_16_determinism_and_array_order(self):
        self.assertEqual(self.assess(), self.assess(events=list(reversed(self.events))))

    def test_17_unbound_exact_match_requires_review(self):
        packet = copy.deepcopy(self.packet)
        sc = self.scenario(packet=packet)
        sc['reviewed_event_binding'] = None
        row = flatten(self.assess(packet=packet))[sc['scenario_id']]
        self.assertEqual(row['status'], 'REVIEW_REQUIRED')
        self.assertFalse(row['confirmed_absent_faithful_configuration'])

    def test_18_missing_bound_observation_is_review_not_invented_gap(self):
        sc = self.scenario()
        events = [e for e in self.events if e['event_id'] != sc['reviewed_event_binding']['event_id']]
        self.assertEqual(flatten(self.assess(events=events))[sc['scenario_id']]['status'], 'REVIEW_REQUIRED')

    def test_19_invented_bound_scores_cannot_verify(self):
        for invented in (0, 0.5, 0.9):
            row = flatten(self.assess(events=self.events + [self.fake_source_event('10333', invented=invented)]))[self.scenario('10333')['scenario_id']]
            self.assertEqual(row['status'], 'REVIEW_REQUIRED')
            self.assertIsNone(row['verified_event_id'])

    def test_20_bounds_and_dashes_never_carry_exact_values(self):
        for result in ({'kind': 'strict_upper_bound', 'literal': '<1%', 'upper_percent': 1, 'percent': 0},
                       {'kind': 'source_dash', 'literal': '-', 'numeric_meaning': 'unconfirmed', 'value': 0}):
            packet = copy.deepcopy(self.packet)
            self.scenario('10333', packet=packet)['rows'][0]['result'] = result
            with self.assertRaises(coverage.CoverageDiagnosticError):
                self.assess(packet=packet)
        packet = copy.deepcopy(self.packet)
        self.scenario('10333', packet=packet)['rows'][0]['result'] = {'kind': 'source_dash', 'literal': '-', 'numeric_meaning': 'unconfirmed'}
        self.assertEqual(flatten(self.assess(packet=packet))[self.scenario('10333')['scenario_id']]['status'], 'MISSING_CONFIRMED')

    def test_21_exact_literal_value_conflict(self):
        packet = copy.deepcopy(self.packet)
        self.scenario(packet=packet)['rows'][0]['result']['percent'] = 2
        with self.assertRaises(coverage.CoverageDiagnosticError):
            self.assess(packet=packet)

    def test_22_duplicate_canonical_candidate(self):
        packet = copy.deepcopy(self.packet)
        sc = self.scenario(packet=packet)
        sc['rows'].append(copy.deepcopy(sc['rows'][0]))
        with self.assertRaises(coverage.CoverageDiagnosticError):
            self.assess(packet=packet)

    def test_23_duplicate_event_or_scenario(self):
        with self.assertRaises(coverage.CoverageDiagnosticError):
            self.assess(events=self.events + [self.events[0]])
        packet = copy.deepcopy(self.packet)
        packet['surveys'][0]['scenarios'].append(copy.deepcopy(packet['surveys'][0]['scenarios'][0]))
        with self.assertRaises(coverage.CoverageDiagnosticError):
            self.assess(packet=packet)

    def test_24_incomplete_inventory_never_proves_completeness_or_gap(self):
        packet = copy.deepcopy(self.packet)
        for survey in packet['surveys']:
            survey['inventory_review']['complete'] = False
        result = self.assess(packet=packet)
        self.assertFalse(any(s['numerically_complete'] for s in result['surveys']))
        self.assertFalse(any(s['confirmed_absent_faithful_configuration'] for s in flatten(result).values()))

    def test_25_stale_baseline_has_no_coverage_result(self):
        with self.fixture() as (cache, corpus, *_):
            events = coverage._read_json(corpus / 'polls.json')
            events[0]['candidates'][0]['score'] += 1
            write_json(corpus / 'polls.json', events)
            with self.assertRaises(coverage.CoverageDiagnosticError) as caught:
                coverage.assess_coverage(cache, corpus_dir=corpus)
            self.assertEqual(caught.exception.code, 'BASELINE_STALE')
            self.assertNotIn('summary', caught.exception.details)
            self.assertNotIn('surveys', caught.exception.details)

    def test_26_unauthenticated_manifest_edit_rejected(self):
        with self.fixture() as (cache, corpus, manifest_path, _):
            packet = coverage._read_json(manifest_path)
            packet['surveys'][0]['commissioner'] = 'Wrong source'
            write_json(manifest_path, packet)
            with self.assertRaisesRegex(coverage.CoverageDiagnosticError, 'manifest changed'):
                coverage.assess_coverage(cache, corpus_dir=corpus)

    def test_27_authentication_pin_edit_rejected(self):
        with self.fixture() as (cache, corpus, _, pin_path):
            pin = coverage._read_json(pin_path)
            pin['baseline_sha'] = '0' * 40
            write_json(pin_path, pin)
            with self.assertRaisesRegex(coverage.CoverageDiagnosticError, 'pin changed'):
                coverage.assess_coverage(cache, corpus_dir=corpus)

    def test_28_no_event_id_generation(self):
        import poll_contract
        with patch.object(poll_contract, 'make_event_id', side_effect=AssertionError('No new IDs')), \
             patch.object(poll_contract, 'make_scenario_key', side_effect=AssertionError('No new keys')):
            self.assertEqual(self.assess()['summary']['status_counts']['NUMERIC_VERIFIED'], 14)

    def test_29_offline_operation(self):
        with patch('socket.socket.connect', side_effect=AssertionError('Network prohibited')):
            self.assertEqual(self.assess()['result'], 'ASSESSED')

    def test_30_public_diagnostic_and_cli_only_read_and_print(self):
        with self.fixture() as (cache, corpus, *_):
            with patch.object(Path, 'write_text', side_effect=AssertionError('No writes')), \
                 patch.object(Path, 'write_bytes', side_effect=AssertionError('No writes')), \
                 contextlib.redirect_stdout(io.StringIO()) as stream:
                code = coverage._main(['--evidence-dir', str(cache), '--corpus-dir', str(corpus)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stream.getvalue())['result'], 'ASSESSED')

    def test_31_duplicate_plausible_object_requires_review(self):
        event = copy.deepcopy(next(e for e in self.events if e['event_id'] == self.scenario()['reviewed_event_binding']['event_id']))
        event['event_id'] = 'e' * 64
        row = flatten(self.assess(events=self.events + [event]))[self.scenario()['scenario_id']]
        self.assertEqual(row['status'], 'REVIEW_REQUIRED')

    def test_32_boolean_is_not_score(self):
        row = self.mutate_bound(lambda e: e['candidates'][0].update(score=True))
        self.assertEqual(row['status'], 'REVIEW_REQUIRED')

    def test_33_bridge_identity_conflict(self):
        for field in ('commissioner', 'population_id'):
            packet = copy.deepcopy(self.packet)
            self.scenario(packet=packet)['reviewed_event_binding']['legacy_metadata_bridge'][field] = 'Wrong identity'
            with self.assertRaises(coverage.CoverageDiagnosticError):
                self.assess(packet=packet)

    def test_34_omitted_censored_rows_not_hidden_by_total_100(self):
        event = self.fake_source_event('10333')
        event['candidates'] = [c for c in event['candidates'] if c['name'] not in ('Nathalie Arthaud', 'Karim Bouamrane')]
        event['partial_scenario'] = False
        self.assertEqual(sum(c['score'] for c in event['candidates']), 100)
        row = flatten(self.assess(events=self.events + [event]))[self.scenario('10333')['scenario_id']]
        self.assertEqual(row['status'], 'REVIEW_REQUIRED')

    def test_35_unexplained_conflicting_source_is_review_not_gap(self):
        event = self.fake_source_event('10166a')
        event.update(commissioner='L’Opinion', sample_size=2000)
        event['candidates'][0]['score'] = 2
        row = flatten(self.assess(events=self.events + [event]))[self.scenario('10166a')['scenario_id']]
        self.assertEqual(row['status'], 'REVIEW_REQUIRED')
        self.assertFalse(row['confirmed_absent_faithful_configuration'])
        self.assertTrue({'COMMISSIONER_CONFLICT', 'RESPONDENT_BASE_CONFLICT', 'EXACT_SCORE_VECTOR_CONFLICT'} <= self.reasons(row))

    def test_36_candidate_id_mapping_conflict(self):
        packet = copy.deepcopy(self.packet)
        self.scenario(packet=packet)['rows'][0]['identity_id'] = 'jean-luc-melenchon'
        with self.assertRaises(coverage.CoverageDiagnosticError):
            self.assess(packet=packet)

    def test_37_source_base_hierarchy_conflict(self):
        packet = copy.deepcopy(self.packet)
        next(s for s in packet['surveys'] if s['survey_id'] == 'commission:10333')['respondent_bases']['certain_to_vote'] = 2000
        with self.assertRaises(coverage.CoverageDiagnosticError):
            self.assess(packet=packet)

    def test_38_cross_study_evidence_conflict(self):
        packet = copy.deepcopy(self.packet)
        self.scenario(packet=packet)['table_evidence']['document_id'] = '10319'
        with self.assertRaises(coverage.CoverageDiagnosticError):
            self.assess(packet=packet)

    def test_39_excerpt_cannot_prove_complete_study(self):
        packet = copy.deepcopy(self.packet)
        survey = next(s for s in packet['surveys'] if s['survey_id'] == 'commission:10319')
        survey['scenarios'] = survey['scenarios'][:1]
        survey['inventory_review']['complete'] = False
        packet['surveys'] = [survey]
        result = self.assess(packet=packet)
        self.assertEqual(result['summary']['expected_scenarios'], 1)
        self.assertEqual(result['summary']['status_counts'], {'REVIEW_REQUIRED': 1})
        self.assertFalse(result['surveys'][0]['review_packet_documentary_complete'])

    def test_40_editing_both_manifest_and_pin_does_not_bypass_root_anchor(self):
        with self.fixture() as (cache, corpus, manifest_path, pin_path):
            packet = coverage._read_json(manifest_path)
            packet['surveys'][0]['scenarios'].clear()
            pin = coverage._read_json(pin_path)
            pin['manifest_sha256'] = coverage._digest(packet)
            write_json(manifest_path, packet)
            write_json(pin_path, pin)
            with self.assertRaisesRegex(coverage.CoverageDiagnosticError, 'pin changed'):
                coverage.assess_coverage(cache, corpus_dir=corpus)

    def test_41_identity_implementation_drift_fails_closed(self):
        with self.fixture() as (cache, corpus, *_):
            read_bytes = Path.read_bytes
            def changed_source(path):
                return b'changed identity implementation' if path == ROOT / 'poll_migration.py' else read_bytes(path)
            with patch.object(Path, 'read_bytes', changed_source):
                with self.assertRaisesRegex(coverage.CoverageDiagnosticError, 'identity implementation changed'):
                    coverage.assess_coverage(cache, corpus_dir=corpus)

    def test_42_duplicate_json_keys_fail_closed(self):
        with self.fixture() as (cache, corpus, manifest_path, _):
            manifest_path.write_text('{"schema_version":"a","schema_version":"b"}', encoding='utf8')
            with self.assertRaises(coverage.CoverageDiagnosticError):
                coverage.assess_coverage(cache, corpus_dir=corpus)

    def test_43_additions_deletions_metadata_and_ids_are_stale(self):
        changes = [lambda es: es.pop(), lambda es: es.append(dict(es[0], event_id='a' * 64)),
                   lambda es: es[0].update(source_url='https://controlled.invalid/changed'),
                   lambda es: es[0].update(event_id='b' * 64)]
        for change in changes:
            with self.subTest(change=change), self.fixture() as (cache, corpus, *_):
                rows = coverage._read_json(corpus / 'polls.json')
                change(rows)
                write_json(corpus / 'polls.json', rows)
                with self.assertRaises(coverage.CoverageDiagnosticError) as caught:
                    coverage.assess_coverage(cache, corpus_dir=corpus)
                self.assertEqual(caught.exception.code, 'BASELINE_STALE')

    def test_44_wrapper_timestamp_and_array_order_do_not_make_corpus_stale(self):
        with self.fixture() as (cache, corpus, *_):
            expected = coverage.assess_coverage(cache, corpus_dir=corpus)
            rows = coverage._read_json(corpus / 'second_round_polls.json')
            rows.update(generated_at='new metadata only', events=list(reversed(rows['events'])))
            write_json(corpus / 'second_round_polls.json', rows)
            self.assertEqual(expected, coverage.assess_coverage(cache, corpus_dir=corpus))

    def test_45_cli_stale_has_no_scenario_or_absence_claims(self):
        with self.fixture() as (cache, corpus, *_):
            write_json(corpus / 'polls.json', [])
            with contextlib.redirect_stdout(io.StringIO()) as stream:
                code = coverage._main(['--evidence-dir', str(cache), '--corpus-dir', str(corpus)])
            output = json.loads(stream.getvalue())
            self.assertEqual(code, 2)
            self.assertEqual(output['result'], 'BASELINE_STALE')
            self.assertNotIn('summary', output)
            self.assertNotIn('surveys', output)

    def test_46_only_public_assessment_api_always_authenticates(self):
        self.assertEqual(coverage.__all__, ['assess_coverage', 'CoverageDiagnosticError'])
        self.assertEqual(set(inspect.signature(coverage.assess_coverage).parameters), {'evidence_dir', 'corpus_dir'})
        self.assertFalse(hasattr(coverage, 'reconcile'))
        self.assertFalse(hasattr(coverage, 'run'))
        with self.assertRaises(TypeError):
            coverage.assess_coverage('unused', corpus_authenticated=True)
        with patch.object(coverage, '_load_review', side_effect=coverage.CoverageDiagnosticError('reject')):
            with self.assertRaises(coverage.CoverageDiagnosticError):
                coverage.assess_coverage('unused')

    def test_47_authentic_shipped_pin_and_manifest(self):
        packet, pin = coverage._load_review()
        self.assertEqual(coverage._digest(pin), coverage._PIN_SHA256)
        self.assertEqual(coverage._digest(packet), pin['manifest_sha256'])
        self.assertEqual(pin['baseline_sha'], '7b294e0bea0538980016e1bdc10e52bda9231397')
        self.assertEqual(sum(len(s['scenarios']) for s in packet['surveys']), 21)
        self.assertEqual(sum(sc['reviewed_event_binding'] is not None for s in packet['surveys'] for sc in s['scenarios']), 14)

    def test_48_runtime_does_not_import_or_invoke_diagnostic(self):
        for name in ('fetch_polls.py', 'commission_notice_coverage.py', 'build_poll_explorer.py', 'build_poll_pages.py'):
            self.assertNotIn('reviewed_scenario_coverage', (ROOT / name).read_text(encoding='utf8'))

    def test_49_no_live_mutable_polling_data_needed_by_tests(self):
        read = Path.read_text
        forbidden = {ROOT / 'polls.json', ROOT / 'second_round_polls.json', ROOT / 'commission_notice_registry.json'}
        def guarded(path, *args, **kwargs):
            if path.resolve() in forbidden:
                raise AssertionError('Live polling data must not be a CI fixture')
            return read(path, *args, **kwargs)
        with patch.object(Path, 'read_text', guarded):
            self.assertEqual(self.assess()['summary']['status_counts']['NUMERIC_VERIFIED'], 14)


if __name__ == '__main__':
    unittest.main()
