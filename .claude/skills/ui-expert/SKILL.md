---
name: ui-expert
description: Design rules and checklist for any change to Substrakt's interface under src/ (Overview, Review, Templates, Settings and the paths between them). Load before UI work on Substrakt; it states the 14 rules R1 to R14 with reason and source, the owner's word decisions and the checklist each changed screen must pass.
---

# UI expert for Substrakt

Load this skill before any change under `src/`. It holds the design rules from
the UI audit of 19 November 2026 and the checklist that turns
them into a proof per screen. It does not repeat the existing rules; read
these alongside it:

- `docs/harness/03-frontend.md`: four places, one dark button, texts only in
  `src/i18n/`, word gate, colour tokens, coordinate boundary.
- `docs/design/design-language.md`: the visible language, surfaces, type,
  spacing and the colour meanings.
- `docs/decisions.md`, section “Interface clarity”: the owner's decisions
  these rules serve (hidden manual path, Enter never approves, words).

Where a rule here and one of those files disagree, the code wins, then the
file is corrected (`CLAUDE.md`, section “Sources”).

## Rules

A clerk on a Windows desktop should see the next step at once, find nothing
stated twice, and never read a status that the content below contradicts.
Each rule names why it holds and where the reason comes from.

| # | Rule for Substrakt | Reason | Source |
|---|---|---|---|
| R1 | Each screen states one thing exactly once: a number or status shows up in only one place. | Repeated information adds load and helps nobody (redundancy effect); it also competes with what matters. | S10, S1 (#8) |
| R2 | A screen offers at most one primary next step, and that step is reached by the shortest route. | Decision time grows with the number of choices; one obvious action keeps it low. | S8, S6 |
| R3 | The status line must not contradict what is shown below it. | Visibility of system status only works when the status is true. | S1 (#1) |
| R4 | Explanatory prose goes on the screen only if the next decision needs it; anything else comes up on request. | Progressive disclosure: frequent things in front, rare things one level deeper, two levels at most. | S2, S1 (#8) |
| R5 | The same thing has the same word, symbol and position on every place (back link, save, „Belegart“). | Consistent identification lets people reuse what they have learned. | S5 (3.2.4), S1 (#4) |
| R6 | Every list row a person can act on is clickable across its whole width and leads to the action. | Larger, closer targets are faster and more reliable to hit. | S9, design-language.md |
| R7 | Every task in the core loop (review, decide, release, report) can be done by keyboard, with the same keys on every screen (Enter = primary, Esc = back). | Keyboard operability and expert efficiency. | S5 (2.1.1), S1 (#7) |
| R8 | An approval shows the evidence for each value next to the value; nothing ticks itself on a document no one has looked at. | Automation bias leads to errors of omission and commission, and training alone does not stop it; the interface has to direct attention to the evidence. | S7 |
| R9 | The evidence on the document and the value stand together: the place in question is shown large enough to read, not at a 27 % zoom. | Split attention between separated sources raises cognitive load. | S10 |
| R10 | Errors and refusals appear next to their cause, in plain words with the way out, and input is kept. | Error-message guidelines. | S3, S1 (#9) |
| R11 | Every empty state says why it is empty and offers the one action that fills it. | Empty states should give status, a cue and a direct path. | S4 |
| R12 | An irreversible or wide action (release everything, leave without saving) asks for confirmation or can be undone. | Error prevention; confirmation only where consequences are large. | S6, S1 (#3, #5) |
| R13 | Feedback after an action appears where the action happened, without moving focus. | Command feedback inside the UI; status messages without interruption. | S6, S5 (4.1.3) |
| R14 | Settings take effect in one consistent way: either everything at once or everything through one save. | Consistency; otherwise people cannot tell what has been stored. | S1 (#4), S5 (3.2.4) |

## Words decided by the owner

The word lists in `docs/harness/03-frontend.md` and the gate in
`tests/frontend/places.test.tsx` stay in force. On top of them the owner
decided (`docs/decisions.md`, “Interface clarity”), because „Vorlage“
meant both the assistant's template and a kind of the folder (R5):

- A kind of document is called „Belegart“ on screen, in English “document
  kind”, not „Vorlage“ or “template”.
- „Profil“ (pipeline profile) appears on no place outside „Einstellungen →
  Technische Details“. What a profile decides is described in words of the
  clerk's work.
- The name of the target comes from the title of the profile and stands in
  no text of `src/i18n/`.

Until the dictionaries and the word gate carry this, a change that touches a
text with „Vorlage“ or „Profil“ applies it, in `src/i18n/de.ts` and
`src/i18n/en.ts` alike.

## Checklist per changed screen

Run it for every screen the change touches, in German and English. The
proof goes into the hand-over report, one line per point.

- [ ] **One dark button** (R2): exactly one `bg-ink` button, and it is the
  next step; `tests/frontend/places.test.tsx` counts it.
- [ ] **Status matches content** (R3): every headline, count and state line
  agrees with the rows below it, also when the list is filtered or empty.
- [ ] **Nothing twice** (R1): no number, state or explanation stands in two
  places on the screen; prose that the next decision does not need is behind
  a disclosure (R4).
- [ ] **Enter and Esc** (R7): Enter triggers the dark button, Esc goes back,
  every action is reachable by Tab with a visible focus ring; a Vitest case
  presses the keys.
- [ ] **Empty state with its action** (R11): the empty screen says why it is
  empty and offers the one action that fills it.
- [ ] **Error next to its cause** (R10): a refusal stands beside the control
  or value that caused it, says the way out, and keeps what was typed.
- [ ] **Feedback in place** (R13): a confirmation appears where the action
  happened, as a status message (`role="status"`), without moving focus.
- [ ] **Wide actions confirmed** (R12): release all, delete and leaving
  unsaved input ask first or can be undone.
- [ ] **Words** (R5): same word, symbol and position for the same thing on
  every place; „Belegart“ instead of „Vorlage“, no „Profil“, no term from
  `FORBIDDEN_DE` or `FORBIDDEN_EN`, texts only in `src/i18n/`.
- [ ] **Rows and evidence** (R6, R8, R9): an actionable row is clickable
  across its width; a value to approve shows its place in the document,
  readable, next to it.
- [ ] **Screenshots in light and dark theme**: one per changed screen and
  theme, in German and English, with the script that took them (the theme
  is the `localStorage` key `substrakt.theme`, `light` or `dark`). Screenshots
  never go into the core: they are filed in the private repository of the
  customer setup, under a folder named after the task. Look at each one
  before naming it as proof.

## Sources

All retrieved on 19 November 2026.

| # | Source | Read |
|---|---|---|
| S1 | Nielsen Norman Group, *10 Usability Heuristics for User Interface Design*, https://www.nngroup.com/articles/ten-usability-heuristics/ | full text |
| S2 | NN/g, *Progressive Disclosure*, https://www.nngroup.com/articles/progressive-disclosure/ | full text |
| S3 | NN/g, *Error-Message Guidelines*, https://www.nngroup.com/articles/error-message-guidelines/ | full text |
| S4 | NN/g, *Designing Empty States in Complex Applications*, https://www.nngroup.com/articles/empty-state-interface-design/ | full text |
| S5 | W3C, *WCAG 2.2* (SC 1.4.1, 2.1.1, 2.4.7), https://www.w3.org/TR/WCAG22/; *Understanding SC 3.2.4 Consistent Identification*, https://www.w3.org/WAI/WCAG22/Understanding/consistent-identification.html; *Understanding SC 4.1.3 Status Messages*, https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html | full text |
| S6 | Microsoft, *Commanding basics (Windows apps)*, https://learn.microsoft.com/en-us/windows/apps/design/basics/commanding-basics | full text |
| S7 | Parasuraman and Manzey (2010), *Complacency and bias in human use of automation: an attentional integration*, Human Factors 52(3), 381–410, https://doi.org/10.1177/0018720810376055; abstract at https://pubmed.ncbi.nlm.nih.gov/21077562/ | abstract only |
| S8 | Hick (1952), *On the rate of gain of information*, Q. J. Exp. Psychol. 4(1), 11–26, https://doi.org/10.1080/17470215208416600 | metadata only |
| S9 | Fitts (1954), *The information capacity of the human motor system in controlling the amplitude of movement*, J. Exp. Psychol. 47(6), 381–391, https://pubmed.ncbi.nlm.nih.gov/13174710 | metadata only |
| S10 | Sweller (1988), *Cognitive load during problem solving: Effects on learning*, Cognitive Science 12, 257–285, https://doi.org/10.1207/s15516709cog1202_4 | citation only; split-attention and redundancy effects from secondary sources |

Apple's Human Interface Guidelines could not be read (the page renders by
script) and are not a source. A rule whose source was read only as abstract
or metadata rests on the commonly cited finding, not on a reading of the
paper; do not strengthen it beyond the wording above.
