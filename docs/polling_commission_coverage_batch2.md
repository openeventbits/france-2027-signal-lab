# Commission polling coverage — Batch 2 review

Implementation base: `8c727f2fb30091f295d5508f53a54e5c6f4780c9`; branch `codex/polling-commission-batch2`. Uncommitted proposal; no production workflow, commit, push or PR.

## Decision

Admit exactly two OpinionWay/CNews first-round configurations. Preserve all 437 existing event objects exactly. Reconcile nine of the twelve previously unresolved notices through exact reviewed evidence; retain three unresolved notices. First round: 335 → 337; runoff: 102 → 102; total: 437 → 439. Relevant Commission notices: 37; parsed: 3 unchanged; reconciled: 22 → 31; unresolved: 12 → 3.

The original twelve PDFs were downloaded from the exact registry paths over HTTPS, and all twelve byte-level SHA-256 values matched the recorded evidence. The audit visually inspected 64 Commission methodology/result pages, including complete current-wave recap tables, plus the two original Cluster17 reports. Questionnaire hypotheses, retrospective charts, recalled earlier waves and vote transfers are not additional observations. PDF page references below are one-based file pages, not assumed printed pagination.

Complete literal candidate/score transcriptions for all 79 current-wave configurations, source pages and distinct sample bases are in [the independent source-table fixture](../test_fixtures/fr27_polling/batch2_original_tables.json). The [review registry](../fr27_commission_coverage_batch2.json) pins the exact twelve notice identities, complete published object collections, both Cluster17 representations and two admission decisions. These are reviewed evidence snapshots, not generated production datasets.

## Twelve-notice decision matrix

T1/T2 denote first-round/runoff configuration counts. Every notice was unresolved before this patch. Counts describe published observations; the JDD legacy objects are expressly not faithful source matches.

