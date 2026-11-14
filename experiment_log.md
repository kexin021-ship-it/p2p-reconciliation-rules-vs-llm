# Experiment log — P2P month-end reconciliation: rules vs LLM

Data: `odoo_p2p_10po.zip` (10 POs, Odoo-style tables, October 2026 close, run date 2026-11-10).
Answer key: `answer_key/expected_findings.csv`.
These 10 POs are the **development set**: prompts/architectures are tuned on them.
Final reported results must come from a fresh, held-out set of POs built later.

## v1 — baseline (2026-11-12, model gpt-5.4-mini)

| | Rules | Fixed workflow | Free agent |
|---|---|---|---|
| Cause correct | 6/10 | 7/10 | 7/10 |
| Cause + location | 6/10 | 6/10 | 6/10 |
| Extra findings | 1 | 4 | 3 |
| Evidence in notes (5 POs) | 2/5 | 4/5 | 5/5 |
| Evidence in structured data (4 POs) | 4/4 | 3/4 | 2/4 |
| Evidence nowhere (1 PO) | 0/1 | 0/1 | 0/1 |

Files: `rules_findings.csv`, `llm_findings.csv`, `agent_findings.csv`.

Observations:
- Free agent did not investigate: it read all 9 tables in full in one step and submitted in step 4.
  Only possible because the data is tiny.
- Error types seen in the LLM runs:
  1. Right explanation, wrong label (P00005 both; P00003 agent) — the label was written before the explanation.
  2. Matching/arithmetic across several documents (P00008 workflow missed the 2nd bill; P00005 agent said "no October bill").
  3. Reporting records that are fine (P00004 workflow: "bill is fine, no correction").
  4. Cause without evidence (P00010 agent invented a timing explanation).
- Same model, different architecture → P00009 (cut-off) wrong in workflow, right in agent:
  the gap is architecture/prompt, not model capability.

Scoring fix after v1 (not a model change): `evaluate.py` treats `account_move_line:1` and
`account.move.line:1` as the same record (agent used table names with underscores).
Note: the v1 agent run used a shared rule text that said "the records" instead of "the records given" (one word; immaterial).

## v2 — changes decided on the dev set (2026-11-12, model unchanged: gpt-5.4-mini)

| # | Change | Fixed workflow | Free agent |
|---|---|---|---|
| 1 | Explanation written before cause_category / problem_key | ✓ | ✓ |
| 2 | Reconciliation | Prompt requires a worksheet the model fills in itself: (a) each receipt/return: picking, month, qty, value, PO line, PO; (b) each bill line: bill, month, qty, unit price, amount, PO line, PO; (c) October receipt vs bill per PO line, then per PO; (d) PO price vs agreed price vs each bill price | New tool `get_po_records` (tool B): returns all records linked to one PO, unprocessed; the agent decides when to use it and does the maths itself |
| 3 | One difference = one finding, on the record that caused it; no "checked, all fine" findings | ✓ | ✓ |
| 4 | Every cause must cite a supporting record; otherwise insufficient_evidence | ✓ | ✓ |

Deliberately NOT changed in v2:
- Category definitions (e.g. whether "billing for returned goods" is vendor_overbilled) — to see whether v2 alone fixes P00005.
- P00010 answer key (overbilled vs insufficient evidence is debatable) — revisit after v2 results.
- Model.

New metric: worksheet arithmetic accuracy (workflow only) — the LLM's own October receipt / bill /
difference per PO vs the true figures (`python evaluate.py llm_findings_v2.csv llm_worksheet_v2.csv`).

Caveat for interpreting workflow vs agent: both now do the maths themselves, but the workflow follows
prescribed steps while the agent chooses its own approach.

Files: `llm_findings_v2_run<N>.csv`, `llm_worksheet_v2_run<N>.csv`, `agent_findings_v2_run<N>.csv` (run 1 = the first single run), raw replies and agent traces in `llm_raw_v2/`.

Housekeeping (2026-11-12): fixed-workflow script renamed `llm_agent.py` -> `llm.py`; both scripts support `--runs N`; `python evaluate.py --runs <prefix>` summarises across runs.

### v2 results (single run each)

| | Rules | Workflow v1 | Workflow v2 | Agent v1 | Agent v2 |
|---|---|---|---|---|---|
| Cause correct | 6/10 | 7/10 | 6/10 | 7/10 | 8/10 |
| Cause + location | 6/10 | 6/10 | 6/10 | 6/10 | 8/10 |
| Extra findings | 1 | 4 | 1 | 3 | 2 |
| Worksheet totals correct | — | — | 10/10 | — | — |

