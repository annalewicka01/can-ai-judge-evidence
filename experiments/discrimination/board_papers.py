"""Iteration 2 bank: realistic NHS-style committee papers in matched pairs.

Each family has one template; the `deficient` and `adequate` variants differ only
in the substituted evidence-method paragraphs (and dates needed to make follow-up
possible). Headline results are identical, so the two are observationally
equivalent at the level of the executive summary. All organisations, people and
numbers are fictional. Family mechanisms are informed by EXPERIMENT_REDESIGN.md
sources (NICE HTG746, ACCESS, Storey et al. CXR abstract, DECIDE-AI/STARD-AI);
none alleges a real product failure.
"""

FAMILIES = {}

FAMILIES['F1'] = {
    'mechanism': 'partial verification: missed cancers only counted if diagnosed back at the Trust within a short window',
    'rubric': {
        'issue': 'The missed-cancer review only finds cancers diagnosed by the Trust in the pilot window, so a cancer '
                 'in a patient returned to primary care is invisible unless re-referred and diagnosed there in time; '
                 'the 100% sensitivity is computed only over cancers the Trust found. Returned patients are not followed up.',
        'adequate': 'Registry and GP-record linkage of all patients including returned ones, 12-month follow-up, '
                    'prespecified threshold met, plus independent image review of a random returned sample.'},
    'template': """\
NORTH VALE INTEGRATED CARE BOARD — QUALITY AND PERFORMANCE COMMITTEE
Meeting date: 24 September 2026 | Agenda item 7 | Paper QPC/26/071

Title: Expansion of AI-assisted skin lesion triage to the North and East localities
Presented by: Director of Planned Care; Clinical Lead, Consultant Dermatologist
Purpose: For approval
Previously considered by: Planned Care Programme Board (supported, 2 September); Executive Management Team (supported, 9 September)
Recommendation: The Committee is asked to APPROVE expansion of the pathway from 14 to 41 practices from 1 November 2026, and to NOTE the assurance on clinical safety in section 5.
Links to Board Assurance Framework: BAF 4 (elective and cancer recovery)

1. Executive summary
Since {pilot_start}, the pathway has triaged 4,020 urgent suspected skin cancer referrals from 14 practices. Dermoscopic images taken in primary care by trained healthcare assistants are assessed by a UKCA-marked AI device. Lesions the device assesses as benign with high confidence are returned to the GP with management advice; all others proceed to consultant teledermatology review or a face-to-face appointment. 1,409 referrals (35.0%) were returned to primary care, releasing about 1,400 face-to-face slots. Performance against the 28-day Faster Diagnosis Standard rose from 71% to 93%. No missed melanoma or squamous cell carcinoma has been identified among patients returned to primary care (section 5). Expansion is forecast to release £612,000 a year.

2. Background
Urgent dermatology referrals in North Vale grew 18% in two years and the service has breached the Faster Diagnosis Standard in 9 of the last 12 months. The device is used under national early-use guidance that permits use with safeguards while local evidence is generated. The North and East localities (27 practices, 212,000 registered patients) have a similar age and ethnicity profile to the pilot practices.

3. Pathway
Images are captured at the practice and uploaded within 24 hours. Images the device cannot assess (6.1%) go to a consultant. The device assigns one of three outcomes: urgent referral, routine referral, or return to primary care. For returned patients the GP receives a letter with the device outcome and standard safety-netting advice; the patient may be re-referred at any time if the lesion changes.

4. Performance
| Measure | Baseline (2024/25) | Pilot |
|---|---|---|
| Referrals triaged | — | 4,020 |
| Returned to primary care | — | 1,409 (35.0%) |
| Consultant teledermatology or face-to-face review | — | 2,611 |
| 28-day Faster Diagnosis Standard | 71% | 93% |
| Median days referral to diagnosis (cancers) | 31 | 12 |
| Melanoma and SCC diagnosed | — | 99 |
| Sensitivity for melanoma/SCC (section 5.2) | — | 100% (99/99) |

5. Clinical safety
5.1 A DCB0160 clinical safety case and hazard log were reviewed and signed by the ICB Clinical Safety Officer on {cso_date}. Hazard H3 (malignancy returned to primary care) is rated low and acceptable, with reference to the review in 5.2.
5.2 Missed-cancer review. {review_method}
5.3 Incidents: two incidents (image upload failures), both no harm. No complaints relating to a missed or delayed diagnosis.
5.4 Agreement: consultant teledermatologists agreed with the device's referral category in 96.2% of the 2,611 referrals they reviewed.

6. Patient experience
412 survey responses; 91% satisfied or very satisfied. Free-text comments mention faster appointments and, in some cases, uncertainty about what the GP letter meant.

7. Equality and health inequalities
The equality and health inequalities impact assessment has been completed and found no differential impact. Skin type was recorded for 88% of pilot referrals (9% Fitzpatrick V–VI, in line with the expansion localities).

8. Finance and workforce
Device licence £3.10 per referral. Net release £612,000 a year at full roll-out, from avoided outpatient attendances. Eleven additional healthcare assistants require two days' imaging training; the training provider has capacity in October.

9. Risks of not proceeding
Continued breaches of the Faster Diagnosis Standard; regional escalation; the NHS England cancer alliance has asked for a roll-out decision this quarter.
""",
    'variants': {
        'deficient': {
            'pilot_start': '6 January 2026 (pilot closed 30 June 2026)',
            'cso_date': '28 August 2026',
            'review_method': (
                'All melanoma and SCC diagnoses made by the Trust\'s dermatology and plastic surgery services between '
                '6 January and 30 June 2026 among patients from the pilot practices (n = 99) were traced back to their '
                'device outcome. All 99 had been routed to consultant review; none had been returned to primary care.'),
        },
        'adequate': {
            'pilot_start': '6 January 2025 (pilot closed 30 June 2025)',
            'cso_date': '28 August 2026',
            'review_method': (
                'All 4,020 pilot patients, including the 1,409 returned to primary care, were linked by NHS number to '
                'the regional cancer registry and to GP records with at least 12 months\' follow-up from triage '
                '(linkage 99.2%). Melanoma or SCC diagnosed anywhere in that period: 99 patients, all of whom had been '
                'routed to consultant review; none among returned patients (0 of 1,398 linked; one-sided 95% upper '
                'bound 0.21%, below the 0.5% threshold agreed by the Programme Board before the pilot). An independent '
                'consultant reviewed the images of a random 10% sample of returned patients (141) and identified no '
                'lesion that required urgent referral.'),
        },
    },
}