| Notice; institute / commissioner; fieldwork (2026) | Original evidence pages | Published coverage before → after | Admission/correction; final decision |
|---|---|---|---|
| [10305](https://www.commission-des-sondages.fr/notices/files/notices/2026/octobre/10305-pres-iv-toluna-harris-interactive-12-octobre.pdf); Harris Interactive / M6 & RTL; 2026-10-05–2026-10-08 | method 3; first-round recap 33, individual 34/37/40/43/46; runoff recap 51, individual 52/55 | 5 T1 / 2 T2 → 5 T1 / 2 T2 | **reconciled**. All five first-round and two runoff configurations already exist under Harris. Exact official table matches; the missing-coverage warning is not a missing survey. |
| [10277](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10277-pres-toluna-harris-interactive-rtl-28-septembre.pdf); Harris Interactive / M6 & RTL; 2026-09-22–2026-09-24 | method 3; first-round recap 34, individual 35/38/41/44/47; runoff recap 52, individual 53/56 | 5 T1 / 2 T2 → 5 T1 / 2 T2 | **reconciled**. All five first-round and two runoff configurations already exist under Harris. Exact official table matches; no observation is admitted. |
| [10263](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10263-pres-iv-toluna-harris-interactive-rtl-14-septembre.pdf); Harris Interactive / M6 & RTL; 2026-09-08–2026-09-10 | method 3; first-round recap 33, individual 34/37/40/43/46; runoff recap 51, individual 52/55/58 | 5 T1 / 3 T2 → 5 T1 / 3 T2 | **reconciled**. All five first-round and three runoff configurations already exist under Harris. Exact official table matches; no observation is admitted. |
| [10264](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10264-pres-opinionway-facebook-15-septembre.pdf); OpinionWay / Sébastien Bonnal; 2026-09-02–2026-09-04 | method 3; first round 12 | 0 T1 / 0 T2 → 0 T1 / 0 T2 | **unresolved**. Sébastien Bonnal is published as <1%. The numeric score contract cannot faithfully encode a bound. No admission; the actual commissioner is Sébastien Bonnal, not the Facebook listing label. |
| [10260](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10260-pres-iv-opinionway-cnews-11-septembre.pdf); OpinionWay / CNews; 2026-09-09–2026-09-10 | method 3; first round 12–14; runoff 15–16 | 0 T1 / 2 T2 → 2 T1 / 2 T2 | **unresolved**. Two numeric first-round configurations are admitted. The third publishes Nathalie Arthaud and Karim Bouamrane as <1%, so full coverage remains unresolved. Both existing runoffs are exact matches and remain unchanged. |
| [10273](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10273-pres-iv-cluster17-politico-24-septembre.pdf); Cluster17 / Politico; 2026-09-15–2026-09-16 | method 2; first round 14–16; institute report method 2, first round 5/10/15 | 3 T1 / 0 T2 → 3 T1 / 0 T2 | **reconciled**. Complete three-configuration survey. Exact paired evidence: notice Redressé values at one decimal and the institute public report at published rounded precision. Preserve all original scores, samples and source URLs; no inferred rounding tolerance or global equivalence. |
| [10251](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10251-pres-iv-cluster-17-le-point-5-septembre.pdf); Cluster17 / Le Point; 2026-08-31–2026-09-01 | method 2; first round 19–21; institute report method 2, first round 6/11/16 | 3 T1 / 0 T2 → 3 T1 / 0 T2 | **reconciled**. Complete three-configuration survey. Exact paired evidence: notice Redressé values at one decimal and the institute public report at published rounded precision. Preserve the historical adult-sample representation and all event objects; no inferred rounding rule. |
| [10323](https://www.commission-des-sondages.fr/notices/files/notices/2026/octobre/10323-pres-iv-yougov-le-huffpost-18-octobre.pdf); YouGov / Le HuffPost; 2026-10-12–2026-10-15 | method 4; first round 20–24; runoff 26–28, Pondérés columns | 5 T1 / 6 T2 → 5 T1 / 6 T2 | **reconciled**. All five first-round and six runoff tables match the Pondérés column exactly, including explicit zero values. Preserve legacy adult-sample representations; raw and weighted decided-voter bases are separately recorded. |
| [10270](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10270-pres-iv-yougov-huffpost-23-septembre.pdf); YouGov / Le HuffPost; 2026-09-17–2026-09-21 | method 4; first round 21–26; runoff 28–30, Pondérés columns | 6 T1 / 6 T2 → 6 T1 / 6 T2 | **reconciled**. All six first-round and six runoff tables match the Pondérés column exactly. Preserve legacy adult-sample representations; no trend or recalled result is admitted. |
| [10250](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10250-pres-iv-ipsos-bva-le-parisien-5-septembre.pdf); Ipsos / Le Parisien; 2026-08-31–2026-09-02 | method 2/4; first-round recap 12, individual 13/15/17/19/21/23 | 6 T1 / 0 T2 → 6 T1 / 0 T2 | **reconciled**. All six current first-round configurations match the original tables. June comparisons and vote-transfer tables are not new observations. The overall sample is 1500 registered voters; expressed certain-voter bases vary by configuration. |
| [10242](https://www.commission-des-sondages.fr/notices/files/notices/2026/aout/10242-pres-barometre-election-pres-iv-v5-ifop-26-aout.pdf); Ifop / LCI, Le Figaro et Sud Radio; 2026-08-24–2026-08-25 | method 2; first round 9–15; runoff 16–21 | 7 T1 / 6 T2 → 7 T1 / 6 T2 | **reconciled**. All seven first-round and six runoff tables match the original notice. The method gives 1598 registered voters from 1800 adults and 24-25 August. Record expressed and certain-expressed bases without changing historical events. |
| [10205](https://www.commission-des-sondages.fr/notices/files/notices/2026/juin/10205-pres-iv-opinionway-jdd-13-juin.pdf); OpinionWay / Le Journal du Dimanche; 2026-06-10–2026-06-11 | method 3; first round 12–14 | 3 T1 / 0 T2 → 3 T1 / 0 T2; three legacy individual RN objects retained, zero exact composite matches | **unresolved**. All three official tables test one composite option: Le candidat du RN, Marine Le Pen ou Jordan Bardella. Existing events assign those scores to Jordan Bardella. No exact candidate-identity match is defensible; do not relabel or supersede historical events without a separate composite-option contract review. |

The Harris label is already normalized to Harris Interactive by the existing pollster identity contract. All fifteen Harris first-round and seven Harris runoff observations match the complete official tables. No new Harris record or institute alias rule is needed.

Cluster17 Commission `Redressé` values have one decimal; the institute reports publish integer/half-point values. Each of the six complete configurations is paired explicitly with its corresponding original public report. Existing FR27 values match those public reports exactly. The review does not apply an inferred rounding function, tolerate arbitrary score differences, or rewrite sample metadata. The Le Point legacy sample of 1,711 adults is retained; it is not asserted to be the expressed-vote denominator.

The three remaining warnings are intentional: 10264 publishes Sébastien Bonnal `<1%`; 10260 hypothesis 3 publishes both Nathalie Arthaud and Karim Bouamrane `<1%`; 10205 tests one composite “Le candidat du RN, Marine Le Pen ou Jordan Bardella” option. Numeric scores cannot represent a bound, and an individual candidate identity cannot represent that composite option faithfully. No zero, half-point, candidate substitution, or silent historical correction is introduced. These require separate, explicit contract reviews before admission or supersession. The Bonnal PDF names Sébastien Bonnal as commissioner; the registry listing says Facebook. Both facts are retained as distinct evidence. Its generic page-2 sample template is not substituted for the actual methodology/results.

## Two admissions and lineage

Both decisions use the exact notice 10260 identity/hash, 9–10 September fieldwork, CNews commissioner, 935 registered voters (`sample_scope=registered_voters`), complete thirteen-candidate tables, and total 100%. The adult parent sample is 1,001; 690 respondents say they are certain to vote. The notice does not supply a separate expressed-vote count, so none is invented. Publication date remains null; the notice listing date is not asserted to be the survey publication date. Previous event is null for both admissions; no historical event is superseded.

| Decision / full event ID | Page | Complete candidate-score list (%) |
|---|---|---|
| `FR27-B2-10260-H1` / `34b67c973777cf14f9c19068b4642d119367e3312053f442ba16e9612c051cac` | 12 | Nathalie Arthaud 1; Jean-Luc Mélenchon 16; Fabien Roussel 3; Marine Tondelier 3; François Hollande 7; Karim Bouamrane 1; Gabriel Attal 8; Édouard Philippe 16; Bruno Retailleau 7; David Lisnard 2; Nicolas Dupont-Aignan 2; Éric Zemmour 2; Marine Le Pen 32 |
| `FR27-B2-10260-H2` / `547d14cf13fb2f407e743b91f6347dad9c0a3db48e750b380bdfc27b8fede2cd` | 13 | Nathalie Arthaud 1; Jean-Luc Mélenchon 17; Fabien Roussel 4; Marine Tondelier 3; Ségolène Royal 3; Karim Bouamrane 1; Gabriel Attal 8; Édouard Philippe 16; Bruno Retailleau 7; David Lisnard 2; Nicolas Dupont-Aignan 3; Éric Zemmour 2; Marine Le Pen 33 |

## Sample semantics

Historical published sample fields remain unchanged. Coverage reconciliation means that the complete source-backed configurations are represented; it does not certify a historical `reported` sample as a matchup denominator. Registered-voter parent samples, certain-voter subsets, expressed-vote counts, weighted counts and effective samples are recorded separately in the source fixture.

| Notice | Adults / registered voters | Configuration-specific source bases |
|---|---|---|
| 10305 | 2348 / 2004 | T1 p34: certain_to_vote_and_expressed=1285; T1 p37: certain_to_vote_and_expressed=1274; T1 p40: certain_to_vote_and_expressed=1264; T1 p43: certain_to_vote_and_expressed=1267; T1 p46: certain_to_vote_and_expressed=1251; T2 p52: certain_to_vote_and_expressed=1093; T2 p55: certain_to_vote_and_expressed=1156 |
| 10277 | 2334 / 1974 | T1 p35: certain_to_vote_and_expressed=1242; T1 p38: certain_to_vote_and_expressed=1227; T1 p41: certain_to_vote_and_expressed=1216; T1 p44: certain_to_vote_and_expressed=1219; T1 p47: certain_to_vote_and_expressed=1223; T2 p53: certain_to_vote_and_expressed=1055; T2 p56: certain_to_vote_and_expressed=1125 |
| 10263 | 2358 / 2052 | T1 p34: certain_to_vote_and_expressed=1339; T1 p37: certain_to_vote_and_expressed=1317; T1 p40: certain_to_vote_and_expressed=1304; T1 p43: certain_to_vote_and_expressed=1309; T1 p46: certain_to_vote_and_expressed=1312; T2 p52: certain_to_vote_and_expressed=1116; T2 p55: certain_to_vote_and_expressed=1178; T2 p58: certain_to_vote_and_expressed=1174 |
| 10264 | 1034 / 951 | T1 p12: certain_to_vote=700, expressed_respondents=undocumented |
| 10260 | 1001 / 935 | T1 p12: certain_to_vote=690, expressed_respondents=undocumented; T1 p13: certain_to_vote=690, expressed_respondents=undocumented; T1 p14: certain_to_vote=690, expressed_respondents=undocumented; T2 p15: certain_to_vote=690, expressed_respondents=undocumented; T2 p16: certain_to_vote=690, expressed_respondents=undocumented |
| 10273 | 2045 / 1943 | T1 p14: expressed_respondents=1733, effective_sample_after_weighting=1337; T1 p15: expressed_respondents=1723, effective_sample_after_weighting=1342; T1 p16: expressed_respondents=1729, effective_sample_after_weighting=1341 |
| 10251 | 1711 / 1628 | T1 p19: expressed_respondents=1459, effective_sample_after_weighting=1150; T1 p20: expressed_respondents=1451, effective_sample_after_weighting=1131; T1 p21: expressed_respondents=1491, effective_sample_after_weighting=1211 |
| 10323 | 1094 / 976 | T1 p20: raw_decided_expressed=725, weighted_decided_expressed=689; T1 p21: raw_decided_expressed=713, weighted_decided_expressed=680; T1 p22: raw_decided_expressed=721, weighted_decided_expressed=683; T1 p23: raw_decided_expressed=708, weighted_decided_expressed=666; T1 p24: raw_decided_expressed=734, weighted_decided_expressed=696; T2 p26: raw_decided_expressed=653, weighted_decided_expressed=612; T2 p26: raw_decided_expressed=672, weighted_decided_expressed=616; T2 p27: raw_decided_expressed=669, weighted_decided_expressed=633; T2 p27: raw_decided_expressed=605, weighted_decided_expressed=552; T2 p28: raw_decided_expressed=641, weighted_decided_expressed=610; T2 p28: raw_decided_expressed=488, weighted_decided_expressed=473 |
| 10270 | 1103 / 1008 | T1 p21: raw_decided_expressed=719, weighted_decided_expressed=646; T1 p22: raw_decided_expressed=729, weighted_decided_expressed=653; T1 p23: raw_decided_expressed=719, weighted_decided_expressed=641; T1 p24: raw_decided_expressed=707, weighted_decided_expressed=636; T1 p25: raw_decided_expressed=733, weighted_decided_expressed=658; T1 p26: raw_decided_expressed=739, weighted_decided_expressed=669; T2 p28: raw_decided_expressed=685, weighted_decided_expressed=618; T2 p28: raw_decided_expressed=679, weighted_decided_expressed=583; T2 p29: raw_decided_expressed=687, weighted_decided_expressed=611; T2 p29: raw_decided_expressed=647, weighted_decided_expressed=572; T2 p30: raw_decided_expressed=656, weighted_decided_expressed=582; T2 p30: raw_decided_expressed=476, weighted_decided_expressed=480 |
| 10250 | not separately documented / 1500 | T1 p13: certain_to_vote_and_expressed=1020; T1 p15: certain_to_vote_and_expressed=1005; T1 p17: certain_to_vote_and_expressed=999; T1 p19: certain_to_vote_and_expressed=1004; T1 p21: certain_to_vote_and_expressed=992; T1 p23: certain_to_vote_and_expressed=979 |
| 10242 | 1800 / 1598 | T1 p9: registered_and_expressed=1188, certain_to_vote_and_expressed=930; T1 p10: registered_and_expressed=1158, certain_to_vote_and_expressed=920; T1 p11: registered_and_expressed=1141, certain_to_vote_and_expressed=909; T1 p12: registered_and_expressed=1176, certain_to_vote_and_expressed=925; T1 p13: registered_and_expressed=1144, certain_to_vote_and_expressed=898; T1 p14: registered_and_expressed=1122, certain_to_vote_and_expressed=889; T1 p15: registered_and_expressed=1100, certain_to_vote_and_expressed=872; T2 p16: registered_and_expressed=1150, certain_to_vote_and_expressed=883; T2 p17: registered_and_expressed=1105, certain_to_vote_and_expressed=850; T2 p18: registered_and_expressed=949, certain_to_vote_and_expressed=731; T2 p19: registered_and_expressed=1107, certain_to_vote_and_expressed=860; T2 p20: registered_and_expressed=1117, certain_to_vote_and_expressed=870; T2 p21: registered_and_expressed=940, certain_to_vote_and_expressed=720 |
| 10205 | 1001 / 901 | T1 p12: certain_to_vote=683, expressed_respondents=undocumented; T1 p13: certain_to_vote=683, expressed_respondents=undocumented; T1 p14: certain_to_vote=683, expressed_respondents=undocumented |

## Original document hashes

| Notice | SHA-256 of original Commission PDF |
|---|---|
| [10305](https://www.commission-des-sondages.fr/notices/files/notices/2026/octobre/10305-pres-iv-toluna-harris-interactive-12-octobre.pdf) | `71bea2f6ee85ee22834fac0f9ead6d49d867638201900e3f215ecb8119b49891` |
| [10277](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10277-pres-toluna-harris-interactive-rtl-28-septembre.pdf) | `0d26bc056a317f25dc9fea3941afc15fbe88e3910db29e6966e26734014b972b` |
| [10263](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10263-pres-iv-toluna-harris-interactive-rtl-14-septembre.pdf) | `2d1abda237d6968b847a7ea117afca4f3b5621386199dcbb4097f1bd66d7fba7` |
| [10264](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10264-pres-opinionway-facebook-15-septembre.pdf) | `3e427407804098116e859a47f1ba3b0d0428145714b35c593e900e800768cd27` |
| [10260](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10260-pres-iv-opinionway-cnews-11-septembre.pdf) | `bcc6f5e46048615f31188b9d98cd708339f276e8fe959d3c9c1b5833a1d58b0c` |
| [10273](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10273-pres-iv-cluster17-politico-24-septembre.pdf) | `67f0106bf17e6de74fa4728fb50d1917b3bb99dcb8240500785de2805eb1e7b1` |
| [10251](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10251-pres-iv-cluster-17-le-point-5-septembre.pdf) | `26e5ace08cfb1237a22fca5f00facab844ea2c4d1c18c04f137064e745454175` |
| [10323](https://www.commission-des-sondages.fr/notices/files/notices/2026/octobre/10323-pres-iv-yougov-le-huffpost-18-octobre.pdf) | `4b2b38114f43bb35521323604842ca8266855c1ac6fd3cb2adc78df442aa9393` |
| [10270](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10270-pres-iv-yougov-huffpost-23-septembre.pdf) | `4b95c5d1ca180dac1117629532518aaa14e47c71619ad70e002e357386dd24ce` |
| [10250](https://www.commission-des-sondages.fr/notices/files/notices/2026/septembre/10250-pres-iv-ipsos-bva-le-parisien-5-septembre.pdf) | `85895ae3d08bb74da9c0da8f6be6ab409607207525f85ce35268c86c4433fc90` |
| [10242](https://www.commission-des-sondages.fr/notices/files/notices/2026/aout/10242-pres-barometre-election-pres-iv-v5-ifop-26-aout.pdf) | `cb6eb35f5e1f2ff84a400ed3beb81ed665ae47b693aa646ed9dbdd4290f60cbb` |
| [10205](https://www.commission-des-sondages.fr/notices/files/notices/2026/juin/10205-pres-iv-opinionway-jdd-13-juin.pdf) | `c22521b061c86f448e5779fdfb89bf1728c6100efc837775d39b70ec72c0a90d` |

Cluster17 commission:10273: [original institute report](https://cluster17.com/wp-content/uploads/2026/09/Intentions-de-vote-P27-Politico-Septembre-26.pdf), SHA-256 `f8c6c2eabab2b9b7226fe6b4c361cdd1f69f965419e5c5629acd5e82ccfd92ee`. Complete result-page references are in the matrix and per-configuration source fixture; the Le Point pages 6/11/16 were rendered and inspected separately from the initial methodology render.

Cluster17 commission:10251: [original institute report](https://cluster17.com/wp-content/uploads/2026/09/C17_Le_Point_Sondage_Election_Presidentielle_2027_Sep26-.pdf), SHA-256 `2153a3ed0d02c830dda9919f3cefe77671ad5ab60e43c6c9d0cf86b65219a4d6`. Complete result-page references are in the matrix and per-configuration source fixture; the Le Point pages 6/11/16 were rendered and inspected separately from the initial methodology render.

## Exact event evidence

The following complete pre-existing object collections are pinned in the review. All are retained exactly, including the three conflicting JDD objects, which are evidence of the unresolved identity problem rather than approved composite matches. The two admission IDs are listed above. There are no Batch 2 predecessor/successor pairs.

### commission:10305

- `003ea41284c91407011bf3d22784e12600f439baa1cb2600b354cbe5918769a1` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Gabriel Attal, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `6e60fb9acfdb11ec72dddbe7f6e37dd88ba685fa7703e445d5cb30f16b2364a2` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `7d509c935fca987cfeb13a06132d9e23cd97ff2339f3ebba3c048b93a0dc4c06` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, François Hollande, Gabriel Attal, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `a0670f44b3422b262d409b4e87a311b1a13e481433fb933b3c636a557934ccb9` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Gabriel Attal, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `c7c4b9d7ca3c2b391585d3e570b4f882702335f1ce10b54bea09c4f1caba9e56` — second_round; Édouard Philippe, Marine Le Pen.
- `e0534cb4f3bef4fd65d0e6d9fceb340db4d7e528b08eff106e1b400b0d24d5ec` — second_round; Jean-Luc Mélenchon, Marine Le Pen.
- `ff997ba2744a25e14270f76945f0c766519f16bfd7b916c83f25287bc063cb91` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, François Hollande, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
### commission:10277

- `0fd5c8b9d085207d29bdebeb98ea386cba41271d25c2f3180f883c52667cf4da` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Gabriel Attal, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `20e56fe5b9df0f5fd17b6485cd112c0e319d0b64f81c384f77b28466abecffab` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `9b5efcf3ce2f9c78f0a1062fae39885576331ab02276a40a866513c59266bf60` — second_round; Édouard Philippe, Marine Le Pen.
- `9ef2d586bf1801408ff5f178a1698009e2afda44eaba974c4ed81f58e4c8e871` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, François Hollande, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `a192ada6e8e89934f05741ed3f50e36bcf1ab310d3820dc9c96f032a9507683f` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Gabriel Attal, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `b7994cbbcfaac06ef75941727d726a528e11da31412a459a121cf2ecbba3bd7e` — second_round; Jean-Luc Mélenchon, Marine Le Pen.
- `c7792c80a8992c1356d86afd25336890d7e166fc67f6b031cf7238b22ac0dd16` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, François Hollande, Gabriel Attal, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
### commission:10263

- `14f2d363876c8ed64b648958b755841fbfad8f508e3bd6ac12d0cf532782742e` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, François Hollande, Gabriel Attal, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `3856921029f4934d7a6894fe7cf1e9150e440bc8b5042fdc3b43b2a1998b377c` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Gabriel Attal, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `3a92e667319480e8c55d00780463415740ade96a9eaa09f3d611caa13984430f` — second_round; Jean-Luc Mélenchon, Marine Le Pen.
- `623ea1ced88c579ea8b8467ab9660c750db170db14c65ce226e4cff08b9cffd3` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, François Hollande, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `74be88dd54c260b901e0996928e118869bd67ea0fbd5f46acea0db8c6f4ba41c` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `82509b8b622835bce52f36c47c4179b281dc6fb71b4afbdf3830f6be8fa4dc09` — second_round; Édouard Philippe, Marine Le Pen.
- `be671844a99b635ba38079bae2bebbe482a910a6735cb5e6e37ede5bcd92e53d` — second_round; Gabriel Attal, Marine Le Pen.
- `f6e83c14109c85f81e240329e6d85b2f42402908fdc908f14a14687ae7030da7` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Gabriel Attal, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
### commission:10264

No published predecessor observations.
### commission:10260

- `74f414c18b471202a9e99991b3aef62a3765aab33af40c333c19c1275ef7cd67` — second_round; Jean-Luc Mélenchon, Marine Le Pen.
- `fdf663f564346145574ec28b75f4f9810bc2501065aa6790f9fb014e9148eea4` — second_round; Édouard Philippe, Marine Le Pen.
### commission:10273

- `440af5d658d87f19584558c1fd5f5772e6815ce9f5330cf487554be876e4337c` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Gabriel Attal, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `5d3b7a892d22e89eb0e41f0f7ef2029056d436d77458a1987ee64bcb4a12170f` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `dbd4d0a0c168b8dd853117aef7d9963a57054f2eaf520dea0842c0aa4e15e289` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, François Hollande, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, David Lisnard.
### commission:10251

- `3343a3f579673a9c6d739c692fd3f409fd2ef0ebbdb11775ba881b7b51d63263` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Édouard Philippe, Dominique de Villepin, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `4810851ea958b928b63298fa94fb082afc6cc7d449b2aad41f023953bb1aac36` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, François Ruffin, Raphaël Glucksmann, Édouard Philippe, Dominique de Villepin, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour, David Lisnard.
- `76e77f1828ffae02a34ee1de2e4cf1668ab77c5e5611dfbb6d0c7b57bfb84752` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Gabriel Attal, Dominique de Villepin, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
### commission:10323

- `297cedfc0e854593c3013d5bfddc7b76bd366a6701ba2bd73aa5762d853c1572` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Gabriel Attal, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `2e6a90806a3a9ba63b210a8254e9948932a669851598e41f40fc5282b6326153` — second_round; Gabriel Attal, Marine Le Pen.
- `69933addd5206c5b47593f35e1676e2fa1e8042a3a3a8c37feb2d00b1b29f37a` — second_round; Jean-Luc Mélenchon, Marine Le Pen.
- `6d9731a8f7039402b668307735c7446686f353d00806a162cab200e80d176e51` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `6e23ed69179c8a59fa4b665fa2191b7385510400d5762056d559bb1ba0531a6a` — second_round; Raphaël Glucksmann, Marine Le Pen.
- `78cbfabfad83f8a973d596f06987a5f1ac1463658c2e7114f6e1096e99060352` — second_round; Édouard Philippe, Marine Le Pen.
- `9b43ed344c441fa1cd738bf0bd54cc90d8460a8640373cc5bcc3d34ef7150767` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, François Hollande, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `a79541851a8b05303d44d7a6bec119dd4cb37fdefa46e07f520e0a80e3c4cf02` — second_round; François Hollande, Marine Le Pen.
- `a8b5d1cac12f97bb852a3da38204cd52aca008eed9be5a4e17938411bff29166` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Gabriel Attal, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `bd55e05410eeeda6271e16babdf6d3da958fcacf058991fa086d4544cb2e82d6` — second_round; Jean-Luc Mélenchon, Édouard Philippe.
- `c787431f293e9e743e53144858f9e6aa5d3bdba2b0e8de4f337ac5ad6081bb79` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Gabriel Attal, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour, David Lisnard, François Ruffin, Dominique de Villepin.
### commission:10270

- `0afbaa084764711d790a215088f938b11d1db89e223edbdb3aa78b3a28e616d6` — second_round; Raphaël Glucksmann, Marine Le Pen.
- `1412effcb1a765a0a56850a8e0dd842a4b05deb976d158efbb31a0ada85168f0` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Gabriel Attal, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `1f31b9d7b29539f7b45871ad254f8db4977fa12271dbe83dc1ed876d930c68a9` — second_round; Édouard Philippe, Marine Le Pen.
- `44a6411d5cbb73e264613fcd90f0857576049bd039fd189db6c10e5028eda108` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, François Hollande, Raphaël Glucksmann, Gabriel Attal, Édouard Philippe, Dominique de Villepin, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour, David Lisnard, François Ruffin, Xavier Bertrand.
- `649b93dfc310012f1f34105bae182dffec0aa88f919d267b4595e4c4291b42b1` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `7e2c238b851f64c11214c4bff0c0b1f7c7fbd4e7b78aa139b50603406aac6d10` — second_round; Gabriel Attal, Marine Le Pen.
- `c6c882f4d4d3108b9544da4bc3947ab152df456e9a4ceb08cea1054cb5d4b3d1` — second_round; François Hollande, Marine Le Pen.
- `cf0f5ec68eed02381f89b59e5e8dba1d6ccd2c81a4f3c99e504e2415e5e681d2` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Olivier Faure, Gabriel Attal, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `e3bd315da43ee17ba8179519e0a3cde4f8331d975d62c742f145bb492a4c25fb` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Bruno Le Maire, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `efe2df66960c4fac5d251f9c237750c79602de51a25dcd03b84cf24095525a4d` — second_round; Jean-Luc Mélenchon, Marine Le Pen.
- `f6df923b62a79fa7df1d65b9a8223650eb172610c1282b09587fbbbf440b7721` — second_round; Édouard Philippe, Jean-Luc Mélenchon.
- `fce9f5e59dc2dc1d26b53f7c8aa5551ab862c7ce78140cfe3ce0f5d36b5d46f1` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Gabriel Attal, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
### commission:10250

- `167b7ca5bdc5958c8f9b17ab81d2575164b2b2399a3dcada437a950554f776ab` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Olivier Faure, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `5fb7463e879a2fc782072c7e41434af61b2c84ba2e8b119f671ad5dc2212590a` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `a32116c38a51ee5a6313ffa7951c8c1bca247f8bcdefb208bfa34b053a8e4ffb` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Gabriel Attal, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `ae32fa4e5db242ed30e9e54e03bed1915cda611ab3425778e946cb96a15f3253` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Olivier Faure, Gabriel Attal, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `b956766bee4fc2795b19e81a23c80f4c10356d547e07aa4e86825e6e2786f443` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Gabriel Attal, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `d53000c5d264f54d11fe1522b92570966c91fcd335f32887b4461e474d7732a7` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Olivier Faure, Gabriel Attal, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
### commission:10242

- `42057803cafd0dd60425e7403ab080f40db330577c81fdcee13f796f08fa0d47` — second_round; Édouard Philippe, Marine Le Pen.
- `50d70dee6001288aaf3cf3827f8cbf3611b8f5cb1b10a14da39272e4f1d92dee` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Bruno Le Maire, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `5e17ffb709c3ae023fa4c2a75eb554400d1272b66c41470bfd1413edc6a3165c` — second_round; Bruno Retailleau, Marine Le Pen.
- `71646f271cd5c859cd45d2c1b3f3768d2abaec197459765017f9e12c8af736b3` — second_round; Jean-Luc Mélenchon, Marine Le Pen.
- `b629f5c7183cac0aefdb2a985bbd2c5874a0564f32644666978d12beff5c8fbb` — second_round; Raphaël Glucksmann, Marine Le Pen.
- `bc4cf6190fcb87af8b27a5da77340df2f32951702651dd4c20a2910a6cc692ee` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, François Hollande, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `bed2677cbae4b104f50a80e33de7da58f5dcef62d4cb20cb34ba7dbeaf57cd76` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Gabriel Attal, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `d099fb9efc87034acc97bc44a5078110b252b5882e02627cc9491d88b3355c07` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Raphaël Glucksmann, Gabriel Attal, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `eea476922917752cddf86b35b97df9b776556536bc7721a36825b76f02e6a35c` — second_round; François Hollande, Marine Le Pen.
- `f10cddfb79ebff7ca0dd9d6e9afb4ec75cf9d4b97ba3033a0a86147a2a358793` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Raphaël Glucksmann, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `faaa3931b3ebfb248a9d38780db337f9f4a6322deab5bf53800611769eeb0361` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Gabriel Attal, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `fcddf261fdcb1633df374b1d6559a8b12523a81faea1918b5ee1927a8ea23eca` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Marine Le Pen, Éric Zemmour.
- `fe2206dee2e7378d2d397fb1e42b087ae7ffebe3da2a6469372c37bd345df213` — second_round; Gabriel Attal, Marine Le Pen.
### commission:10205

- `18c3f04dfcd854092bfaddba00a48f75bb6c129f483507dc9f880a1065657210` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Gabriel Attal, Bruno Retailleau, Nicolas Dupont-Aignan, Jordan Bardella, Éric Zemmour.
- `97585f1475829d9d8af92d50051dc40d3fc7e515c8c5bed45e8ce8c5c9f50085` — first_round; Nathalie Arthaud, Jean-Luc Mélenchon, Fabien Roussel, Marine Tondelier, Raphaël Glucksmann, Édouard Philippe, Bruno Retailleau, Nicolas Dupont-Aignan, Jordan Bardella, Éric Zemmour.
- `992208751ce22334e7b107c86d1b2cf2bf0ab411fcb4bd97df1bf6bde8734900` — first_round; Arthaud, Mélenchon, Raphaël Glucksmann, Philippe, Retailleau, Dupont-Aignan, Bardella, Zemmour.

## Batch 1 live source-drift diagnosis and compatibility review

The first temporary live fetch failed before Batch 2 ran: `Batch 1 reviewed source facts/provenance changed`. Saved French Wikipedia revision 240569682 cites a newly available Commission original for Ifop October: [notice 10327](https://www.commission-des-sondages.fr/notices/files/notices/2026/octobre/10327-pres-barometre-election-v7-ifop-20-octobre.pdf), SHA-256 `39b82377458a44db5c7de3ad95ca4f7938f87dd791163083206538c32795fac5`.

The exact new URL was absent from the six initially affected Batch 1 source variant lists. During verification, revision 240570516 added the Ruffin–Polony table and corrected the Hollande discovery score to 2%, producing two further exact variants affecting seven decisions in total. Every incoming factual key already existed under another reviewed source URL. The new PDF was independently inspected: methodology p2 establishes 17–19 October, 1,928 registered voters from 2,081 adults; Hollande p13 gives Dupont-Aignan 2%; Ruffin–Polony p16 verifies all thirteen scores including Polony 1%; runoffs pp17–21 give Mélenchon 32/68, Glucksmann 43/57, Hollande 41/59, Attal 42/58, Philippe 44/56 against Marine Le Pen. Known Wikipedia sample/score errors are not adopted as canonical facts.

`FR27-B2-IFOP-SOURCE-10327` explicitly appends only these eight exact `(factual key, source URL)` discovery variants to the existing Batch 1 mechanism. The guard implementation is unchanged; its canonical JSON pin is updated for that evidence review. No URL wildcard, source alias rule, tolerance, new event, or additional notice coverage reconciliation is introduced. Removing those eight appended variants and the new review reconstructs the exact original Batch 1 registry digest `ecce41bfd0ff61dc30fd8003c8fea2ae5fc43e21743922f735b2b3eda4db207b`.

| Source locator | Batch 1 decision | Evidence page | Canonical event ID (unchanged) | Incoming distinction |
|---|---|---|---|
| `FR-R3r1` | `FR27-B1-D-Jean-Luc Mélenchon` | 17 | `115ff210edfe581876a9fae703475ecec7f608b2312df5d2ce64941e7ec4117a` | Scores and 17–19 October dates agree; discovery still labels 2,081 adults as reported. Retain the reviewed 1,928 registered-voter successor and its original identity. |
| `FR-R2r1` | `FR27-B1-D-Raphaël Glucksmann` | 18 | `3e337be6f1827ed917ec83139951a27de24713fbc93cb0249150b7f9ebf08677` | Scores and 17–19 October dates agree; discovery still labels 2,081 adults as reported. Retain the reviewed 1,928 registered-voter successor and its original identity. |
| `FR-R4r1` | `FR27-B1-D-Édouard Philippe` | 21 | `ca79c8681e49e780251417d6d916c3d5df2cbabefa17d3a831a978ee148aa553` | Scores and 17–19 October dates agree; discovery still labels 2,081 adults as reported. Retain the reviewed 1,928 registered-voter successor and its original identity. |
| `FR-R1r1` | `FR27-B1-D-Gabriel Attal` | 20 | `e97f8a9a7ba535b47a0b2c191562fa86bbcf8e38ee904d213a5b180541c62d88` | Scores and 17–19 October dates agree; discovery still labels 2,081 adults as reported. Retain the reviewed 1,928 registered-voter successor and its original identity. |
| `FR-POST-HOLLANDE-LE-PENr1` | `FR27-B1-D-François Hollande` | 19 | `dc48e1acd3d243666e98420673a25411d08adb73f2ef7375632e52f548be17a2` | Scores and 17–19 October dates agree; discovery still labels 2,081 adults as reported. Retain the reviewed 1,928 registered-voter successor and its original identity. |
| `FR-T0R5` | `FR27-B1-E` | 13 | `9f33fd416a66b1ed0a57260cd84fbe566de7763c32ac5aca10287dff04cbc30f` | The PDF gives Dupont-Aignan 2%; the discovery row still says 2.5%. Retain the already reviewed Batch 1 score correction. |
| `FR-T0R8` | `FR27-B1-C` | 16 | `458cb1a84a083ed5be2c5275b0e20fe0988fab911b9090ae7a5cc0611b4f642e` | The newly discovered Ruffin–Polony table matches all thirteen official scores on p16; retain the previously admitted Batch 1 object and registered-voter scope, without creating another ID. |
| `FR-T0R5` | `FR27-B1-E` | 13 | `9f33fd416a66b1ed0a57260cd84fbe566de7763c32ac5aca10287dff04cbc30f` | The updated discovery row now correctly gives Dupont-Aignan 2%; retain the exact reviewed Batch 1 object and its existing identity. |

All nine Batch 1 canonical events and predecessor objects remain exact; all five runoff supersessions retain their original successor IDs, dates and 1,928 registered-voter samples. Their lineage is:

| Predecessor ID | Successor ID |
|---|---|
| `a233b6b1c77d00740286c6bfc74c97472e2ee359c6dc5288028259106c419139` | `115ff210edfe581876a9fae703475ecec7f608b2312df5d2ce64941e7ec4117a` |
| `ed3b0944c6e298e66eb3d9ffd1d1c173af598b862105153901dcf3702428c26a` | `3e337be6f1827ed917ec83139951a27de24713fbc93cb0249150b7f9ebf08677` |
| `2bc03248b8380b8f6d9c388b9dd2d1f0cfddc1c46bc2506fce2aceef326a9311` | `ca79c8681e49e780251417d6d916c3d5df2cbabefa17d3a831a978ee148aa553` |
| `e90cc39c2cb9b055f44514b654f46831cc3e69d3d480b5fa4d57d920d94d988c` | `e97f8a9a7ba535b47a0b2c191562fa86bbcf8e38ee904d213a5b180541c62d88` |
| `0c13045c50fa51f5ee0dcd59e01fc24aee555cfbe3246315dc042a1ea249bf4f` | `dc48e1acd3d243666e98420673a25411d08adb73f2ef7375632e52f548be17a2` |

## Proposed code and evidence changes

- `reviewed_commission_coverage.py`: `load_batch2_review`, `admit_batch2_configurations`, `reconcile_batch2_notice_coverage` and private exact-identity helpers. Pin complete evidence; admit two records once; reconcile only twelve exact notices and complete object collections. Weak poll/date/lineup anchors can reject duplicates, never authorize an admission or equivalence.
- `fr27_commission_coverage_batch2.json`: twelve reviews, complete source transcriptions, 77 pinned published objects after admission and two explicit admission decisions.
- `fetch_polls.py:main`: apply admissions only after successful live French migration/Phase 1 guards; apply later exact coverage after generic/Batch 1 coverage; preserve frozen fixture behavior and print bounded diagnostics.
- `poll_migration.py`: add Karim Bouamrane to the existing polling identity mapping; `parse_french_frozen_fixture` retains prior extraction rejections by default. No caller enables broader Bouamrane discovery, and no candidacy status changes.
- `fr27_polling_accuracy_batch1.json`: eight exact 10327 source variants and one explicit compatibility review; `reviewed_polling_accuracy.py`: canonical review digest only. Matching/guard logic is unchanged.
- `test_commission_coverage_batch2.py`: 27 focused regressions, including all 437 unchanged objects, fourteen unchanged archived extractions, full exact coverage, strict failure cases, retained corrections and new/older discovery replay.
- `test_commission_notice_coverage.py`: deployed-state regression now exercises the actual generic/Batch 1/later reviewed coverage layers. The original test omitted the deployed 10324 review and failed before this adjustment; no coverage assertion is removed.
- `.github/workflows/update-polls.yml`: add the Batch 2 regression module to the existing test step only.
- New fixtures: `batch2_original_tables.json`, `batch2_pre_review_335_102.json.gz`, `fr_mediawiki_240569682.json.gz`, `fr_mediawiki_240570516.json.gz`. No existing historical fixture is edited.
- `docs/polling_commission_coverage_batch2.md`: this review report.

## Validation

- Final full polling/publication suite: **1,144 tests passed in 502.563 seconds**, across the 31 modules in `batch2-validation/full-test-modules.txt`. Log: `polling-publication-complete.log`.
- Focused final rerun: **86 tests passed in 82.809 seconds**: 27 Batch 2, 21 Batch 1, all 21 Phase 1 stability tests, and 17 Commission coverage tests. Log: `focused-complete.log`.
- The initial full run had one failure: the legacy deployed-coverage regression omitted Batch 1’s existing exact 10324 layer. Its assertion now reproduces deployed reconciliation, retaining the complete stored-object/summary comparison. The earlier 25 new tests passed before the compatibility review; the two additional tests pin the exact source extension and reject source/factual drift.
- A temporary deployed-state test against the newly generated Batch 2 corpus passed (1 test, 0.885 seconds). It validates the later coverage branch as well as the current production deployment state. Log: `publication-deployed-coverage.log`.
- Two consecutive **live production-equivalent French fetches exited 0**, revision 240570516. The second used the first fetch’s polling corpora and notice registry as previous inputs. Both used the standard CLI options from Update Polls, ran all migration/coverage guards, and wrote exclusively to `fetch-reviewed1/` and `fetch-reviewed2/`. The disposable runtime’s six changed production code/registry files are byte-identical to the final implementation files (hashes in `hygiene-validation.json`). No workflow was invoked. Logs: `fetch-reviewed1.log`, `fetch-reviewed2.log`.
- Both live outputs contain exactly **337 first-round and 102 runoff observations**. Each of the **437 historical event objects is exactly equal**, only the two approved IDs are new, all nine Batch 1 canonical outcomes remain exact, and all five reviewed superseded predecessor IDs remain absent. No unexplained historical loss; first-round extraction 293 against baseline 291 on the first fetch and against retained baseline 293 on the second; runoff extraction 100 against baseline 100 on both. The existing 90% failure floor is unchanged.
- Idempotence: first-round files are byte-identical; all runoff event objects and the existing semantic runoff payload are equal; notice-registry JSON is exactly equal; closest-runoff JSON is equal excluding `generated_at`. The second admission report is `0 admitted; 2 already applied`. Evidence: `output-validation.json`.
- All fourteen previously frozen French snapshots retain their original extraction digests. Replays of revisions 240522402, 240562307, 240569682 and 240570516 preserve reviewed history and admissions. Changed/missing/duplicate/extra configurations, wrong rounds, source/sample/date drift, unknown notice identities, bounded scores and extraction loss remain rejected or unresolved as appropriate.
- **19 downstream generation/check commands passed** in the disposable publication directory: candidate signals, recent changes, polling explorer, section launcher, poll pages, static hub links, route registry, search entrypoints, sitemaps and publication manifest. Results: 80 waves / 337 scenarios; 160 bilingual poll pages; 324 routes across five families; deterministic bilingual search and sitemap checks passed. Publication manifest validated snapshot `fc2c10e2c19d9cce2bc007a3af0fdf2f7c8681fb888dbcd60774ebf2830f8657`, retaining the three intended unresolved-notice warnings. Log: `publication-validation.log`.

The saved initial failed fetch and subsequent failed six-variant attempt are retained as `fetch1.log` and `fetch-final1.log`, with their exact source-drift diagnostics. They were not bypassed; only the individually documented original-source compatibility review enabled successful live fetches. All validation artifacts are retained outside the implementation checkout in the existing `batch2-validation` sibling directory.

## Repository hygiene and remaining limitations

`git diff --check` passed. A complete binary-capable cumulative patch, including all new evidence fixtures, passed `git apply --check` against the untouched implementation-base archive. Every existing tracked file was compared with that archive: only the six intended tracked files differ. No production polling JSON, generated HTML/publication output, pre-existing historical fixture, candidacy-status file, Phase 1 implementation, contract module or unrelated file changed. The primary checkout is clean at the original implementation base; no other worktree was modified.

Final status: **6 tracked files modified, 8 new files untracked, 0 files staged, no new commit**. Branch and HEAD remain `codex/polling-commission-batch2` / `8c727f2fb30091f295d5508f53a54e5c6f4780c9`. Complete changed-file list:

- `.github/workflows/update-polls.yml`
- `docs/polling_commission_coverage_batch2.md`
- `fetch_polls.py`
- `fr27_commission_coverage_batch2.json`
- `fr27_polling_accuracy_batch1.json`
- `poll_migration.py`
- `reviewed_commission_coverage.py`
- `reviewed_polling_accuracy.py`
- `test_commission_coverage_batch2.py`
- `test_commission_notice_coverage.py`
- `test_fixtures/fr27_polling/batch2_original_tables.json`
- `test_fixtures/fr27_polling/batch2_pre_review_335_102.json.gz`
- `test_fixtures/fr27_polling/fr_mediawiki_240569682.json.gz`
- `test_fixtures/fr27_polling/fr_mediawiki_240570516.json.gz`

The full patch is `batch2-validation/batch2-complete.patch`; exact status is `final-git-status.txt`; machine-readable hygiene results are `hygiene-validation.json`. No commit, push, PR, merge, deploy or production workflow was performed.

Review is required before committing or publishing. The outstanding Batch 2 representation limitations are the two bounded-score configurations and the composite RN option described above. They intentionally retain three Commission warnings. No schema redesign or broad precision/sample correction is proposed.

**Separate new-notice limitation:** live discovery added notice 10327 (161 → 162 registry entries). The existing listing classifier sets `excluded_non_voting` solely because its title contains “baromètre”; it does not fetch that excluded PDF and leaves `content_sha256=null`, `confirmed_rounds=[]`. The independently inspected PDF does contain presidential voting intentions. Batch 2 does not claim that notice is covered, parsed, or reconciled, and does not change the classifier or add a thirteenth coverage decision. Its listing classification needs a separately scoped review. All 149 pre-existing notice objects outside the twelve Batch 2 targets remain exactly unchanged.
