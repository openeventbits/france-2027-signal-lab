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


class CurrentCommissionCoverageTests(unittest.TestCase):
    """Synthetic bytes and corpus; explicit test-only anchors, never live poll JSON."""
    @contextlib.contextmanager
    def fixture(self, change=None):
        packet, old_pin = copy.deepcopy(coverage._load_review())
        review = coverage._read_json(coverage._CURRENT_REVIEW_PATH)
        survey = next(s for s in packet['surveys'] if s['survey_id'] == 'commission:10333')
        document = next(d for d in packet['documents'] if d['document_id'] == '10333')
        pdf = b'%PDF-current-controlled-10333'
        document['sha256'] = hashlib.sha256(pdf).hexdigest()
        events = []
        for sc in survey['scenarios']:
            binding = sc['reviewed_event_binding']
            if binding:
                event = {'event_id': binding['event_id'], 'round': sc['round'], 'pollster': 'OpinionWay',
                         'commissioner': None, 'publication_date': None, 'fieldwork_start': '2026-10-21',
                         'fieldwork_end': '2026-10-22', 'sample_size': 973, 'sample_scope': 'reported',
                         'source_url': binding['source_url'],
                         'candidates': [{'name': r['published_name'], 'score': r['result']['percent']} for r in sc['rows']]}
                binding['event_object_sha256'] = coverage._digest(event)
                events.append(event)
        source = coverage._read_json(ROOT / 'poll_source_tables.json')
        table = source['tables']['10333']['table']
        table['source']['pdf_sha256'] = document['sha256']
        if change:
            change(packet, events, source, review)
        source['tables']['10333']['record_sha256'] = coverage._digest(table)
        old_pin['manifest_sha256'] = coverage._digest(packet)
        review.update(manifest_sha256=coverage._digest(packet), historical_pin_sha256=coverage._digest(old_pin),
                      document=copy.deepcopy(document), survey_sha256=coverage._digest(survey))
        review['notice_identity']['content_sha256'] = document['sha256']
        review['identity_source_sha256'] = {n: hashlib.sha256((ROOT / n).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                                            for n in old_pin['identity_source_sha256']}
        for expected, sc in zip(review['scenarios'], survey['scenarios']):
            expected['reviewed_event_binding'] = copy.deepcopy(sc['reviewed_event_binding'])
        proof = review['documentary']
        proof.update(source_tables_sha256=coverage._digest(source), record_sha256=coverage._digest(table))
        first, second = [e for e in events if e['round'] == 'first_round'], [e for e in events if e['round'] == 'second_round']
        review['corpora'] = {n: {'count': len(es), 'sha256': coverage._digest(sorted(es, key=lambda e: e['event_id']))}
                             for n, es in [('polls.json', first), ('second_round_polls.json', second)]}
        with tempfile.TemporaryDirectory(prefix='fr27-current-controlled-') as directory:
            root = Path(directory)
            cache, corpus, publication = root / 'evidence', root / 'corpus', root / 'publication'
            for path in (cache, corpus, publication):
                path.mkdir()
            (cache / '10333.pdf').write_bytes(pdf)
            write_json(corpus / 'polls.json', first)
            write_json(corpus / 'second_round_polls.json', {'events': second})
            write_json(publication / 'commission_notice_registry.json', {'notices': [review['notice_identity']]})
            write_json(publication / 'poll_source_tables.json', source)
            write_json(publication / 'poll_pages_manifest.json', {'source_pages': [proof['registration']]})
            from html import escape
            for lang, pin in proof['pages'].items():
                page = publication / pin['relative_path']
                page.parent.mkdir(parents=True)
                rows = ''.join('<tr><th scope="row">' + escape(r['published_name']) + '</th><td data-published-literal="'
                               + escape(r['result']['literal'], quote=True) + '">' + escape(r['result']['literal'])
                               + '</td></tr>' for r in table['rows'])
                html = '<html lang="' + lang + '"><link rel="canonical" href="https://france2027.app' + proof['registration']['page_path_' + lang] + '">'
                html += '<details id="source-table-10333"><table>' + rows + '</table></details>'
                html += ''.join('<span data-coverage-state="' + s + '"></span>' for s in (
                    'SOURCE_DOCUMENT_VERIFIED', 'DOCUMENTARY_COVERAGE_PUBLISHED', 'NUMERICAL_OBSERVATION_ABSENT'))
                html += '<a href="' + document['url'] + '#page=12">PDF</a><details>Footer</details></html>'
                page.write_text(html, encoding='utf8')
                pin['sha256_lf'] = hashlib.sha256(page.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            manifest_path, pin_path, review_path = root / 'manifest.json', root / 'historical-pin.json', root / 'current-review.json'
            for path, obj in ((manifest_path, packet), (pin_path, old_pin), (review_path, review)):
                write_json(path, obj)
            with patch.object(coverage, '_MANIFEST_PATH', manifest_path), patch.object(coverage, '_PIN_PATH', pin_path), \
                 patch.object(coverage, '_PIN_SHA256', coverage._digest(old_pin)), \
                 patch.object(coverage, '_CURRENT_REVIEW_PATH', review_path), \
                 patch.object(coverage, '_CURRENT_REVIEW_SHA256', coverage._digest(review)), \
                 patch.object(coverage, '_CURRENT_PUBLICATION_ROOT', publication):
                yield cache, corpus, publication, review_path, manifest_path

    def assess(self, fixture):
        return coverage._assess_current_coverage(fixture[0], corpus_dir=fixture[1])

    def test_current_reference_and_independent_dimensions(self):
        with self.fixture() as f:
            report = self.assess(f)
            self.assertEqual(report['result'], 'ASSESSED')
            self.assertEqual(report['summary'], {'expected_configurations': 4, 'verified_numerical_configurations': 3,
                'published_documentary_only_configurations': 1, 'configurations_without_either_representation': 0,
                'configurations_lacking_faithful_numerical_representation': 1, 'numerically_complete': False})
            self.assertEqual(report['production_notice_coverage']['state'], 'unresolved')
            first = report['scenarios'][0]
            self.assertEqual(first['numerical_coverage'], {'state': 'absent', 'reason': 'non_exact_source_values', 'event_binding': None})
            self.assertEqual(first['documentary_coverage']['state'], 'published')
            bounds = [r for r in first['rows'] if r['result']['kind'] == 'strict_upper_bound']
            self.assertEqual([r['identity_id'] for r in bounds], ['nathalie-arthaud', 'karim-bouamrane'])
            self.assertTrue(all(r['result'] == {'kind': 'strict_upper_bound', 'literal': '<1%', 'upper_percent': 1.0} for r in bounds))
            self.assertEqual([s['respondent_bases']['expressed_certain_voters'] for s in report['scenarios']], [680, 518, 574, 603])
            self.assertTrue(all(s['documentary_coverage']['state'] == 'reviewed-only' for s in report['scenarios'][1:]))

    def test_current_missing_or_changed_pdf_never_claims_absence(self):
        for raw, state in ((None, 'unavailable'), (b'changed', 'changed')):
            with self.subTest(state=state), self.fixture() as f:
                path = f[0] / '10333.pdf'
                path.unlink() if raw is None else path.write_bytes(raw)
                report = self.assess(f)
                self.assertEqual(report['source_authentication']['state'], state)
                self.assertEqual(report['result'], 'REVIEW_REQUIRED')
                self.assertIsNone(report['summary']['numerically_complete'])
                self.assertIsNone(report['summary']['configurations_lacking_faithful_numerical_representation'])
                self.assertTrue(all(s['numerical_coverage']['state'] == 'unverified' for s in report['scenarios']))
                self.assertEqual(report['scenarios'][0]['documentary_coverage']['state'], 'published')

    def test_current_missing_or_changed_publication_inputs(self):
        names = ['poll_source_tables.json', 'poll_pages_manifest.json',
                 'sondages/documents/opinionway-cnews-10333/index.html',
                 'en/sondages/documents/opinionway-cnews-10333/index.html']
        for name in names:
            for missing in (True, False):
                with self.subTest(name=name, missing=missing), self.fixture() as f:
                    path = f[2] / name
                    path.unlink() if missing else path.write_text('{}', encoding='utf8')
                    report = self.assess(f)
                    self.assertEqual(report['result'], 'REVIEW_REQUIRED')
                    self.assertEqual(report['scenarios'][0]['documentary_coverage']['state'], 'unverified')
                    self.assertEqual(report['summary']['verified_numerical_configurations'], 3)
                    self.assertIsNone(report['summary']['configurations_without_either_representation'])

    def test_current_stale_complete_corpus_has_no_claims(self):
        mutations = [lambda es: es.pop(), lambda es: es[0].update(event_id='0' * 64),
                     lambda es: es[0].update(commissioner='Wrong'),
                     lambda es: es[0]['candidates'][0].update(score=30),
                     lambda es: es.append(dict(es[0], event_id='1' * 64))]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.fixture() as f:
                rows = coverage._read_json(f[1] / 'second_round_polls.json')
                mutation(rows['events'])
                write_json(f[1] / 'second_round_polls.json', rows)
                with self.assertRaises(coverage.CoverageDiagnosticError) as caught:
                    self.assess(f)
                self.assertEqual(caught.exception.code, 'BASELINE_STALE')
                self.assertNotIn('summary', caught.exception.details)
        with self.fixture() as f:
            (f[1] / 'polls.json').unlink()
            with self.assertRaises(coverage.CoverageDiagnosticError):
                self.assess(f)

    def test_current_duplicate_ids_rejected_even_in_attested_fixture(self):
        with self.fixture(lambda p, es, s, r: es.append(copy.deepcopy(es[0]))) as f:
            with self.assertRaisesRegex(coverage.CoverageDiagnosticError, 'Duplicate historical event ID'):
                self.assess(f)

    def test_current_duplicate_configuration_with_other_id_requires_review(self):
        with self.fixture(lambda p, es, s, r: es.append(dict(es[0], event_id='e' * 64))) as f:
            report = self.assess(f)
            self.assertEqual(report['result'], 'REVIEW_REQUIRED')
            self.assertEqual(report['scenarios'][1]['numerical_coverage']['state'], 'conflicting')
            self.assertIsNone(report['summary']['numerically_complete'])

    def test_current_conflicting_full_objects_and_sample_substitutions(self):
        changes = [('source_url', 'https://wrong.invalid'), ('pollster', 'Ifop'), ('commissioner', 'Wrong'),
                   ('publication_date', '2026-10-23'), ('sample_size', 731), ('sample_size', 518),
                   ('sample_scope', 'certain_to_vote'), ('fieldwork_end', '2026-10-23'),
                   ('population_id', 'wrong'), ('extra_metadata', 'changed')]
        for field, value in changes:
            with self.subTest(field=field, value=value), self.fixture(lambda p, es, s, r: es[0].update({field: value})) as f:
                report = self.assess(f)
                self.assertEqual(report['result'], 'REVIEW_REQUIRED')
                self.assertNotEqual(report['scenarios'][1]['numerical_coverage']['state'], 'verified')
        for value in (0, 0.5, True, '31'):
            with self.subTest(score=value), self.fixture(lambda p, es, s, r: es[0]['candidates'][0].update(score=value)) as f:
                self.assertEqual(self.assess(f)['result'], 'REVIEW_REQUIRED')

    def test_current_wrong_lineup_round_and_missing_bound_event(self):
        changes = [lambda es: es[0]['candidates'].pop(),
                   lambda es: es[0]['candidates'][0].update(name='Gabriel Attal'),
                   lambda es: es[0].update(round='first_round'), lambda es: es.pop(0)]
        for change in changes:
            with self.subTest(change=change), self.fixture(lambda p, es, s, r: change(es)) as f:
                report = self.assess(f)
                self.assertEqual(report['result'], 'REVIEW_REQUIRED')
                self.assertIsNone(report['summary']['configurations_lacking_faithful_numerical_representation'])

    def test_current_non_exact_source_cannot_verify_invented_or_omitted_rows(self):
        for invented in (0, 0.5, 1, '0', True, None):
            def change(packet, events, source, review):
                survey = next(s for s in packet['surveys'] if s['survey_id'] == 'commission:10333')
                rows = survey['scenarios'][0]['rows']
                event = {'event_id': 'f' * 64, 'pollster': 'OpinionWay', 'round': 'first_round',
                         'fieldwork_start': '2026-10-21', 'fieldwork_end': '2026-10-22', 'sample_size': 973,
                         'source_url': survey['accepted_source_urls'][0],
                         'candidates': [{'name': r['published_name'], 'score': r['result'].get('percent', invented)}
                                        for r in rows if invented is not None or r['result']['kind'] == 'exact']}
                events.append(event)
            with self.subTest(invented=invented), self.fixture(change) as f:
                report = self.assess(f)
                self.assertEqual(report['result'], 'REVIEW_REQUIRED')
                self.assertNotEqual(report['scenarios'][0]['numerical_coverage']['state'], 'verified')

    def test_current_documentary_semantic_conflicts_survive_collection_attestation(self):
        changes = [lambda t: t['source'].update(pdf_page=13), lambda t: t['source'].update(published_column='Brut'),
                   lambda t: t.update(commissioner='Wrong'), lambda t: t.update(institute='Ifop'),
                   lambda t: t['source'].update(pdf_sha256='0' * 64), lambda t: t['rows'].pop(),
                   lambda t: t['rows'][0].update(result={'kind': 'exact', 'percent': 0, 'literal': '0%'}),
                   lambda t: t['respondent_bases'][1].update(count=731),
                   lambda t: t.update(reviewed_scenario_id='10333-second_round-p13-1')]
        for change in changes:
            with self.subTest(change=change), self.fixture(lambda p, es, s, r: change(s['tables']['10333']['table'])) as f:
                report = self.assess(f)
                self.assertEqual(report['result'], 'REVIEW_REQUIRED')
                self.assertEqual(report['scenarios'][0]['documentary_coverage']['state'], 'unverified')

    def test_current_overlay_manifest_notice_and_identity_authentication(self):
        with self.fixture() as f:
            review = coverage._read_json(f[3]); review['scope'].append('commission:10319'); write_json(f[3], review)
            with self.assertRaisesRegex(coverage.CoverageDiagnosticError, 'overlay changed'):
                self.assess(f)
        with self.fixture() as f:
            packet = coverage._read_json(f[4]); packet['surveys'][0]['scenarios'].clear(); write_json(f[4], packet)
            with self.assertRaisesRegex(coverage.CoverageDiagnosticError, 'manifest changed'):
                self.assess(f)
        for field in ('content_sha256', 'commissioner', 'institute', 'resolved_url'):
            with self.subTest(field=field), self.fixture() as f:
                path = f[2] / 'commission_notice_registry.json'; registry = coverage._read_json(path)
                registry['notices'][0][field] = 'wrong'; write_json(path, registry)
                with self.assertRaisesRegex(coverage.CoverageDiagnosticError, 'notice identity changed'):
                    self.assess(f)
        with self.fixture() as f:
            original = Path.read_bytes
            def changed(path):
                return b'changed' if path == ROOT / 'fetch_polls.py' else original(path)
            with patch.object(Path, 'read_bytes', changed):
                with self.assertRaisesRegex(coverage.CoverageDiagnosticError, 'identity implementation changed'):
                    self.assess(f)

    def test_current_scope_inventory_and_binding_assignments_are_authenticated(self):
        for change in (lambda r: r.update(scope=['commission:10319']),
                       lambda r: r['scenarios'].pop(),
                       lambda r: r['scenarios'].append(copy.deepcopy(r['scenarios'][0])),
                       lambda r: r['scenarios'][1].update(reviewed_event_binding=r['scenarios'][2]['reviewed_event_binding']),
                       lambda r: r['scenarios'][0].update(pdf_page=13),
                       lambda r: r['scenarios'][0].update(published_column='Brut')):
            with self.subTest(change=change), self.fixture() as f:
                review = coverage._read_json(f[3]); change(review); write_json(f[3], review)
                with self.assertRaises(coverage.CoverageDiagnosticError):
                    self.assess(f)

    def test_current_route_registration_and_html_are_independently_verified(self):
        with self.fixture() as f:
            path = f[2] / 'poll_pages_manifest.json'; manifest = coverage._read_json(path)
            manifest['source_pages'].append(copy.deepcopy(manifest['source_pages'][0])); write_json(path, manifest)
            self.assertEqual(self.assess(f)['result'], 'REVIEW_REQUIRED')
        for fragment, replacement in [('Nathalie Arthaud', 'Wrong'), ('&lt;1%', '0%'),
                                      ('source-table-10333', 'scenario-1'), ('#page=12', '#page=13'),
                                      ('rel="canonical"', 'rel="alternate"')]:
            with self.subTest(fragment=fragment), self.fixture() as f:
                review = coverage._read_json(f[3]); pin = review['documentary']['pages']['fr']; path = f[2] / pin['relative_path']
                path.write_text(path.read_text(encoding='utf8').replace(fragment, replacement), encoding='utf8')
                pin['sha256_lf'] = hashlib.sha256(path.read_bytes()).hexdigest(); write_json(f[3], review)
                # Test-only new page attestation reaches semantic checks; never runtime repinning.
                with patch.object(coverage, '_CURRENT_REVIEW_SHA256', coverage._digest(review)):
                    self.assertEqual(self.assess(f)['result'], 'REVIEW_REQUIRED')

    def test_current_determinism_wrapper_order_and_cross_platform_pages(self):
        with self.fixture() as f:
            expected = self.assess(f)
            path = f[1] / 'second_round_polls.json'; obj = coverage._read_json(path)
            obj.update(events=list(reversed(obj['events'])), generated_at='wrapper only'); write_json(path, obj)
            for page in f[2].rglob('*.html'):
                page.write_bytes(page.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
            self.assertEqual(expected, self.assess(f))

    def test_current_cli_is_offline_read_only_and_never_generates_ids(self):
        import poll_contract
        with self.fixture() as f:
            before = {p: p.read_bytes() for p in f[0].parent.rglob('*') if p.is_file()}
            with patch('socket.socket.connect', side_effect=AssertionError('No network')), \
                 patch.object(Path, 'write_bytes', side_effect=AssertionError('No writes')), \
                 patch.object(Path, 'write_text', side_effect=AssertionError('No writes')), \
                 patch.object(poll_contract, 'make_event_id', side_effect=AssertionError('No new IDs')), \
                 patch.object(poll_contract, 'make_scenario_key', side_effect=AssertionError('No new keys')), \
                 contextlib.redirect_stdout(io.StringIO()) as stream:
                code = coverage._main(['--review', '10333-20261028', '--evidence-dir', str(f[0]), '--corpus-dir', str(f[1])])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stream.getvalue())['summary']['verified_numerical_configurations'], 3)
            self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_current_cli_stale_and_unverified_do_not_emit_success(self):
        for stale in (True, False):
            with self.subTest(stale=stale), self.fixture() as f:
                write_json(f[1] / 'second_round_polls.json', {'events': []}) if stale else (f[0] / '10333.pdf').unlink()
                with contextlib.redirect_stdout(io.StringIO()) as stream:
                    code = coverage._main(['--review', '10333-20261028', '--evidence-dir', str(f[0]), '--corpus-dir', str(f[1])])
                output = json.loads(stream.getvalue())
                self.assertEqual(code, 2)
                self.assertNotEqual(output['result'], 'ASSESSED')
                if stale:
                    self.assertNotIn('scenarios', output)
                    self.assertNotIn('summary', output)


if __name__ == '__main__':
    unittest.main()