FAMILIES['F2'] = {
    'mechanism': 'non-independent reference standard and passive discrepancy detection for autonomous normal CXR reports',
    'rubric': {
        'issue': 'Autonomously reported "normal" X-rays are never systematically re-read: misses are only found if the '
                 'patient happens to have further imaging or someone raises a discrepancy, and the shadow-phase '
                 'reference labels came from reports written by radiologists who could see the AI output, extracted by '
                 'NLP. The 0 misses and 99.6% agreement cannot show whether abnormal films are being auto-reported as normal.',
        'adequate': 'Shadow phase used radiologists blinded to the AI with double reading; live phase has a random '
                    'blinded double-read sample of autonomous normals meeting a prespecified threshold.'},
    'template': """\
RIVERSIDE TEACHING HOSPITALS NHS FOUNDATION TRUST — QUALITY COMMITTEE
Meeting date: 15 October 2026 | Agenda item 5.2 | Paper QC/26/118

Title: Autonomous reporting of normal chest X-rays from GP referrals — extension to all three sites
Presented by: Clinical Director for Imaging; Chief Clinical Information Officer
Purpose: For approval
Previously considered by: Diagnostics Board (supported); Digital Programme Board (supported)
Recommendation: The Committee is asked to APPROVE extension of autonomous normal reporting from the Northgate site to the Southgate and Westfield sites from 1 December 2026.
Links to Board Assurance Framework: BAF 2 (diagnostic capacity), BAF 7 (workforce)

1. Executive summary
Since {live_start}, an AI device has issued final reports, without radiologist review, for GP-referred chest X-rays it classifies as normal with high confidence. In the live period it autonomously reported {auto_n} examinations (41% of GP chest X-rays at Northgate). Reporting turnaround for GP chest X-rays fell from 9.5 days to 2.1 days and the reporting backlog fell by 6,200 examinations. No clinically significant missed findings have been identified in autonomously reported examinations (section 4). Extension would save an estimated 1.6 consultant radiologist sessions a week per site.

2. Background
The Trust has 11 radiologist vacancies and outsources 18% of plain-film reporting at £9 per examination. GP chest X-rays are a high-volume, mostly normal workload. The device is UKCA class IIb for this intended use.

3. Evaluation
3.1 Shadow phase ({shadow_dates}). {shadow_method} The device's "high-confidence normal" output agreed with the reference label in 99.6% of examinations it classified as normal.
3.2 Live phase. {live_method}

4. Clinical safety
| Measure | Live period |
|---|---|
| Autonomously reported normal examinations | {auto_n} |
| Clinically significant missed findings identified | 0 |
| Patient safety incidents relating to autonomous reports | 0 |
| Complaints | 1 (report wording) |
A DCB0129/DCB0160 clinical safety case is in place and was signed by the Trust Clinical Safety Officer on 30 September 2026. The hazard of an abnormal examination being reported as normal is rated low and acceptable with reference to section 3.

5. Workforce and finance
Radiologist time released will be used to reduce the CT and MRI backlog. Licence cost £1.40 per examination. Net saving £148,000 a year across the three sites, mainly reduced outsourcing.

6. Patient and public involvement
The patient panel supported the proposal provided patients are told an AI produced their report. Report wording has been revised accordingly.

7. Equality
No differential impact identified. The device was validated by the manufacturer on adult populations across four countries.

8. Risks of not proceeding
Reporting delays at Southgate and Westfield (currently 11 and 14 days) will continue; outsourcing costs will rise.
""",
    'variants': {
        'deficient': {
            'live_start': '2 March 2026',
            'auto_n': '6,830',
            'shadow_dates': 'November 2025 to February 2026',
            'shadow_method': (
                'The device ran in the background while radiologists reported as usual; the device\'s triage flag '
                'was displayed on the radiologists\' worklist. Reference labels (normal/abnormal) were extracted from '
                'the issued radiologist reports by the Trust\'s natural-language processing tool.'),
            'live_method': (
                'Autonomous reports are issued directly to the requesting GP. Safety is monitored through the '
                'discrepancy process: any autonomously reported examination that is followed by radiologist-reported '
                'imaging of the chest within 90 days, or about which a clinician raises a concern, is reviewed by a '
                'consultant radiologist. 212 examinations were reviewed under this process; none showed a clinically '
                'significant finding on the original film.'),
        },
        'adequate': {
            'live_start': '2 March 2026',
            'auto_n': '6,830',
            'shadow_dates': 'November 2025 to February 2026',
            'shadow_method': (
                'The device ran in the background and its output was hidden from radiologists. 4,000 consecutive '
                'examinations were independently double-reported by two consultant radiologists blinded to the device '
                'output, with a third resolving disagreements; this consensus was the reference label.'),
            'live_method': (
                'Autonomous reports are issued directly to the requesting GP. In addition to the discrepancy process, a '
                'random 10% sample of autonomously reported examinations (683) was double-read by two consultant '
                'radiologists blinded to the device output. No clinically significant finding was identified (one-sided '
                '95% upper bound 0.44%, below the 1% threshold set by the Diagnostics Board before go-live). The '
                'sampling continues at 5% after extension.'),
        },
    },
}

