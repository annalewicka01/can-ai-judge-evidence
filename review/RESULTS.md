# Review results

Each cell shows X / Y. Totals count version answers, not pairs.

| Pair | joint | opus |
| --- | --- | --- |
| F1 | agree / agree | agree / agree |
| F2 | agree / agree | agree / agree |
| F3b | agree / agree | agree / agree |
| F4 | agree / agree | agree / agree |
| F5 | agree / agree | agree / agree |
| G1 | blank / blank | agree / agree |
| G2 | agree / agree | agree / agree |
| G3 | agree / agree | agree / agree |
| G4 | agree / agree | agree / agree |
| covid-surveillance | agree / agree | agree / agree |
| covid-masking | agree / agree | agree / agree |

| Reviewer | Agree | Disagree | Unsure | Blank |
| --- | --- | --- | --- | --- |
| joint | 20 | 0 | 0 | 2 |
| opus | 22 | 0 | 0 | 0 |

## Reviewer comments

- joint, F1: x is only including diagnoses made by the Trust
- joint, F2: to make the comparison fair, the results from ai must be hidden from the radiologists
- joint, F3b: no patients being lost in follow-up
- joint, F4: readmission to any NHS hospital and death in any setting must included to make the results reliable
- joint, F5: the data is coming only from Trust records in X, while Y expands to national records
- joint, G2: we are excludig patients with stroke so no point adding a ward for them as in X
- joint, G3: selection bias in Y
- joint, G4: 0 of 1,044 linked low-risk patients
- joint, covid-surveillance: Follow-up swabs were completed by only a small group of patients in scenraio Y
- joint, covid-masking: infections are measured in passengers who did not wear a covering
- opus, F1: X's review only searched cancers diagnosed by Trust services within the pilot window itself, so returned patients (who wouldn't go back to the Trust) and late-pilot patients had almost no chance of a missed cancer being found; 99/99 sensitivity is circular. Y has 12-month registry and GP linkage, 0 cancers in 1,398 linked returned patients, upper bound 0.21% vs a 0.5% threshold set before the pilot, plus an independent 10% image re-read. Minor wrinkles: in Y the 2024/25 baseline overlaps the Jan 2025 pilot start; in both, the equality assessment gives no results by skin type.
- opus, F2: X: the reference standard is independent and blinded, the random live sample has a pre-set threshold, and the upper bound is right (3/683 ≈ 0.44%). Two caveats: 683 films can't rule out rare cancer misses, and nothing shows the other sites' patients match Northgate's. Y: the shadow labels are contaminated, because radiologists saw the AI flag and labels were pulled from reports by NLP. Live checks only reach patients re-imaged within 90 days or raised as a concern, so most misses would never be seen and '0 missed' says little. Fair contrast, nothing clinically implausible.
- opus, F3b: X: 'no one lost to follow-up' rests only on referrals being sent and not rejected, with no data on HES attendance. The 312 ungradable patients (10.6%) are counted in the 88% uptake but excluded from outcomes and sent back to the routine programme that has low uptake. Y links referrals to attendance records for all 548 (236+312), and the figures add up (232+306=538; 4+6=10 seen by 20 weeks). Nothing implausible; the 240-patient negative sample is 10% of the 2,402 AI-negatives.
- opus, F4: X: linkage covers all NHS hospitals and deaths in any setting, and the non-inferiority margin was set in advance, with CIs inside it. Caveat: if the 1,184 are only tool-selected patients and the comparator is all non-pilot discharges, adjusting for age, sex and frailty may not remove selection bias. Y: only Trust records are used, so readmissions to the 2 nearby hospitals and deaths at home are missed. No CIs or margin. With data from March to 31 Aug 2026, late discharges lack full 30-day follow-up. Fair contrast.
- opus, F5: X: The interval-cancer data come only from the Trust's own records, with a median 6 months of follow-up against a 36-month screening interval. That is too short, and it misses cancers diagnosed elsewhere. The 0.3/1,000 rate is implausibly low, so 'no increase' isn't shown. Y: Registry linkage over the full 36 months, with a CI inside a pre-set margin, supports the claim. Allocation by unit/month isn't randomised, but that's a fair limitation for both. The 2023 dates are consistent with the follow-up timing.
- opus, G1: X: same v3.2 threshold as pilot, so the registry-linked missed-cancer review (0/1,398, upper bound 0.21% below the 0.5% threshold set beforehand) applies directly. Y: v4.0's recalibrated threshold returns about 17% more borderline lesions (52% vs 35%), backed only by manufacturer retrospective testing; the local safety review and H3 rating don't cover this, and UKCA marking isn't local safety evidence. Minor: the '100% sensitivity 99/99' in section 4 is near-circular; section 5.2 does the real work.
- opus, G2: X: the extension covers groups the pilot excluded (stroke wards, care-of-older-people wards with median CFS 7, and 'all inpatients'), so the pilot safety data can't support it. Y: same case mix and rules; national linkage picks up readmissions and deaths at the two nearby hospitals, and both CIs fall within the 1-point margin. Caveat: this is a non-randomised comparison of consultant-selected pilot patients against all non-pilot discharges, adjusted only for age, sex and frailty, so selection bias could favour the pilot. A strict reader might say unsure for Y.
- opus, G3: X: intention-to-treat analysis of all 1,162 patients, national linkage at 99.5%, a non-inferiority margin set in advance and a confidence interval inside it. That's enough for a commissioning decision. One caveat: the comparison is matched, not randomised, and lower uptake in the most deprived quintile suggests self-selection may make the 31% look bigger than it is. Y: the 214 excluded patients include those who died or were admitted for more than 14 days, but the comparator group isn't filtered the same way. That biases both the admission and mortality results in the service's favour. A 6.1% death rate among patients who completed six months is also hard to square with excluding deaths during those same six months. Local records may miss out-of-area admissions too.
- opus, G4: X: registry linkage of all patients by any route, 12-month follow-up, 99.4% linked; 0/1,044 gives an upper bound of 3/1,044 ≈ 0.29%, below the 0.5% threshold set before the pilot, so the result can be trusted. Y: cancers are only counted if found at colonoscopy within 90 days, but low-risk patients don't get colonoscopy (repeat FIT is at 3 months), and data run only to 30 Sep 2026 for a pilot that ended in June. Missed cancers couldn't show up, so the '0' tells us nothing, and the safety case rests on it. The answer key looks fair, and nothing seems clinically implausible.
- opus, covid-masking: X matches the claim. Fellow passengers were offered the programme, and infections were measured in enrolled passengers who were not told to wear coverings. Allocation was randomised in pairs, testing was blinded with complete follow-up, and the pair-adjusted, cohort-clustered 95% interval (0.33–0.75) is wholly below 1. Y tests something else: the enrolled passengers wore the coverings themselves while fellow passengers' use was unchanged, so it shows wearer protection, not protection from other passengers' coverings. Neither answer depends on whether the six-week programme should be adopted. Nothing seems clinically implausible or unfair. A small wording point: in Y, the '80% of passengers offered' audit now refers to the enrolled group, which is consistent but easy to misread.
- opus, covid-surveillance: X: follow-up swabs were scheduled whatever people's symptoms, and procedures stayed the same, so the 0.60 ratio (CI 0.42–0.86) supports a real fall that isn't just about test access. Y: follow-ups depended on the narrowed referral route (2,000 vs 1,200 completed). Positivity among those followed up was the same both weeks (100/2,000 = 60/1,200 = 5%), so access changes alone could explain the whole fall. Neither result decides the policy.
