# Test questions and expected answers (Helios Robotics corpus)

These are the 13 questions used in `rag_pipeline.ipynb` (section 2.4 / 2.6). Every expected answer was checked against the text of the source file.

| # | Question | Expected answer | Source |
|---|---|---|---|
| 1 | How many days of annual leave do full-time employees get per year? | 21 days | hr_leave_policy.pdf (2.1) |
| 2 | What is the maximum nightly hotel cost in Tier-1 cities such as New York, London and Singapore? | $260 | expense_policy.pdf (2.2) |
| 3 | How many operating hours are there between full inspections of the HX-200? | 500 hours | hx200_manual.pdf (8.2) |
| 4 | Within how many hours must a critical vulnerability be patched? | 72 hours | security_policy.pdf (9) |
| 5 | How quickly must the on-call engineer respond to a SEV1 incident? | 15 minutes | incident_runbook.md (2) |
| 6 | How long is the standard warranty for the HX-200? | 24 months | warranty_and_support.pdf (2.1) |
| 7 | What is the list price of one HX-200 robot? | $24,500 | customer_faq.txt |
| 8 | What minimum test coverage is required for new code? | 80% | engineering_handbook.md (4.3) |
| 9 | How many days per year may an employee work remotely from another country? | 20 days | remote_work_policy.txt (3) |
| 10 | How long is the probation period for new hires? | 6 months | onboarding_guide.txt |
| 11 | How quickly must a lost or stolen laptop be reported to the security team? (hard: "1 hour" also appears in other documents) | within 1 hour | security_policy.pdf (4.2) |
| 12 | What is the annual salary of the CEO of Helios Robotics? | NOT in the corpus, must refuse | none |
| 13 | Under which stock ticker symbol is Helios Robotics publicly traded? | NOT in the corpus, must refuse | none |

## Extra questions for the live demo (all verified in the corpus)

| Question | Expected answer | Source |
|---|---|---|
| How many weeks of paid parental leave do secondary caregivers receive? | 6 weeks | hr_leave_policy.pdf (5.1) |
| What does error code E-73 mean on the HX-200? | Battery temperature too high | hx200_manual.pdf (9) |
| Who must approve expenses above $5,000? | The CFO | expense_policy.pdf (6) |
| How often is the status page updated during a SEV1 incident? | Every 30 minutes | incident_runbook.md (4) |
| How many robots can HX-Fleet manage per site? | Up to 250 | hx200_manual.pdf (5.2) |
