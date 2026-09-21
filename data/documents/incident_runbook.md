# Incident Response Runbook

## 1. Purpose
This runbook describes how Helios Robotics detects, responds to and learns from incidents affecting the HX-Fleet platform, the customer portal, internal systems and robots in the field. It is meant to be read before you are on call, not during an incident.

## 2. Severity levels
- **SEV1**: customer-facing outage or a safety event. The on-call engineer must respond within 15 minutes.
- **SEV2**: degraded service. Respond within 1 hour.
- **SEV3**: minor issue. Respond by the next business day.

### 2.1 Examples
SEV1 examples: the HX-Fleet console is unavailable for more than 5 minutes, a robot injures a person or its protective field fails, or customer data is exposed. SEV2 examples: robot missions are delayed by more than 30 minutes, or OTA firmware updates fail for a subset of customers. SEV3 examples: a dashboard shows wrong numbers, or a non-critical background job fails.

### 2.2 Changing severity
The Incident Commander can raise or lower the severity at any time. When in doubt, choose the higher severity and downgrade later.

## 3. Roles
Every SEV1 and SEV2 incident has an Incident Commander who coordinates the response. Larger incidents also have the following roles.
- **Communications Lead**: writes customer and internal updates.
- **Operations Lead**: makes technical changes to systems and robots.
- **Scribe**: keeps a timeline of decisions and actions in the incident channel.
The Incident Commander does not make technical changes; their job is to coordinate.

## 4. Communication
All communication happens in the #incident-war-room Slack channel. Each incident gets a thread with a short title and its severity. For SEV1 incidents the status page is updated every 30 minutes, and affected customers are notified within 60 minutes of the incident being declared. For SEV2 incidents the status page is updated every 2 hours. Do not discuss incidents in private messages, so that everyone shares the same information.

## 5. On-call
### 5.1 Rotation
On-call rotates weekly. Handover happens on Mondays at 10:00 CET, and the outgoing engineer must post a handover summary in the #oncall channel. Engineers receive a stipend of $400 for each on-call week.

### 5.2 Paging and escalation
The on-call engineer must acknowledge a page within 5 minutes. If there is no acknowledgement within 5 minutes, the secondary on-call engineer is paged. If there is no acknowledgement within 10 minutes, the engineering manager is paged.

### 5.3 Swapping shifts
Engineers may swap on-call weeks with a colleague, but the swap must be recorded in the on-call tool before the week begins.

## 6. Incident handling steps
1. **Detect and acknowledge.** Acknowledge the page and open a thread in #incident-war-room.
2. **Assess.** Decide the severity and appoint an Incident Commander. The on-call engineer is the Incident Commander by default.
3. **Stabilise.** Restore service first; find the root cause later. Prefer rollbacks and feature flags over live fixes.
4. **Communicate.** Post updates at the intervals defined in section 4.
5. **Resolve.** Confirm that metrics have returned to normal for at least 30 minutes.
6. **Review.** Schedule the post-incident review.

## 7. Safety events involving robots
When a robot is involved in a safety event, the Operations Lead immediately puts all robots of the affected site in hold mode using the HX-Fleet console. Robots stay in hold mode until the safety team has completed its review and signed the release form. The customer's site manager is called by phone; email alone is not sufficient. Any injury must be reported to the head of safety within 1 hour.

## 8. Rollbacks
A rollback of a firmware or platform release should be started when a SEV1 incident is traced to that release and no fix is available within 30 minutes. Rollbacks follow the staged process described in the Engineering Handbook, but the Incident Commander may skip the soak periods.

## 9. After the incident
A blameless post-incident review must be held within 5 business days of resolution and must produce action items with owners and due dates. Action items must be completed within 30 days, unless the engineering manager grants an extension. The review document includes a timeline, the root cause, what went well, what went badly and what was lucky. Reviews are shared with the whole engineering team and, for SEV1 incidents, a summary is sent to affected customers.

## 10. Frequently asked questions
**How fast must I respond to a SEV1 page?** Within 15 minutes; acknowledge the page within 5 minutes.

**Who is paged if I do not acknowledge?** The secondary on-call engineer after 5 minutes, and the engineering manager after 10 minutes.

**How often is the status page updated during SEV1?** Every 30 minutes.

**When is the review held?** Within 5 business days of resolution.
