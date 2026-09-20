# Form Templates

Three collection types. Nothing else justifies a form.

| Type | Need | Destination |
|---|---|---|
| `acknowledgement` | confirm people saw their assignments | email notification |
| `signoff` | record explicit approval of a decision | Google Sheets |
| `feedback` | gather input the meeting did not settle | Google Sheets |

---

## `acknowledgement`

Title: `{meeting_title} — Acknowledgement {date}`

| # | Question | Type | Required |
|---|---|---|---|
| 1 | Your name | dropdown, from `recipients` | yes |
| 2 | I have reviewed my assigned tickets | checkbox | yes |
| 3 | Anything recorded incorrectly? | short text | no |

Three questions. Anything longer stops being an acknowledgement and starts being a
survey people skip.

---

## `signoff`

Title: `{meeting_title} — Sign-off {date}`

| # | Question | Type | Required |
|---|---|---|---|
| 1 | Your name | dropdown, from `recipients` | yes |
| 2 | Decision being signed off | pre-filled, read-only | — |
| 3 | Do you approve? | radio: Approve / Approve with comment / Object | yes |
| 4 | Comment | paragraph | required if not plain Approve |
| 5 | Date reviewed | date | yes |

Question 2 is pre-filled from the decision text in the report, verbatim. People
signing off on a paraphrase are not signing off on the decision.

---

## `feedback`

Title: `{meeting_title} — Feedback {date}`

| # | Question | Type | Required |
|---|---|---|---|
| 1 | Your name | dropdown, from `recipients` | no |
| 2 | Which topic is this about? | dropdown, from report topics | yes |
| 3 | Your input | paragraph | yes |
| 4 | Does this change an action item? | radio: Yes / No / Not sure | no |
| 5 | Which item? | dropdown, from ticket keys | no |

Name is optional here and required in the other two. Feedback people will not put
their name to is often the feedback worth having; a sign-off without a name is
worthless.

---

## Rules

| Rule | Why |
|---|---|
| Name is a dropdown from `recipients`, never free text | free text does not reconcile against Jira |
| Never ask for anything already in Jira | duplicate state that immediately diverges |
| Never ask for contact details | already known, and it reads as a phishing form |
| Pre-fill decision and ticket text verbatim | people approve what they read |
| Sheets destination past three questions | email notifications do not aggregate |

## Response handling

Responses land in Sheets or an inbox. Nothing in this pipeline reads them back —
there is no step 7. If responses need to drive Jira updates, that is a separate
workflow, and the form should say so rather than implying an automatic effect it
does not have.