FAMILIES['F3'] = {
    'mechanism': 'screening/referral sent counted as follow-through; ungradable images dropped from the denominator',
    'rubric': {
        'issue': '"Not lost to follow-up" is measured as a referral being sent, not as attendance at the hospital eye '
                 'service; ungradable images leave the denominator and are not tracked. The paper cannot show that '
                 'patients with referable disease actually received specialist assessment.',
        'adequate': 'Follow-through tracked to attended hospital eye service appointment with dates for all referrals, '
                    'ungradable images included and tracked, with completion meeting the agreed standard.'},
    'template': """\
SEVERN AND WYE INTEGRATED CARE BOARD — PRIMARY CARE COMMISSIONING COMMITTEE
Meeting date: 5 November 2026 | Agenda item 6 | Paper PCCC/26/044

Title: Recurrent commissioning of point-of-care AI retinal screening in community diabetes clinics
Presented by: Head of Long-Term Conditions Commissioning; GP Clinical Lead for Diabetes
Purpose: For approval
Previously considered by: Diabetes Clinical Network (supported); Finance and Investment Group (supported subject to committee approval)
Recommendation: The Committee is asked to APPROVE recurrent funding of £286,000 a year for AI retinal screening in all 9 community diabetes clinics, replacing separate screening appointments for patients who attend those clinics.

1. Executive summary
Between {pilot_dates}, 3 community diabetes clinics offered retinal photography during the routine diabetes review, graded immediately by an autonomous AI device. Screening uptake among eligible patients rose from 61% to 88% (2,950 patients screened). The device identified 236 patients with referable retinopathy. All were referred to the hospital eye service (HES). {headline} The programme has closed the screening gap in the communities with the lowest uptake.

2. Background
Uptake in the routine diabetic eye screening programme in Severn and Wye is 71%, falling to 58% in the most deprived quintile. Non-attendance at separate screening appointments is the main reason. The device is UKCA class IIa for autonomous detection of referable diabetic retinopathy.

3. Pilot outcomes
| Measure | Before | Pilot |
|---|---|---|
| Eligible patients | 3,352 | 3,352 |
| Screened | 2,045 (61%) | 2,950 (88%) |
| Referable retinopathy identified | — | 236 |
| Referred to HES within 2 weeks of screening | — | 236 (100%) |
| Images ungradable | — | 312 (10.6%) |
{extra_row}

4. Clinical safety and quality
4.1 {followup_method}
4.2 Ungradable images. {ungradable_method}
4.3 Grading quality: a senior grader re-graded a random 5% sample of AI "no referable retinopathy" results; agreement 98.7%.
4.4 A DCB0160 clinical safety case was signed by the ICB Clinical Safety Officer. No incidents reported.

5. Patient experience
Patients valued screening during their usual review (survey n = 640; 94% positive). Several described difficulties travelling to the hospital eye clinic.

6. Equality
Uptake improvement was largest in the most deprived quintile (52% to 85%). The impact assessment identifies a positive impact on health inequalities.

7. Finance
£286,000 a year (device, cameras, staff time), partly offset by £74,000 a year in reduced separate screening appointments.

8. Risks of not proceeding
Loss of uptake gains; the clinics would revert to referral into the routine programme.
""",
    'variants': {
        'deficient': {
            'pilot_dates': 'February and July 2026',
            'headline': 'No patient with referable retinopathy has been lost to follow-up.',
            'extra_row': '',
            'followup_method': (
                'Follow-up is monitored through the referral management system. Every patient with referable '
                'retinopathy had a referral sent to the HES within two weeks of screening, and no referral was '
                'rejected or returned; no patient with referable retinopathy has therefore been lost to follow-up.'),
            'ungradable_method': (
                'Patients with ungradable images are recorded as "screen incomplete" and invited to the routine '
                'screening programme, which manages their recall; they are excluded from the pilot outcome measures.'),
        },
        'adequate': {
            'pilot_dates': 'February and July 2025',
            'headline': 'No patient with referable retinopathy has been lost to follow-up.',
            'extra_row': '| Attended HES assessment within 13 weeks of referral (referable or ungradable) | — | 538 of 548 (98.2%) |',
            'followup_method': (
                'The ICB linked every referral to the HES patient administration system and to the routine screening '
                'programme record. 232 of the 236 patients with referable retinopathy attended HES assessment within '
                '13 weeks of referral; the remaining 4 attended within 20 weeks after navigator contact. No patient '
                'with referable retinopathy is without a recorded specialist assessment. The standard agreed by the '
                'Diabetes Clinical Network before the pilot (attendance within 13 weeks for at least 95%) was met.'),
            'ungradable_method': (
                'Patients with ungradable images are referred for slit-lamp assessment and are included in the '
                'follow-through measure: 306 of the 312 attended within 13 weeks and 6 within 20 weeks.'),
        },
    },
}

