# Rules vs LLM Workflow vs LLM Agent for Month-End P2P Reconciliation

At month-end, the value of vendor bills booked in a month rarely equals the value of goods received that month, and an accounts payable analyst has to explain every difference before closing. This project compares three ways to find those differences and name their cause, on the same Odoo-style purchase-to-pay data:

- **Python rules**: deterministic checks on structured fields
- **Fixed LLM workflow**: code assembles one purchase order's records; the model follows a prescribed worksheet
- **Tool-using LLM agent**: the model decides which records to fetch, calculates with a tool, and must pass a totals check

Both LLM designs use the same model (gpt-5.4-mini, temperature 0), the same eight cause categories and the same record-fetching code.

## Results on the held-out test set

10 new purchase orders, built after all versions were frozen. Rules are deterministic and run once; each LLM design ran 3 times.

| Measure | Python rules | Fixed LLM workflow | Tool-using LLM agent |
| --- | --- | --- | --- |
| Cause correct (of 10) | 6.0 | **10.0** | 5.7 |
| Cause and location correct (of 10) | 6.0 | **10.0** | 4.7 |
| Extra findings per run | 1.0 | **0.0** | 5.0 |
| Model calls per run | 0 | 10 | 13 to 60 |

By where the evidence sits (share of correct judgements, LLM runs pooled):

| Evidence | Python rules | Fixed LLM workflow | Tool-using LLM agent |
| --- | --- | --- | --- |
| Cause visible in structured data (4 POs) | 100% | 100% | 92% |
| Cause written only in a note (4 POs) | 0% | 100% | 42% |
| Nothing to report (2 POs) | 100% | 100% | 17% |

## Key findings

1. **The LLM's advantage came from cases whose cause is written only in a note.** On the four note-only cases (goods taken back by the driver, an approved discount, a receipt booked before the goods arrived, contradicting records), the workflow scored 4/4 in every run and the rules 0/4. The rules read no notes by design, so this measures what structured-data checks miss, not a head-to-head on reading text. On structured cases both were perfect.
2. **With the same model, the fixed workflow was far more reliable than the free agent.** Same model, same definitions: the workflow scored 10/10 with one call per PO; the agent scored 5.7/10, skipped POs and flagged normal POs as problems. The agent also had to gather each PO's records itself, so part of the gap may come from incomplete inputs rather than from the freedom to plan (see next steps).
3. **An outcome-only check taught the agent to fake the outcome.** The agent's submit tool rejected findings that did not add up to its own October total. In two test runs the agent passed by inventing balancing figures, once citing a PO line that does not exist. A check that every cited record exists, and that every PO with a difference is covered, would have caught both. The traces are in `results/test_llm_raw_v8/`.

Also from development: the same model made arithmetic errors in 18 of 18 agent submissions, but got 30 of 30 PO totals right when the workflow made it write each step in a worksheet.

## Data

A synthetic Odoo-style dataset of 10 tables: vendors, products, agreed vendor prices, purchase orders, PO lines, receipts and returns (pickings), stock moves, vendor bills, bill lines and chatter notes. Records link the way Odoo links them. Both sets reconcile October 2026 as at 10 November 2026.

| Set | File | POs | Purpose |
| --- | --- | --- | --- |
| Development | `data/odoo_p2p_10po.zip` | 10 | tuning prompts and architectures |
| Test (held out) | `data/odoo_p2p_test.zip` | 10 | the reported results; new vendors and products, PO numbers shuffled |

Answer keys are in `answer_key/`, outside the data files the systems read.

Cause categories: `timing`, `po_price_error`, `vendor_overbilled`, `vendor_underbilled`, `approved_price_change`, `unrecorded_return`, `cut_off_error`, `insufficient_evidence`. Normal POs should get no finding. Definitions are in `llm.py` (`CATEGORY_TEXT`).

## Evaluation

- **Cause correct**: a finding on the PO has the expected category.
- **Cause and location correct**: that finding also points at the right record (PO line, receipt or bill line).
- **Extra findings**: findings on records that are not the problem, repeated findings on the problem record (one problem = one finding) and findings on POs that do not exist; on a normal PO any finding counts.
- Prompts and logic were tuned only on the development set, then frozen with file fingerprints before the test set was built.
- Each LLM design ran 3 times; a run that ends without accepted findings counts as all 10 POs wrong, including the normal POs.

The full history of versions, errors and decisions is in `experiment_log.md`.

## Repository layout

```
make_data.py, make_test_data.py   generate the development and test data and their answer keys
rules_baseline.py                 Python rules
llm.py                            fixed LLM workflow (also holds the shared category definitions)
agent.py                          tool-using LLM agent
evaluate.py                       scoring for all three
experiment_log.md                 iteration log, decisions and final results
data/                             development and test data (zipped Odoo-style tables)
answer_key/                       expected findings for both sets, kept apart from the data
results/                          test-set outputs of the frozen versions
  test_rules_findings.csv
  test_llm_findings_v6_run1-3.csv, test_llm_worksheet_v6_run1-3.csv
  test_agent_findings_v8_run1-3.csv
  test_llm_raw_v8/                full agent traces for the three test runs
```

## How to run

Requires Python 3.10+ and an OpenAI API key (rules and scoring need neither).

```
pip install -r requirements.txt
export OPENAI_API_KEY="sk-..."        # Windows: setx OPENAI_API_KEY "sk-..."

python rules_baseline.py --test
python llm.py --test --runs 3
python agent.py --test --runs 3

python evaluate.py --test results/test_rules_findings.csv
python evaluate.py --test --runs results/test_llm_findings_v6
python evaluate.py --test --runs results/test_agent_findings_v8
```

Without `--test`, the scripts use the development set. All outputs go to `results/`. New runs are numbered after the existing ones, so the included results are never overwritten. Scripts can be run from any folder.

## Limitations and next steps

What the results do not show:

- **Small, self-designed test set.** 10 POs, one case per cause, designed by the same people after seeing development results. Some workflow rules were added after development errors and cover the same patterns as test cases. The 10/10 shows reliability on these patterns, not a general accuracy figure.
- **Notes are explicit.** Test notes state the cause plainly (e.g. "confirmed ahead of time to make the month-end"). Real warehouse and AP notes are shorter and vaguer.
- **Scoring checks the category and the record, not the amounts or the recommended action.** The agent's invented balancing figures were found by reading the traces, not by the score.
- **One small model, synthetic data, one PO at a time.** Problems that span POs (a bill posted to the wrong PO) are out of scope. Cost and latency were not measured beyond the number of model calls.

Next steps, in order:

1. **LLM reads the notes, rules decide.** The LLM turns each note into fixed fields (event, quantity, date, record), and Python rules do the arithmetic and the classification. If this matches the workflow, the LLM's value lies in reading text, and the judgement can stay in auditable code.
2. **A new held-out set** with vague notes, POs with more than one cause, and situations outside the category list, frozen before any run.
3. **Score the amounts and the evidence**: each finding's explained difference, and whether every cited record exists.
4. **Give the agent the workflow's case files**, to separate the effect of incomplete inputs from the effect of free planning.
