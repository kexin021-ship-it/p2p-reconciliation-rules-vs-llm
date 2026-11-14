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
| Extra findings per run | 1.0 | **0.0** | 4.7 |
| Model calls per run | 0 | 10 | 13 to 60 |

By where the evidence sits (share of correct judgements, LLM runs pooled):

| Evidence | Python rules | Fixed LLM workflow | Tool-using LLM agent |
| --- | --- | --- | --- |
| Cause visible in structured data (4 POs) | 100% | 100% | 92% |
| Cause written only in a note (4 POs) | 0% | 100% | 42% |
| Nothing to report (2 POs) | 100% | 100% | 17% |

## Key findings

1. **The LLM adds value exactly where the evidence is free text.** On cases whose cause is stated only in a chatter note (goods taken back by the driver, an approved discount, a receipt booked before the goods arrived, contradicting records), rules scored 0/4 and the workflow 4/4 in every run. On structured cases both were perfect.
2. **Architecture, not the model, decided reliability.** Same model, same definitions: the workflow scored 10/10 with one call per PO; the agent scored 5.7/10, skipped POs and flagged normal POs as problems.
3. **An outcome-only check taught the agent to fake the outcome.** The agent's submit tool rejected findings that did not add up to its own October total. In two test runs the agent passed by inventing balancing figures, once citing a PO line that does not exist. The traces are in `test_llm_raw_v8/`.

Also from development: the same model made arithmetic errors in 18 of 18 agent submissions, but got 30 of 30 PO totals right when the workflow made it write each step in a worksheet.

## Data

A synthetic Odoo-style dataset of 10 tables: vendors, products, agreed vendor prices, purchase orders, PO lines, receipts and returns (pickings), stock moves, vendor bills, bill lines and chatter notes. Records link the way Odoo links them. Both sets reconcile October 2026 as at 10 November 2026.

| Set | File | POs | Purpose |
| --- | --- | --- | --- |
| Development | `odoo_p2p_10po.zip` | 10 | tuning prompts and architectures |
| Test (held out) | `odoo_p2p_test.zip` | 10 | the reported results; new vendors and products, PO numbers shuffled |

Answer keys are in `answer_key/`, outside the data files the systems read.

Cause categories: `timing`, `po_price_error`, `vendor_overbilled`, `vendor_underbilled`, `approved_price_change`, `unrecorded_return`, `cut_off_error`, `insufficient_evidence`. Normal POs should get no finding. Definitions are in `llm.py` (`CATEGORY_TEXT`).

## Evaluation

- **Cause correct**: a finding on the PO has the expected category.
- **Cause and location correct**: that finding also points at the right record (PO line, receipt or bill line).
- **Extra findings**: findings on records that are not the problem; on a normal PO any finding counts.
- Prompts and logic were tuned only on the development set, then frozen with file fingerprints before the test set was built.
- Each LLM design ran 3 times; a run that ends without accepted findings counts as all 10 POs wrong.

The full history of versions, errors and decisions is in `experiment_log.md`.

## Repository layout

| File | What it is |
| --- | --- |
| `make_data.py`, `make_test_data.py` | generate the development and test data and their answer keys |
| `rules_baseline.py` | Python rules |
| `llm.py` | fixed LLM workflow (also holds the shared category definitions) |
| `agent.py` | tool-using LLM agent |
| `evaluate.py` | scoring for all three |
| `answer_key/` | expected findings for both sets |
| `test_*_findings_*.csv`, `test_llm_worksheet_v6_run*.csv` | test-set outputs of the frozen versions |
| `test_llm_raw_v8/` | full agent traces for the three test runs |
| `experiment_log.md` | iteration log and final results |

## How to run

Requires Python 3.10+ and an OpenAI API key (rules and scoring need neither).

```
pip install openai
export OPENAI_API_KEY="sk-..."        # Windows: setx OPENAI_API_KEY "sk-..."

python rules_baseline.py --test
python llm.py --test --runs 3
python agent.py --test --runs 3

python evaluate.py --test test_rules_findings.csv
python evaluate.py --test --runs test_llm_findings_v6
python evaluate.py --test --runs test_agent_findings_v8
```

Without `--test`, the scripts use the development set. New runs are numbered after the existing ones, so the included results are never overwritten. Scripts can be run from any folder.

## Limitations

- The test set has 10 POs and was designed by the same people who saw the development results; the workflow's 10/10 shows reliability on these patterns, not a general accuracy figure.
- The workflow reviews one PO at a time, so problems that span POs (a bill posted to the wrong PO) are out of scope.
- One model only (gpt-5.4-mini) and synthetic data; real ERP exports carry more noise.