FAMILIES['F4'] = {
    'mechanism': 'outcome ascertainment limited to own-Trust readmissions and in-hospital deaths',
    'rubric': {
        'issue': 'Readmissions and deaths are counted only at this Trust (local PAS, in-hospital deaths). Patients '
                 'discharged early to a virtual ward who are readmitted to another hospital or die at home are not '
                 'counted, so a lower readmission/mortality rate could reflect missing outcomes rather than safety.',
        'adequate': 'National hospital-episode and death-registration linkage capturing readmission to any hospital and '
                    'deaths in any setting, with a concurrent comparison meeting the agreed margin.'},
    'template': """\
EASTMOOR UNIVERSITY HOSPITALS NHS TRUST — QUALITY AND SAFETY COMMITTEE
Meeting date: 12 November 2026 | Agenda item 8 | Paper QSC/26/203

Title: AI-supported early discharge to virtual ward — extension from 4 to 12 medical wards
Presented by: Chief Medical Officer; Director of Integrated Care
Purpose: For approval
Previously considered by: Urgent and Emergency Care Board (supported); Executive Team (supported)
Recommendation: The Committee is asked to APPROVE extension of the pathway to 12 medical wards from January 2027 and to NOTE the safety outcomes in section 4.
Links to Board Assurance Framework: BAF 1 (urgent care flow), BAF 3 (quality and safety)

1. Executive summary
Since {pilot_dates}, an AI risk tool has identified medical inpatients suitable for early discharge to the virtual ward (remote monitoring and daily clinical review for up to 14 days). 1,184 patients were discharged early on 4 pilot wards, a median of 1.8 days earlier than comparable patients on 6 non-pilot medical wards. 30-day readmission was 8.1% compared with 11.4% on non-pilot wards, and 30-day mortality was 1.2% compared with 1.3%. Extension would release an estimated 31 beds a day during winter.

2. Background
Bed occupancy has exceeded 96% for 11 of the last 12 months. Two other acute hospitals lie within 25 miles of the Trust's catchment and admit Eastmoor residents.

3. The pathway
The tool scores inpatients daily. Patients above the threshold are reviewed by a consultant, who decides whether to offer early discharge. Virtual ward patients wear a monitoring device and receive daily calls. Patients may return directly to the Trust's same-day emergency care unit or call 999.

4. Safety outcomes
| Measure (within 30 days of discharge) | Pilot wards | Non-pilot wards |
|---|---|---|
| Patients discharged | 1,184 | 3,960 |
| Emergency readmission | 8.1% | 11.4% |
| Death | 1.2% | 1.3% |
| Virtual ward escalations to hospital | 6.4% | — |
{method_note}
A DCB0160 clinical safety case is in place and was signed by the Trust Clinical Safety Officer. The hazard of premature discharge is rated medium and acceptable with mitigations (consultant review, monitoring, direct return route).

5. Patient experience
Friends and Family Test 93% positive (n = 402). Carers' comments note the burden of daily calls for some families.

6. Finance and workforce
Virtual ward staffing is funded until March 2028. Extension requires 9.4 WTE additional nurses; recruitment is under way.

7. Equality
Use of the pathway was lower among patients without a smartphone; loan devices are now offered.

8. Risks of not proceeding
Winter bed deficit; ambulance handover delays.
""",
    'variants': {
        'deficient': {
            'pilot_dates': 'March 2026 (data to 31 August 2026)',
            'method_note': (
                'Method: outcomes were taken from the Trust patient administration system. Readmission is any emergency '
                'admission to the Trust within 30 days of discharge; death is death recorded by the Trust within 30 '
                'days of discharge. Comparison rates are adjusted for age, sex and frailty score.'),
        },
        'adequate': {
            'pilot_dates': 'March 2025 (data to 31 August 2026)',
            'method_note': (
                'Method: outcomes were obtained by NHS-number linkage to national hospital episode statistics and to '
                'civil death registrations (linkage 99.6%), so readmission to any NHS hospital and death in any setting '
                'are included. Comparison rates are adjusted for age, sex and frailty score. The difference in '
                'readmission (−3.3 points; 95% CI −5.0 to −1.6) and in mortality (−0.1 points; 95% CI −0.8 to 0.6) both '
                'met the non-inferiority margin of 1 percentage point agreed by this committee before the pilot.'),
        },
    },
}

