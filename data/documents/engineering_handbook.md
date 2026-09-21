# Helios Robotics - Engineering Handbook

## 1. Introduction
This handbook describes how engineering teams at Helios Robotics plan, build, test and release software for the HX-200 robot and the HX-Fleet platform. It is a living document; every engineer is encouraged to propose changes through a pull request.

## 2. Languages and tools
Real-time robot control software is written in C++17. Platform services, tooling and tests are written in Python 3.11. Source code is stored in GitHub, issues are tracked in Jira, and builds run in the company CI system. New languages or frameworks require an Architecture Decision Record (ADR) approved by the architecture group.

## 3. Working agreements
### 3.1 Sprints
Teams work in 2-week sprints. Sprint planning is held on the first Monday of the sprint and the sprint review on the last Friday. The daily stand-up lasts at most 15 minutes and starts at 09:45 CET for the Munich teams.

### 3.2 Technical debt
Every team reserves 20% of its sprint capacity for technical debt, bug fixing and tooling improvements. The share is reviewed each quarter.

### 3.3 Design reviews
Design reviews take place every Wednesday. A design document must be circulated at least 2 working days before the review. Decisions that affect more than one team must be recorded as an ADR.

## 4. Code quality
### 4.1 Branching
Teams use trunk-based development with short-lived branches. Branches should live for no more than 3 days. Direct commits to the main branch are blocked.

### 4.2 Pull requests
Every pull request requires 2 approvals, at least one of which must come from a member of the owning team. The CI pipeline must pass before merging. Pull requests should be smaller than 400 changed lines wherever possible.

### 4.3 Testing
New code must have at least 80% test coverage. Bug fixes must include a test that fails before the fix and passes after it. Every pull request runs the unit tests and a fast set of 50 simulation scenarios. The nightly regression suite runs 1,200 simulation scenarios and its results are posted in the #engineering-quality channel.

### 4.4 Static analysis
C++ code is checked with clang-tidy and Python code with ruff and mypy. Warnings are treated as errors in the main branch. Security scanning of dependencies runs on every build.

### 4.5 Third-party libraries
New third-party libraries need a licence check by Legal and a security review by the security team before they are added. Only libraries with permissive licences (MIT, BSD, Apache 2.0) are accepted by default.

## 5. Performance and safety
The safety-critical control loop of the HX-200 runs at 500 Hz, and its worst-case latency must stay below 4 ms. Changes to safety-critical code require review by a member of the safety team and a passing run of the full hardware-in-the-loop test bench. Safety-critical code must not use dynamic memory allocation after start-up.

## 6. Releases
### 6.1 Cadence
Minor firmware releases are published every quarter and a major release once per year, in the first full week of March. A code freeze starts 3 days before each release, and only fixes that are approved by the release manager are merged during the freeze.

### 6.2 Staged rollout
Firmware is rolled out to the customer fleet in stages: 5% of robots first, then 25%, then 100%. There is a soak period of 24 hours between stages, during which the release manager watches error rates, mission success rates and battery metrics. A stage may only start when the previous stage shows no increase in error rates.

### 6.3 Rollback
Every release must have a tested rollback plan. A rollback must be possible within 30 minutes of the decision. Rollbacks are triggered by the Incident Commander during a SEV1 incident, as described in the Incident Response Runbook.

### 6.4 Hotfixes
Hotfixes for P1 issues must be released within 24 hours of the issue being confirmed. Hotfixes follow the shortened staged rollout: 5% for 2 hours, then 100%.

## 7. Documentation
Every service has a README that explains how to run it locally, an architecture diagram and a runbook page. Public APIs are documented with OpenAPI. Documentation changes are reviewed in the same pull request as the code change.

## 8. Onboarding for engineers
New engineers set up their development environment in the first week and merge their first pull request within 10 working days. They are paired with an onboarding buddy for the first month and take part in one on-call shadow week before joining the rotation.

## 9. Frequently asked questions
**How many approvals does a pull request need?** Two, at least one from the owning team.

**What is the minimum test coverage for new code?** 80%.

**How large is the first stage of a firmware rollout?** 5% of the fleet, followed by 25% and then 100%, with a 24-hour soak period between stages.

**How often does the safety-critical control loop run?** At 500 Hz.