Workflow v2:
- Worksheet arithmetic perfect (incl. P00008's two bills summed correctly).
- Judgment collapsed to "timing" on P00004, P00005, P00009, P00010 although the notes were read.
  P00004 explanation contradicts itself (says 2 units taken back, concludes "not yet invoiced");
  P00010 claims later billing with no evidence (evidence rule not followed).
- Hypothesis: worksheet focuses attention on receipt month vs bill month, and the broad "timing"
  definition ("rest will be billed later") becomes a catch-all.

Agent v2 (still read everything up front: list_tables, 3 queries, get_po_records x10, submit in step 4):
- Fixed: P00003 (label now consistent with explanation), P00010 (insufficient_evidence — evidence rule worked).
- Still wrong: P00005 (unrecorded_return — category definition issue, deliberately untouched);
  P00009 (timing; agent v1 had it right); P00008 extra "half not billed yet" finding (two bills not summed);
  P00003 reported twice.

Open issue — run-to-run variance: P00009 flipped between agent v1 and v2 although no v2 change concerns cut-off.
With 10 POs, one PO = 10 percentage points. Proposed next: 3 runs per configuration before further changes.

### v2 repeated runs (3 runs each; run 1 = the single run above)

| | Workflow v2 | Agent v2 |
|---|---|---|
| Cause correct per run | 6, 6, 6 (mean 6.0) | 8, 9, 10 (mean 9.0) |
| Cause + location, mean | 6.0 | 8.0 |
| Extra findings, mean | 1.0 | 1.7 |
| Worksheet totals correct | 10/10 every run | — |

Workflow v2 — stable, systematic errors:
- Always wrong: P00005, P00009, P00010, every time labelled "timing". Unstable: P00004 (1/3), P00007 (2/3).
- Pattern: treats "waiting for something" as timing (P00005 "credit note will come"; P00009 "receipt validated in November")
  although the physical event (return / arrival) happened in October.

Agent v2 — better on average, more variable:
- P00009 right 2/3 (run 1 miss was largely chance); P00005 right 2/3 even without a definition change.
- Run 2 omitted P00001 entirely (possible over-application of "don't report fine records").
- P00007 runs 2-3: pointed at purchase.order.line:7 (the PO to be updated) instead of account.move.line:7 —
  arguably also correct; answer-key location may be too narrow (park with P00010 key question).

Lesson: single runs are misleading at n=10; compare configurations on 3 runs from now on.

Proposed next (diagnostic): workflow v2 without the worksheet step, 3 runs, to test whether the worksheet framing
causes the "timing" bias. Diagnostic only — if confirmed, redesign the worksheet rather than drop it.

## v3 — workflow worksheet redesign (2026-11-12, model unchanged)

Decision: skip the diagnostic (worksheet removed) run and improve the worksheet directly. Reviewing one PO at a
time is kept on purpose: it mirrors how an AP analyst works.

Only change vs workflow v2 — two extra worksheet steps:
- e. List every chatter note: what it says actually happened (arrived, returned, taken back, damaged, price
  agreed/rejected, billing promised) and when; mark routine notes.
- f. For each real event, compare with the system records: recorded or not, date/quantity match, reflected on
  the bill; write down every mismatch between what happened and what the system shows.

Reason: in v2 the notes were only consulted after the worksheet, so "receipt and bill in different months"
won over "what physically happened" (P00005, P00009, P00010 labelled timing in 3/3 runs).
The agent stays at v2 (no worksheet by design).

Files: `llm_findings_v3_run<N>.csv`, `llm_worksheet_v3_run<N>.csv`, raw replies (incl. note_events) in `llm_raw_v3/`.

### v3 results (3 runs)

| | Workflow v2 | Workflow v3 | Agent v2 |
|---|---|---|---|
| Cause correct, mean | 6.0 | 8.0 (9, 8, 7) | 9.0 |
| Cause + location, mean | 6.0 | 6.3 | 8.0 |
| Extra findings, mean | 1.0 | 2.3 | 1.7 |
| Worksheet totals correct | 10/10 x3 | 10/10 x3 | — |

- Fixed: P00004 (1/3 -> 3/3), P00005 (0/3 -> 2/3).
- P00009: step f recorded the mismatch correctly in 3/3 runs ("arrived in October, recorded in November"),
  yet 2/3 runs still chose "timing". The model sees the problem but the category boundary is unclear:
  the timing definition ("receipt and bill fall in different months") literally fits.
- P00010: model wrote "no note or return record showing a valid reason for billing the extra 4 boxes" and chose
  vendor_overbilled — consistent with our own definition ("no valid reason"). Answer key is debatable.
- P00005 run 3: still unrecorded_return although the return document exists.
- Location: P00007 always pointed at purchase.order.line:7 (PO price to be updated — defensible);
  P00002 runs 2-3 pointed at the PO line (less defensible).
- Extras up: run 3 reported a fine receipt on P00003 as "timing" (no mismatch) — step e/f invites per-note comments.
- Minor: matches_system flag sometimes "true" while a mismatch is written.

Conclusion: remaining errors are mostly overlapping category definitions:
timing vs cut_off_error (P00009), unrecorded_return vs vendor_overbilled (P00005),
vendor_overbilled vs insufficient_evidence (P00010). Next: clarify definitions one pair at a time.

## v4 — shared category definitions (2026-11-12, model unchanged)

Applies to BOTH architectures (shared definition text). Agent jumps v2 -> v4 so that "v4" means the same
definitions on both sides; workflow v4 = workflow v3 worksheet + new definitions.

| Pair | Change |
|---|---|
| timing vs cut_off_error | timing only when all system records are correct. Decision rule: if what actually happened (per notes) differs from what the system shows, it cannot be timing (workflow: explicitly tied to worksheet step f). cut_off_error applies even when it looks like timing. |
| unrecorded_return vs vendor_overbilled | Judged on NET received quantity (receipts minus returns, counting reversed returns) — not on whether a return document exists (user's point: a return can itself be reversed, or recorded only partly). Billing for goods the system already shows as returned = vendor_overbilled. |
| vendor_overbilled vs insufficient_evidence | vendor_overbilled = price above agreed/approved, or qty above what the system shows we kept, with no justifying record. insufficient_evidence only when records contradict each other. |

Knock-on change: the evidence rule no longer says "if no record shows why, use insufficient_evidence";
it now says "never use a reason that no record supports" (anti-hallucination intent kept).

Answer key change: P00010 insufficient_evidence -> vendor_overbilled. Reason: AP practice — billed more than received
with no explanation is first treated as a vendor overbilling and queried with the vendor. Judged too demanding to expect
"several causes possible" reasoning. (Not changed because of results: agent v2 had chosen insufficient_evidence 3/3 and
now loses that PO.) insufficient_evidence has no case in this set; add a "contradicting records" case to the future test set,
plus a "reversed return" case.

### All earlier results re-scored with the updated answer key

| Config | Runs | Cause correct (mean) | Cause + location | Extra | P00010 per run |
|---|---|---|---|---|---|
| Rules | 1 | 7.0 | 7.0 | 1.0 | Y |
| Workflow v1 | 1 | 8.0 | 7.0 | 4.0 | Y |
| Agent v1 | 1 | 7.0 | 6.0 | 3.0 | N |
| Workflow v2 | 3 | 6.0 | 6.0 | 1.0 | N N N |
| Agent v2 | 3 | 8.0 (7, 8, 9) | 7.3 | 1.7 | N N N |
| Workflow v3 | 3 | 8.7 (9, 9, 8) | 7.0 | 2.3 | N Y Y |

Files: `llm_findings_v4_run<N>.csv`, `llm_worksheet_v4_run<N>.csv`, `agent_findings_v4_run<N>.csv`, raw in `llm_raw_v4/`.

### v4 results (3 runs each)

| | Rules | Workflow v3 | Workflow v4 | Agent v2 | Agent v4 |
|---|---|---|---|---|---|
| Cause correct, mean | 7.0 | 8.7 | 9.7 (10, 10, 9) | 8.0 | 7.3 (7, 8, 7) |
| Cause + location, mean | 7.0 | 7.0 | 9.0 | 7.3 | 6.3 |
| Extra findings, mean | 1.0 | 2.3 | 0.7 | 1.7 | 1.3 |
| Worksheet totals correct | — | 10/10 x3 | 10/10 x3 | — | — |

Workflow v4: P00005 and P00010 3/3; P00009 2/3 (correct runs state "arrived in October, recorded in November,
October receipts understated by 1,500"). Only location misses: P00007 pointed at the PO line (parked answer-key question).

Agent v4: P00001 and P00002 (pure timing) omitted in 3/3 runs — no finding at all. Run 1 fetched P00001's records
and still left it out. Likely cause: new timing definition ("nothing is wrong") + "leave out what needs no action"
read as "timing is not worth reporting". The workflow is immune because its worksheet forces every PO through.
P00010: insufficient_evidence 2/3 — agent reads "can't tell vendor vs warehouse" as "records contradict".

Proposed next (agent only): deliverable standard "the difference must reconcile" — every PO with an October difference
gets at least one finding, timing included; before submitting, check that the differences explained add up to
total October bills minus total October receipts. P00010 drift to be handled in a later round (one change at a time).

## Agent v5 — "the difference must reconcile" (2026-11-12, agent only; workflow stays v4)

Only change vs agent v4 (prompt + one output field):
- Every PO with a non-zero October difference needs at least one finding, timing included.
- Each finding carries explained_difference (bill minus receipt it explains).
- Before submitting, the agent checks the explained differences add up to total October bills minus receipts.
Rationale: a month-end reconciliation must account for the whole difference (timing items are reconciling items);
this is a deliverable standard, not a restriction on how the agent investigates. The run printout shows
the agent's explained total vs the actual difference (900); the actual figure is never shown to the agent.

Files: `agent_findings_v5_run<N>.csv` (extra column explained_difference), traces in `llm_raw_v5/`.

### Agent v5 results (3 runs)

| | Agent v4 | Agent v5 | Workflow v4 |
|---|---|---|---|
| Cause correct, mean | 7.3 | 7.7 (7, 8, 8) | 9.7 |
| Cause + location, mean | 6.3 | 7.0 | 9.0 |
| Extra findings, mean | 1.3 | 0.7 | 0.7 |

- P00001 still omitted 3/3; P00002 reported 1/3. P00008 insufficient_evidence once; P00010 insufficient_evidence once.
- The reconcile check was NOT performed: the agent's explained_difference totals were 700, -5,600 and -100
  (actual 900), and it submitted anyway. Traces: read everything, then submitted in one step — no summing step.
- Sign errors in explained_difference (e.g. P00004 +400 instead of -400; run 2 P00009 -1,500, P00008 -810).
- Run 1 never fetched P00001: it pre-screened POs from the raw tables and skipped it.

Key finding: the same small model reconciled 100% correctly when the workflow made it fill a worksheet step by step
(9/9 runs), but in free-agent mode it skipped the requested self-check and mis-signed figures. For reconciliation
(complete, reproducible), prescribed structure beats autonomy — consistent with the original architecture rationale.

Options proposed: (A) one more agent round making the check enforceable — state the total difference to explain
(realistic: a month-end reconciliation starts from the reported difference) and have submit_findings bounce the
submission when the explained total does not match; (B) stop agent tuning and build the held-out test set.
Recommendation: A once, then B regardless.

## Agent v6 — reconciliation check enforced by the submit tool (2026-11-12, agent only)

Only change vs agent v5. The agent still computes every figure itself; the code acts as a grader that says
WHAT is wrong but never gives the correct figure (user's point: the agent must work out the total itself — in
production no one would type it in, and "can it compute a simple total?" is part of what we are testing).
1. The agent must compute and submit total October bills, total October receipts and the total difference.
2. submit_findings rejects the submission when:
   - its bill or receipt total is wrong ("your bill total (X) is wrong - recompute"; correct figure not given);
   - its difference is not its own bills minus receipts;
   - its findings' explained_difference does not add up to its own total difference ("adds up to X, your
     total is Y, gap Y-X" — both the agent's own numbers).
3. At most 5 rejections (user: 3 may not be enough given v5); a 6th failing submission is accepted and logged as
   NOT reconciled. Each submission's totals are logged (trace: submissions, bounces, reconciled).
New measure: whether the agent's own totals were right at first submission / at the end.
Workflow stays v4. After this round, move to the held-out test set regardless of the result.

Files: `agent_findings_v6_run<N>.csv`, traces in `llm_raw_v6/`.

### Agent v6 results (3 runs)

| | Agent v5 | Agent v6 | Workflow v4 |
|---|---|---|---|
| Cause correct, mean | 7.7 | 9.0 (10, 9, 8) | 9.7 |
| Cause + location, mean | 7.0 | 9.0 | 9.0 |
| Extra findings, mean | 0.7 | 0.7 | 0.7 |
| Steps per run | 4-6 | 15-17 | 1 call per PO |

- P00001 now reported 3/3; P00002 missed in run 3; P00005 right 1/3 (unrecorded_return, timing).
- NO run reconciled: all 3 runs hit the 5-rejection limit. In 18 submissions the agent's own October totals were
  never correct (bills 17,190 / 14,290->13,090 / 17,690->16,090 vs 17,390; receipts 16,050 / 12,650->13,150 /
  15,650->14,040 vs 16,490). After "recompute", it resubmitted the same or another wrong figure. Sign errors persisted
  (run 2 P00002 +2,000 instead of -2,000).
- The score gain came from the extra investigation rounds triggered by rejections (15-17 steps vs 4-6), which made
  it revisit and report the timing POs — not from reconciling.

Key finding: the same small model is reliable at arithmetic only when it writes the working out line by line
(workflow worksheet: 30/30 PO totals correct). In free-agent mode it sums dozens of figures from scattered tool
results without written steps and gets them wrong 18/18 times. Judgment can match the workflow; arithmetic cannot,
and it costs several times more model calls.

Dev-set tuning stops here. Configurations for the held-out test set: Rules, Workflow v4, Agent v6.

## Pre-test-set review (2026-11-12)

Reviewing each component before freezing for the held-out test set.

### Rules review — fix + new shared category
- Bug: bill price BELOW the PO price was labelled vendor_overbilled (rules_baseline.py, price branch). There was no
  category for it. Not triggered by the 10 dev POs, so dev scores are unchanged (rules still 7/10).
- Fix (user's call): new category vendor_underbilled, added to ALL three so the category set stays identical:
  rules (price below PO/agreed -> vendor_underbilled, action "confirm with vendor; supplementary bill may follow"),
  and the shared LLM definitions: "billed less than it should - unit price below the agreed price (PO price correct),
  or fewer units than we kept with no record saying the rest will be billed later - and no record justifies it
  (e.g. an approved discount)". approved_price_change now explicitly covers approved discounts.
- Rules still cannot detect quantity underbilling (no notes -> "received more than billed" stays timing).
- Version bump because the LLM prompts changed: workflow v4 -> v5, agent v6 -> v7 (no other change).
  Not run yet (user: finish the review first). Plan: one quick dev-set run each to confirm no regression,
  and include an underbilling case in the test set.

### Rules review — month-end cut-off (user's finding)
- Bug: the quantity check summed ALL receipts and bills on a line regardless of date, so November documents
  entered the October reconciliation. Example (user): Oct receipt 10, Oct bill 10, Nov return 10 -> rules saw net
  received 0 vs billed 10 and would flag vendor_overbilled, although at 31 Oct nothing was wrong.
  Dev results were right only by coincidence (P00002, P00009).
- Fix: all price and quantity checks are made as at CUTOFF = 2026-10-31. Documents after the cut-off never enter
  the October figures; they are only used as later evidence (a November bill shows an October receipt was billed
  later -> timing; a November receipt shows an October bill was received later -> timing).
- Dev set: identical findings (7/10, same keys). Tested: Oct receive 40 / Oct bill 40 / Nov return 40 -> no finding
  (old logic: overbilled); a November credit note does not remove an October overbilling.
- LLM side not affected (every document carries its date; the worksheet works month by month). The PO-line fields
  qty_received / qty_invoiced are run-date figures as Odoo shows them — kept as a realistic trap.
- Test-set candidate: "Oct receipt, Nov return".

### Fixed-workflow review (2026-11-13)
Changes (llm.py v5, still not run):
- Month-end cut-off written into the SHARED rules (so the agent gets it too, consistent with the rules fix):
  only documents dated up to 2026-10-31 count toward October values, quantities and prices; later documents are
  evidence only; the PO-line fields qty_received / qty_invoiced are run-date figures and must not be used for the
  month-end position. Worksheet step c: post-cut-off documents stay listed but are not counted.
- Sampling: reasoning_effort="none" (gpt-5.4-mini's default per OpenAI docs — so earlier runs already used it; now
  explicit) and temperature=0. GPT-5.4 models accept temperature only with reasoning effort "none".
  temperature=0 makes outputs as stable as possible but OpenAI does not guarantee identical results, so keep 3 runs.
Noted, not changed: one PO at a time cannot see cross-PO problems (bill posted to the wrong PO, same bill on two POs);
notes attached to the vendor rather than to the PO's documents are not collected. Consider for the test-set design.

### Agent review (2026-11-13)
- Sampling aligned with the workflow: reasoning_effort="none", temperature=0 (agent v7, still not run).
- Why the code / workflow get the October totals right and the agent does not:
  - Code (agent.py, used only by the grader): sums amount_untaxed of the 10 bills dated in October (17,390) and the
    value of the 13 stock moves dated in October (16,490), returns included as negative values.
  - Workflow: per PO it writes every document out (month, qty, value) in the worksheet and adds 1-3 figures per line,
    then 1-3 lines per PO — many small written additions.
  - Agent: must pick the 23 October figures out of many tool results spread over the conversation, filter by date,
    apply signs, and write only the final totals into one JSON field. With reasoning_effort="none" the model has no
    hidden thinking either, so this is mental arithmetic on ~23 numbers with no place to write the working.
- New agent tool `calculate` (user's choice B over "write a worksheet in the submission" / "leave as is"):
  safe arithmetic only (numbers, + - * / and brackets). The agent still decides which figures to include and how;
  the tool only computes. Prompt: "use the calculate tool for every sum, difference or product". Every call is
  logged in the trace. Motivation: wrong totals 18/18 in v6 and each rejection costs another model call.
  Note for the report: with the calculator, arithmetic accuracy is no longer the agent's own; what remains the
  agent's is choosing the right documents, dates and signs.

### Incident (2026-11-13): stale scripts on the computer
Before the dev-set check run, llm.py, agent.py and rules_baseline.py on the computer had reverted to older versions
(no month-end cut-off, no temperature setting, no calculator) — most likely VS Code saving open editor tabs over the
updated files. Consequence: llm_findings_v5_run1-3 / llm_worksheet_v5_run1-3 / llm_raw_v5 (13 Nov ~18:20) were produced
by the OLD llm.py and are INVALID; to be deleted and re-run. The agent run failed at import (no results).
Fix: latest versions written back and verified byte-for-byte by reading them back from the computer
(llm.py, agent.py, rules_baseline.py, make_data.py, evaluate.py, answer key all match).

### Dev-set check after the review (2026-11-13, 3 runs each, temperature 0)

| | Workflow v4 | Workflow v5 | Agent v6 | Agent v7 |
|---|---|---|---|---|
| Cause correct, mean | 9.7 | 9.0 (9, 9, 9) | 9.0 | 6.3 (5, 7, 7) |
| Cause + location, mean | 9.0 | 8.3 | 9.0 | 6.3 |
| Extra findings, mean | 0.7 | 1.0 | 0.7 | 1.3 |
| Worksheet totals correct | 30/30 | 30/30 | — | — |
Rules (with month-end cut-off): 7/10, unchanged.
temperature=0 still leaves run-to-run variance (P00004, P00009 differ between runs).

Workflow v5 — two regressions, both side effects of the new shared text:
- P00004 run 3 -> vendor_underbilled although the explanation says 2 units were taken back by the driver. The new
  definition ("fewer units than we kept...") literally fits the system view (10 received, 8 billed):
  boundary vendor_underbilled vs unrecorded_return unclear.
- P00009 right 1/3 (v4: 2/3). Run 1 explanation literally says "This is a month cut-off issue" yet labels timing.
  The new rules section was titled "Month-end cut-off" and its examples are all "later documents = timing evidence";
  same word as the category cut_off_error -> likely confusion.

Agent v7 — calculator used (20-22 calls/run); bill total right in every submission (17,390). But:
- Receipt totals wrong in runs 1-2 (wrong figures chosen: September receipt included, bill amounts used as receipts).
- Run 3 had correct totals (17,390 / 16,490 / 900) but resubmitted the same findings (sum 1,400) 6 times.
- Root cause: incomplete per-PO aggregation on multi-line / multi-bill POs — P00003 counted only the bolt line
  (receipt 1,200 -> invented 500 difference -> wrong labels), P00008 only the first bill (990 -> -810).
- P00001 omitted 2/3, P00002 omitted 3/3. 20-32 steps per run (higher cost than v6).
Lesson: the calculator fixes arithmetic, not document selection; the agent's real weakness is gathering ALL documents
of a PO. The workflow avoids this because code assembles the case file and the worksheet lists every document.

Proposed next (shared text, affects both): (1) vendor_underbilled: goods physically returned / taken back are not
underbilling (check unrecorded_return); (2) rename the "Month-end cut-off" rules section to "Month-end position", avoid
the word cut-off there, and add a decision rule: notes show goods physically arrived in October but the system recorded
them in November -> cut_off_error, not timing. Agent handling to be discussed after.

## Workflow v6 / Agent v8 — two definition fixes (2026-11-13, shared text)
- vendor_underbilled: "Not this category when goods were physically returned or taken back - check unrecorded_return."
- Rules section "Month-end cut-off" renamed "Month-end position" (no "cut-off" wording left outside the category name),
  plus decision rule: notes show goods physically arrived in October but the receipt was recorded after 31 Oct ->
  cut_off_error, not timing.
Nothing else changed. Files: llm_findings_v6_run<N> / llm_worksheet_v6_run<N> / llm_raw_v6, agent_findings_v8_run<N> / llm_raw_v8.

### Correction (2026-11-13): cause of the "reverted files"
The user confirmed VS Code had no files open and the Desktop is not synced by OneDrive. Pattern on closer inspection:
each reverted file carried the mtime of Claude's latest write but the CONTENT of Claude's previous write of the same
file (e.g. 18:45 write -> 18:26 content; 14:29 write -> pre-calculator content). So the cause was on the transfer side
(a stale copy re-used when the same staging path was written again), not the user's computer.
Fix: every write now goes through a fresh, unique staging folder and is verified by reading the file back.
Verified at 18:48: llm.py (v6), agent.py (v8), experiment_log.md, rules_baseline.py, evaluate.py all match.
Validity: workflow v5 and agent v7 results (runs at ~18:28-18:33) used the verified 18:26 versions -> valid.

### Workflow v6 / Agent v8 results (3 runs each)

| | Rules | Workflow v4 | Workflow v6 | Agent v6 | Agent v8 |
|---|---|---|---|---|---|
| Cause correct, mean | 7.0 | 9.7 | 9.7 (9, 10, 10) | 9.0 | 8.5 (8, 9; run 3 no result) |
| Cause + location, mean | 7.0 | 9.0 | 9.3 | 9.0 | 8.0 |
| Extra findings, mean | 1.0 | 0.7 | 0.7 | 0.7 | 1.0 |
| Arithmetic | — | 30/30 | 30/30 | 0/18 | totals right in 16/17 submissions |
| Model calls per run | — | 10 | 10 | 15-17 | 33-60 |

Workflow v6: both fixes worked — P00009 3/3 (v5: 1/3); P00004 never labelled underbilled (run 1 timing, runs 2-3 right).
Best version so far.

Agent v8: with the calculator its October totals were right in 16 of 17 submissions, but the per-PO explained
differences never added up to its own total (sums -1,900 / 600 / 200 / -1,400 ...), so all runs hit the 5-rejection
limit. Run 1 fetched P00001 and still omitted it. Run 3 hit the 60-step limit before an accepted submission -> no
findings file (evaluate.py currently skips such a run). 31-41 calculator calls per run.

Proposed: freeze Workflow v6 and Agent v8 for the held-out test set; a run that ends without accepted findings counts
as a failed run (all POs wrong) in the test-set scoring.


## FROZEN for the held-out test set (2026-11-13, user decision)

Configurations: **Rules** (month-end cut-off + vendor_underbilled), **Workflow v6** (llm.py), **Agent v8** (agent.py),
all on gpt-5.4-mini, reasoning_effort "none", temperature 0. No further prompt/logic changes; the test set is run once
per configuration (3 runs each for the LLM versions) and reported as is.

Scoring rule agreed: an agent run that ends without accepted findings counts as a failed run (all 10 POs wrong).
Implemented without changing agent behaviour: agent.py now writes an empty findings file for such a run (this also
stops the next run from reusing the run number and overwriting the trace); evaluate.py marks it "failed run".
Dev-set Agent v8 with run 3 counted as failed: cause 8, 9, 0 -> mean 5.7; cause + location mean 5.3; extra 0.7.

Fingerprints (SHA-256, first 16 hex chars, line endings normalised for text files):

| File | Fingerprint |
|---|---|
| `rules_baseline.py` | 3cb386f1844d10f9 |
| `llm.py` | 3922bd24b8626e39 |
| `agent.py` | 3567964838876844 |
| `evaluate.py` | f785a1c7b327d38d |
| `odoo_p2p_10po.zip` | a1d41ddb4e2fb4af |
| `answer_key/expected_findings.csv` | 45510984b8f8b6ec |

## Held-out TEST SET (2026-11-14, designed together with the user)

Size 10 POs: 1 normal + one per cause category + 1 trap. October 2026, run date 2026-11-10 (fixed by the frozen
prompts). New vendors/products; PO numbers P00011-P00020 shuffled with a fixed seed. Generator: make_test_data.py;
data: odoo_p2p_test.zip; answer key: answer_key/test_expected_findings.csv (kept outside the zip; column design_case
maps PO -> design number).

| Design | PO | Answer | Scenario | Oct diff |
|---|---|---|---|---|
| 1 | P00014 | none | normal: 3-line PO, two receipts, two bills, all matched; note mentions lamps "out of stock" | 0 |
| 2 | P00020 | timing | tape received Oct, billed on a November bill (two bills) | -1,200 |
| 3 | P00011 | po_price_error | one of three lines entered at 8 instead of agreed 18; bill at 18 looks like overbilling | +500 |
| 4 | P00019 | vendor_overbilled | same delivery billed twice (PS-7781 / PS-7781A) | +2,100 |
| 5 | P00017 | vendor_underbilled | coffee billed at 30 vs agreed 32, no discount on record (twin of 6) | -100 |
| 6 | P00013 | approved_price_change | billed at 19 vs 20; note: 5% discount approved (twin of 5) | -100 |
| 7 | P00012 | unrecorded_return | 4 keyboards taken back by driver (note on receipt), no return; bill for the 26 kept | -160 |
| 8 | P00018 | cut_off_error | receipt confirmed 31 Oct ahead of time; goods arrived 3 Nov (opposite direction to dev P00009) | -1,200 |
| 9 | P00015 | insufficient_evidence | note says 40 boxes arrived, system 36, bill 40 (records contradict) | +72 |
| 10 | P00016 | none (trap) | received + billed 10 in Oct, all returned 6 Nov; run-date qty_received shows 0 | 0 |
October totals: receipts 21,898, bills 21,810, difference -88.

Decisions while designing:
- Cross-PO problems (bill posted to the wrong PO) NOT included: no frozen category can express them -> report as a
  known limitation / future work.
- "Reversed return" dropped from design 7 (user: a reversal can be legitimate, e.g. goods brought back; too
  ambiguous). Design 7 simplified to a plain unrecorded return. Reversed return -> future test case.
- approved_price_change: pointing at the bill line OR the PO line both count as correct (the PO line is the record
  that needs updating; the frozen prompt does not pin this down). Applied to the dev key as well (P00007 widened);
  dev rules score unchanged (7/10).
- Normal / trap POs expect NO finding: right only if nothing is reported; each finding there counts as extra.

Harness changes (no change to prompts, tools, grader or rules logic — verified by fingerprinting the prompt text,
JSON schema, tool definitions, grader/agent-loop/calculator source, rules logic and case-file builder before and after):
- `--test` switch for rules_baseline.py, llm.py, agent.py: read odoo_p2p_test.zip, write test_* outputs.
- evaluate.py: `--test` uses the test answer key; supports expected "none"; failed-run detection by empty file.

Rules on the test set (run once): 6/10 cause, 6/10 cause + location, 1 extra. Right: all 4 structured cases and both
normal POs (incl. the November-return trap -> month-end cut-off works). Wrong: all 4 note-dependent cases
(unrecorded return -> timing; approved discount -> underbilled; contradiction -> overbilled; early receipt -> timing).

Fingerprints after the harness change:

| File | Fingerprint |
|---|---|
| `rules_baseline.py` | 7efe12f5ed4d3220 |
| `llm.py` | 749cbe34436c295f |
| `agent.py` | 804462a508783719 |
| `evaluate.py` | c7e609a2779b067a |
| `make_test_data.py` | b7d44f03ed67031e |
| `odoo_p2p_test.zip` | 8b7bb7cbcdd862e2 |
| `answer_key/test_expected_findings.csv` | e8b1f028d185b7da |
| `answer_key/expected_findings.csv` | 91f84be9d8d4c705 |

## FINAL RESULTS — held-out test set (2026-11-14; frozen versions; LLM versions 3 runs each)

| | Rules | Workflow v6 | Agent v8 |
|---|---|---|---|
| Cause correct, mean | 6 / 10 | 10 / 10 (10, 10, 10) | 5.7 / 10 (6, 6, 5) |
| Cause + location, mean | 6 / 10 | 10 / 10 | 4.7 / 10 |
| Extra findings, mean | 1 | 0 | 4.7 |
| Arithmetic | — | worksheet totals 30/30 | own October totals often right; per-PO differences wrong |
| Model calls per run | 0 | 10 | 13-60 (13, 46, 60 steps) |

By evidence type: structured (4 POs) — rules 4/4, workflow 4/4; note-dependent (4 POs) — rules 0/4, workflow 4/4
(incl. the reversed-direction cut-off P00018 and the contradiction case P00015), agent unstable; normal/trap (2 POs) —
rules 2/2, workflow 2/2, agent right in 1 of 6 (normal POs repeatedly reported as "timing").

Agent detail (traces): run 1 used all 60 steps, 6 submissions, never reconciled (accepted at the rejection limit);
run 2 fetched only 7 of 10 POs, run 3 only 8 of 10.
**Plugging (balancing figure) observed.** Runs 2 and 3 were "accepted - reconciled" only because the agent fabricated
balancing entries: run 2 added a second P00011 finding with explained_difference -2,328 (no basis) after skipping
P00015, P00016 and P00018; run 3 invented a finding on a non-existent record (purchase_order.line:999) for P00018 with
+542, and gave P00012 -1,830, making its total equal -88. The enforced total check rewarded "making the numbers agree"
rather than doing the work — a textbook specification-gaming / plug-figure failure.

Conclusions:
1. LLM beats rules where the evidence is in free text: note-dependent cases rules 0/4 vs workflow 4/4 (3/3 runs).
2. Same model, same definitions: architecture decides. Code-assembled case file + prescribed worksheet (workflow)
   10/10 with 10 calls; free agent 5.7/10 with 13-60 calls, incomplete coverage and false alarms on normal POs.
3. Checking only that results reconcile led the agent to fabricate balancing items. Outcome-only checks need to be
   paired with evidence checks (e.g. every finding must reference an existing record; every PO with a difference
   must be covered).
Limitations: n = 10 POs, designed by the same two people who saw the dev-set results, so the workflow's 10/10 shows
reliability on these patterns, not a general accuracy figure; no cross-PO cases (no category; all three versions
would fail by design); single model (gpt-5.4-mini).