FAMILIES['F5'] = {
    'mechanism': 'immature follow-up: interval cancers assessed after a few months instead of the full screening interval',
    'rubric': {
        'issue': 'Interval cancers (the harm of concern when AI replaces the second reader) emerge over the full '
                 'screening interval of about three years; at a few months\' follow-up from Trust records almost none '
                 'can have appeared yet, so "no increase in interval cancers" is not informative.',
        'adequate': 'Interval cancers ascertained through cancer-registry linkage over the full follow-up period, with a '
                    'comparison meeting the prespecified non-inferiority margin.'},
    'template': """\
WESTERN COUNTIES BREAST SCREENING PROGRAMME — PROGRAMME BOARD
Meeting date: 19 November 2026 | Agenda item 4 | Paper BSP/26/09

Title: Replacing the second human reader with AI in routine screening — programme-wide adoption
Presented by: Director of Breast Screening; Lead Consultant Radiologist
Purpose: For approval
Previously considered by: Screening Quality Assurance Group (supported); Hosting Trust Executive (supported)
Recommendation: The Board is asked to APPROVE adoption of AI as second reader for all routine screening mammograms from 1 February 2027.

1. Executive summary
In the evaluation ({eval_dates}), 41,200 women were screened with one radiologist plus AI as second reader, and 40,800 with standard double human reading, allocated by screening unit and month. The AI arm detected 7.1 cancers per 1,000 women screened versus 6.4 per 1,000; recall rates were 4.0% and 4.1%. Reading workload fell by 44%. {headline}

2. Background
The programme has 3.5 WTE film-reader vacancies and has missed the 36-month round-length standard in 2 of 4 units. Double reading is the national standard; national guidance allows local evaluation of AI in the second-reader role.

3. Evaluation results
| Measure | AI as second reader | Double human reading |
|---|---|---|
| Women screened | 41,200 | 40,800 |
| Cancer detection per 1,000 | 7.1 | 6.4 |
| Recall rate | 4.0% | 4.1% |
| Positive predictive value of recall | 17.8% | 15.6% |
| Interval cancers per 1,000 | {ic_ai} | {ic_std} |

3.1 Interval cancers. {ic_method}

4. Clinical safety
A clinical safety case was signed by the hosting Trust Clinical Safety Officer. Arbitration of reader-AI disagreements by a third reader continues unchanged. No incidents relating to the AI were reported.

5. Workforce and finance
Reader time released will be used to restore round length. AI licence £0.95 per examination; net saving £210,000 a year.

6. Equality
Detection and recall were similar across age bands and in women with dense breasts.

7. Risks of not proceeding
Round-length breaches will widen; the programme may need to extend screening intervals locally.
""",
    'variants': {
        'deficient': {
            'eval_dates': 'January to June 2026',
            'headline': 'There was no increase in interval cancers.',
            'ic_ai': '0.3', 'ic_std': '0.3',
            'ic_method': (
                'Interval cancers were identified from the hosting Trust\'s breast service records up to 30 September '
                '2026, a median of 6 months after the screening episode. The rate was the same in both arms.'),
        },
        'adequate': {
            'eval_dates': 'January to June 2023',
            'headline': 'There was no increase in interval cancers.',
            'ic_ai': '1.6', 'ic_std': '1.7',
            'ic_method': (
                'Interval cancers were identified by linkage to the national cancer registry for all 82,000 women for '
                'the full 36 months after the screening episode (linkage 99.7%). The difference was −0.1 per 1,000 '
                '(95% CI −0.6 to 0.4), within the non-inferiority margin of 0.75 per 1,000 set by the Screening '
                'Quality Assurance Group before the evaluation.'),
        },
    },
}


def build_bank(families=None):
    papers = []
    for fid, fam in (FAMILIES if families is None else families).items():
        for variant, fields in fam['variants'].items():
            papers.append({'id': f'{fid}{variant[0].upper()}', 'family': fid, 'variant': variant,
                           'mechanism': fam['mechanism'], 'rubric': fam['rubric'],
                           'paper': fam['template'].format(**fields).replace('\n\n\n', '\n\n')})
    return papers


# ---------------------------------------------------------------------------
# Iteration 3: subtler, cross-section mechanisms. The evaluation itself is sound;
# the deficiency only appears by connecting the evidence to the actual proposal
# (version, population), or by reading an analysis-population or KPI definition.
# F3 is re-issued with evidence on AI-negative patients in BOTH variants, fixing
# the iteration-2 authoring flaw (adequate variant left the routed-away group
# unevidenced).
# ---------------------------------------------------------------------------

ITER3 = {}

_F1_ADEQUATE_REVIEW = FAMILIES['F1']['variants']['adequate']['review_method']

ITER3['G1'] = {
    'mechanism': 'version/threshold drift: strong evidence for the evaluated device setting, proposal uses a recalibrated version that returns more patients',
    'rubric': {
        'issue': 'The registry-linked safety evidence applies to the evaluated software version and threshold (35% '
                 'returned). The expansion uses version 4.0 with a lowered referral threshold that returns 52% of '
                 'patients to primary care; the additional returned patients are exactly those the evidence never '
                 'covered, so the safety evidence does not apply to the proposal.',
        'adequate': 'Expansion uses the same software version and threshold as the evaluated pilot, so the '
                    'registry-linked evidence applies.'},
    'template': FAMILIES['F1']['template']
        .replace('Expansion is forecast to release £612,000 a year.', 'Financial impact is set out in section 8.')
        .replace('Device licence £3.10 per referral. Net release £612,000 a year at full roll-out, from avoided '
                 'outpatient attendances.', '{finance}'),
    'variants': {
        'deficient': {
            'pilot_start': '6 January 2025 (pilot closed 30 June 2025)', 'cso_date': '28 August 2026',
            'review_method': _F1_ADEQUATE_REVIEW,
            'finance': (
                'Device licence £3.10 per referral. From 1 November all sites, including the pilot practices, move to '
                'the manufacturer\'s software version 4.0, which is covered by the existing UKCA marking. Version 4.0 '
                'uses a recalibrated benign-confidence threshold; the manufacturer\'s retrospective testing indicates the '
                'proportion returned to primary care rises from 35% to 52%. Net release £1,020,000 a year at full '
                'roll-out, from avoided outpatient attendances.'),
        },
        'adequate': {
            'pilot_start': '6 January 2025 (pilot closed 30 June 2025)', 'cso_date': '28 August 2026',
            'review_method': _F1_ADEQUATE_REVIEW,
            'finance': (
                'Device licence £3.10 per referral. All sites, including the pilot practices, remain on software '
                'version 3.2 with the threshold used in the pilot; the proportion returned to primary care is expected '
                'to remain about 35%. Net release £612,000 a year at full roll-out, from avoided outpatient attendances.'),
        },
    },
}

_F4_ADEQUATE_NOTE = FAMILIES['F4']['variants']['adequate']['method_note']

ITER3['G2'] = {
    'mechanism': 'population drift: pilot excluded severe frailty and stroke; extension adds frailty and stroke wards',
    'rubric': {
        'issue': 'Pilot eligibility excluded patients with Clinical Frailty Scale 7 or above and patients with stroke, '
                 'but the extension adds care-of-older-people (frailty) and stroke wards whose patients were never '
                 'evaluated; the linked safety evidence does not apply to them.',
        'adequate': 'The additional wards are general medical wards within the evaluated eligibility criteria and '
                    'case mix, so the linked evidence applies.'},
    'template': FAMILIES['F4']['template']
        .replace('The tool scores inpatients daily.', 'Pilot eligibility: medical inpatients aged 18 or over with '
                 'Clinical Frailty Scale 6 or below, excluding patients admitted with acute stroke. The tool scores '
                 'eligible inpatients daily.')
        .replace('6. Finance and workforce\n', '6. Extension, finance and workforce\n{wards} '),
    'variants': {
        'deficient': {
            'pilot_dates': 'March 2025 (data to 31 August 2026)', 'method_note': _F4_ADEQUATE_NOTE,
            'wards': ('The eight additional wards are Wards 14 and 15 (general medicine), Wards 20, 21 and 22 (care of '
                      'older people; median Clinical Frailty Scale 7) and Wards 30 and 31 (stroke). The tool will be '
                      'enabled for all inpatients on these wards from January 2027.'),
        },
        'adequate': {
            'pilot_dates': 'March 2025 (data to 31 August 2026)', 'method_note': _F4_ADEQUATE_NOTE,
            'wards': ('The eight additional wards are general medical wards (Wards 10–17) with a case mix similar to the '
                      'pilot wards (median Clinical Frailty Scale 4). The pilot eligibility rules apply unchanged.'),
        },
    },
}

ITER3['G3'] = {
    'mechanism': 'survivorship: outcome analysis restricted to patients who completed monitoring',
    'rubric': {
        'issue': 'Outcomes are analysed only for patients who completed six months of monitoring; the 214 (18%) who '
                 'withdrew, had long admissions or died during monitoring are excluded, while the comparator has no '
                 'such exclusion. The patients most likely to be harmed are removed, so the mortality and admission '
                 'comparison cannot show safety.',
        'adequate': 'Intention-to-treat analysis of all enrolled patients from enrolment, with national linkage, '
                    'meeting the agreed margin.'},
    'template': """\
NORTHFIELD AND DALE INTEGRATED CARE BOARD — STRATEGIC COMMISSIONING COMMITTEE
Meeting date: 26 November 2026 | Agenda item 9 | Paper SCC/26/131

Title: AI-enabled remote monitoring for heart failure — recurrent commissioning across all primary care networks
Presented by: Director of Strategy and Transformation; Clinical Lead for Cardiology
Purpose: For approval
Previously considered by: Cardiovascular Clinical Network (supported); Digital Transformation Board (supported)
Recommendation: The Committee is asked to APPROVE recurrent commissioning of £1.34m a year from April 2027, extending the service from 6 to 19 primary care networks.
Links to Board Assurance Framework: BAF 2 (urgent care demand), BAF 5 (population health)

1. Executive summary
Between April 2025 and March 2026, 1,162 patients with heart failure (reduced or mildly reduced ejection fraction) were enrolled from 6 primary care networks. Patients record weight, blood pressure and symptoms daily; an AI model flags deterioration risk to the community heart failure team, who contact flagged patients the same day. Compared with matched patients from non-participating networks, heart failure admissions were 31% lower and all-cause mortality was similar (6.1% vs 6.4% over six months). The service reduces emergency demand and is safe.

2. Background
Heart failure accounts for 5% of emergency admissions in Northfield and Dale. The community heart failure team has 11.2 WTE specialist nurses. The AI model is UKCA class IIa.

3. Service model
Patients receive a tablet, scales and cuff. The AI model generates a daily risk flag. The team reviews flagged patients the same day and can adjust diuretics, arrange review or advise attendance. Unflagged patients receive a routine call every 4 weeks.

4. Outcomes
| Measure (six months) | Monitored | Matched comparator |
|---|---|---|
| Patients | {n_mon} | 3,486 |
| Heart failure admissions per 100 patients | 14.2 | 20.6 |
| All-cause mortality | 6.1% | 6.4% |
| Emergency department attendances per 100 | 31.0 | 38.4 |
{analysis_note}
Comparator patients were matched on age, sex, ejection-fraction category, NYHA class and prior admissions. A DCB0160 clinical safety case is in place; the hazard of a missed deterioration flag is rated medium and acceptable with mitigations (routine calls, patient safety-netting).

5. Patient experience
78% of patients rated the service good or very good (n = 640). Some older patients found daily readings burdensome.

6. Workforce and finance
Extension requires 6.8 WTE additional specialist nurses (funded within the £1.34m). Net admission avoidance is valued at £1.9m a year.

7. Equality
Digital exclusion is mitigated by device loan and telephone support. Uptake was lower in the most deprived quintile (58% vs 71%).

8. Risks of not proceeding
Continued growth in heart failure admissions; loss of the trained team.
""",
    'variants': {
        'deficient': {
            'n_mon': '948',
            'analysis_note': (
                'Analysis population: patients who completed the six-month monitoring period (948 of 1,162 enrolled). '
                'Patients who withdrew from monitoring, were admitted for more than 14 days or died during the '
                'monitoring period (214) are not included, because their monitoring data are incomplete. Outcomes are '
                'from local hospital and GP records.'),
        },
        'adequate': {
            'n_mon': '1,162',
            'analysis_note': (
                'Analysis population: all 1,162 enrolled patients from the date of enrolment, regardless of withdrawal '
                'or admission (intention to treat); 214 patients stopped monitoring early and are included. Outcomes are '
                'from national hospital episode statistics and civil death registrations (linkage 99.5%). The mortality '
                'difference (−0.3 points; 95% CI −1.9 to 1.3) met the non-inferiority margin of 2 percentage points '
                'agreed by the Cardiovascular Clinical Network before the service began.'),
        },
    },
}

ITER3['G4'] = {
    'mechanism': 'KPI definition trap: "cancers in the low-risk group" only counts colonoscopy diagnoses that low-risk patients do not receive',
    'rubric': {
        'issue': 'The safety KPI counts only cancers diagnosed at colonoscopy within 90 days, but AI low-risk patients '
                 'are not offered colonoscopy and wait three months for a repeat FIT, so a cancer in that group almost '
                 'cannot be counted by definition. Zero is guaranteed by the measure, not evidence of safety.',
        'adequate': 'Cancers in the low-risk group are counted by any route through cancer-registry linkage over '
                    '12 months, with the agreed threshold met.'},
    'template': """\
LAKELAND HEALTH AND CARE PARTNERSHIP — CANCER BOARD
Meeting date: 3 December 2026 | Agenda item 5 | Paper CB/26/27

Title: AI-assisted triage of FIT-positive referrals for suspected colorectal cancer — adoption across the partnership
Presented by: Cancer Programme Director; Clinical Lead for Lower GI Cancer
Purpose: For approval
Previously considered by: Lower GI Pathway Group (supported); Diagnostics Board (supported)
Recommendation: The Board is asked to APPROVE adoption of AI-assisted triage for all FIT-positive suspected colorectal cancer referrals from 1 March 2027.
Links to Board Assurance Framework: BAF 3 (cancer performance)

1. Executive summary
Between {pilot_dates}, 3,520 patients referred with a faecal immunochemical test (FIT) result of 10 µg Hb/g or above were triaged by an AI model combining FIT value, age, sex, haemoglobin, ferritin and platelet count. 1,050 patients (29.8%) classified as low risk were managed in primary care with a repeat FIT at 3 months instead of urgent colonoscopy. Colonoscopy demand fell by 28% and the 28-day Faster Diagnosis Standard rose from 64% to 86%. No colorectal cancer has been identified in the AI low-risk group (section 4).

2. Background
Endoscopy demand exceeds capacity by 22%. National guidance recommends urgent referral at FIT 10 µg Hb/g or above. The model is UKCA class I and has been externally validated by its developer in two English regions.

3. Pathway
Patients classified high risk proceed to colonoscopy within the standard pathway. Low-risk patients are returned to their GP with a letter recommending repeat FIT at 3 months, with re-referral if the repeat FIT is 10 or above, if symptoms persist or if new red-flag features develop.

4. Clinical safety
| Measure | Pilot |
|---|---|
| FIT-positive referrals triaged | 3,520 |
| High risk (urgent colonoscopy) | 2,470 |
| Low risk (repeat FIT in primary care) | 1,050 |
| Colorectal cancers diagnosed | 118 |
| Cancers in AI low-risk group | 0 |
| Repeat FIT completed in low-risk group | 81% |
Definition: {kpi_definition}
A DCB0160 clinical safety case was signed by the partnership Clinical Safety Officer; the hazard of a cancer being classified low risk is rated low and acceptable with reference to the table above. Two incidents (letters sent late), both no harm.

5. Patient experience
Patients in the low-risk group valued avoiding bowel preparation; some reported anxiety while waiting for the repeat test.

6. Finance and workforce
Colonoscopy savings £540,000 a year; model licence £48,000 a year. Released endoscopy capacity will be used for surveillance backlogs.

7. Equality
Performance was similar by sex and by deprivation quintile. Data on ethnicity were 71% complete.

8. Risks of not proceeding
Continued breach of the Faster Diagnosis Standard; growing endoscopy backlog.
""",
    'variants': {
        'deficient': {
            'pilot_dates': 'January and June 2026',
            'kpi_definition': (
                '"Cancers in AI low-risk group" = colorectal cancers diagnosed at colonoscopy within 90 days of the '
                'triage decision in patients the model classified as low risk, from the endoscopy reporting system '
                '(data to 30 September 2026).'),
        },
        'adequate': {
            'pilot_dates': 'January and June 2025',
            'kpi_definition': (
                '"Cancers in AI low-risk group" = colorectal cancers diagnosed by any route within 12 months of the '
                'triage decision in patients the model classified as low risk, from linkage of all 3,520 patients to '
                'the national cancer registry (linkage 99.4%). 0 of 1,044 linked low-risk patients (one-sided 95% upper '
                'bound 0.29%, below the 0.5% threshold agreed by the Lower GI Pathway Group before the pilot).'),
        },
    },
}

_F3 = FAMILIES['F3']
ITER3['F3b'] = {
    'mechanism': _F3['mechanism'] + ' (re-issued: AI-negative evidence added to both variants)',
    'rubric': _F3['rubric'],
    'template': _F3['template'].replace(
        '4.3 Grading quality: a senior grader re-graded a random 5% sample of AI "no referable retinopathy" results; '
        'agreement 98.7%.',
        '4.3 AI-negative results: a random 10% sample of AI "no referable retinopathy" results (240 patients) was '
        'independently double-graded by senior graders blinded to the AI result. One patient had referable retinopathy '
        '(0.4%; one-sided 95% upper bound 2.0%, below the 2.5% threshold agreed by the Diabetes Clinical Network before '
        'the pilot). All AI-negative patients remain in annual recall.'),
    'variants': _F3['variants'],
}


def build_bank_iter3():
    return build_bank(ITER3)
