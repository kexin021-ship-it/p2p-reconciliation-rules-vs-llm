"""Free-form LLM agent for October month-end P2P reconciliation (OpenAI API, tool calling).

Unlike llm.py (fixed workflow: code hands the LLM one PO's records at a time and the prompt
prescribes the worksheet steps), here the LLM gets only the task and four tools. It decides by itself which tables to
read, which POs to look at, which records to follow, and when it is done.

Usage (in the project folder's terminal):
  python agent.py                  # one run  -> agent_findings_v8_run<N>.csv
  python agent.py --runs 2         # two runs in a row (run numbers continue from what already exists)
  python agent.py --test --runs 3  # held-out test set -> test_agent_findings_v8_run<N>.csv (prompt unchanged)
  python evaluate.py --runs agent_findings_v8          # summary across all runs
  python evaluate.py agent_findings_v8_run1.csv        # one run in detail
Every tool call the agent makes is saved to llm_raw_v8/agent_trace_run<N>.json.

v2 changes (2026-11-12, decided on the 10-PO dev set):
  1. explanation is written BEFORE cause_category / problem_key
  2. new tool get_po_records: returns all records linked to one PO, unprocessed
     (no totals, no comparisons) - the agent decides when to use it and does the maths itself
  3. one difference = one finding, on the record that caused it (shared rule text)
  4. every cause must cite a supporting record, otherwise insufficient_evidence (shared rule text)

v4 (2026-11-12): new shared category definitions + decision rules from llm.py (no v3 for the agent;
the workflow's v3 change was its worksheet only). Version numbers aligned so v4 = same definitions.

v5 (2026-11-12, agent only; workflow stays v4): deliverable standard "the difference must reconcile".
  v4 omitted the pure-timing POs (P00001, P00002) in 3/3 runs. Now: every PO with an October difference
  needs a finding (timing included); each finding states the amount of the difference it explains; before
  submitting, the agent checks these add up to total October bills minus total October receipts.

v6 (2026-11-12, agent only): v5 agents never ran the check (totals 700 / -5,600 / -100 vs 900) and submitted anyway.
  Now the check is enforced, but the agent still computes every figure itself:
  (1) the agent must compute and submit total October bills, total October receipts and the difference;
  (2) submit_findings acts as a grader that says WHAT is wrong but never gives the correct figure:
      - "your October bill (or receipt) total is wrong, recompute it"
      - "your findings add up to X, your own total difference is Y, gap Y-X" (both the agent's own numbers)
  (3) at most MAX_BOUNCES (5) rejections; after that the last submission is accepted and logged as not reconciled.

v7 (2026-11-12): only the shared category list changed (new vendor_underbilled, from llm.py v5).
  Same review (before any v7 run): shared month-end cut-off rules (from llm.py) and the same sampling settings
  as the workflow: reasoning_effort="none", temperature=0.
  Also new tool `calculate` (user's choice): the agent decides which figures to use and how to combine them;
  the tool only does the arithmetic (+ - * / and brackets). Reason: in agent v6 its own October totals were
  wrong in 18/18 submissions, and every rejection costs another model call.

v8 (2026-11-13): only the shared definition text changed (llm.py v6: underbilled vs unrecorded_return;
  "Month-end position" section name; arrived-in-October-recorded-later -> cut_off_error rule).

Needs:  pip install openai   and the OPENAI_API_KEY environment variable.
"""
import ast, csv, json, operator, os, sys

# Always work inside this script's own folder, wherever it is run from
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Same data, model, period and category definitions as the fixed workflow
from llm import (load, build_cases, CATEGORIES, CATEGORY_TEXT, MODEL, REASONING_EFFORT, TEMPERATURE,
                 DATA_ZIP, TEST_DATA_ZIP, PERIOD, RUN_DATE,
                 runs_requested, next_run_number, write_findings)

RAW_DIR = "llm_raw_v8"   # agent v8 = v7 (calculator, cut-off, temperature 0) + llm.py v6 definition fixes

OUT_PREFIX = "agent_findings_v8"   # + _run<N>.csv
MAX_BOUNCES = 5      # submit_findings rejects a non-reconciling submission at most this many times
MAX_STEPS = 60          # safety stop: max number of model turns
MAX_ROWS = 200          # max rows returned by one query

SYSTEM_PROMPT = f"""You are an accounts payable analyst doing the {PERIOD} month-end reconciliation
in an Odoo database. Today is {RUN_DATE}.

Goal: the {PERIOD} receipt value (stock moves done in {PERIOD}) does not equal the {PERIOD}
vendor bill value (bills with invoice_date in {PERIOD}). Find every record that explains
the difference, or that is otherwise wrong, across ALL purchase orders, and say why.

You can only see the data through the tools. Investigate however you think best, then call
submit_findings exactly once with all your findings. Nothing else you write is kept.

How Odoo records link together:
- purchase_order_line.order_id -> purchase_order.id
- stock_move.purchase_line_id -> purchase_order_line.id ; stock_move.picking_id -> stock_picking.id
- stock_picking.origin holds the PO name; a return has return_of_picking_id set
- account_move_line.move_id -> account_move.id (the bill) ; account_move_line.purchase_line_id -> purchase_order_line.id
- account_move.invoice_origin holds the PO name
- product_supplierinfo holds agreed vendor prices (partner_id + product_id)
- mail_message holds chatter notes; a note belongs to the record identified by model + res_id
  (model purchase.order / stock.picking / account.move, res_id = that table's id)

Each finding needs the PO name in "po".

Deliverable standard - the difference must reconcile:
- Every PO with a non-zero {PERIOD} difference ({PERIOD} bill value minus {PERIOD} receipt value)
  needs at least one finding, including pure timing differences.
- Give each finding explained_difference: the part of the {PERIOD} difference (bill minus receipt)
  it explains; negative when receipts exceed bills; 0 if it explains none.
- Work out yourself the total {PERIOD} bill value and the total {PERIOD} receipt value across all
  POs, and the total difference (bills minus receipts). Submit these three figures with your findings.
- Use the calculate tool for every sum, difference or product - never do arithmetic in your head.
- Your explained_difference values must add up to your total difference.
- submit_findings checks your totals and whether your findings add up. If anything is off, the
  submission is rejected and you are told what is wrong (not the correct figures): recompute,
  investigate further, and submit the COMPLETE corrected list again.

""" + CATEGORY_TEXT

TOOLS = [
    {"type": "function", "function": {
        "name": "list_tables",
        "description": "List all tables with their column names and row counts.",
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        "strict": True}},
    {"type": "function", "function": {
        "name": "query_table",
        "description": "Return rows of one table that match ALL filters (empty filters = all rows). "
                       "op 'eq' = exact match, 'contains' = substring, 'startswith' = prefix (e.g. a month '2026-10').",
        "parameters": {"type": "object", "properties": {
            "table": {"type": "string"},
            "filters": {"type": "array", "items": {"type": "object", "properties": {
                "column": {"type": "string"},
                "op": {"type": "string", "enum": ["eq", "contains", "startswith"]},
                "value": {"type": "string"}},
                "required": ["column", "op", "value"], "additionalProperties": False}}},
            "required": ["table", "filters"], "additionalProperties": False},
        "strict": True}},
    {"type": "function", "function": {
        "name": "get_po_records",
        "description": "Return every record linked to one purchase order, exactly as stored: the PO, "
                       "its lines with agreed vendor prices, all receipts and returns with their stock moves, "
                       "all vendor bills with their lines, and the chatter notes on each of those records. "
                       "Nothing is added up or compared for you.",
        "parameters": {"type": "object", "properties": {"po": {"type": "string", "description": "PO name, e.g. P00001"}},
                       "required": ["po"], "additionalProperties": False},
        "strict": True}},
    {"type": "function", "function": {
        "name": "calculate",
        "description": "Evaluate an arithmetic expression and return the exact result. "
                       "Supports numbers, + - * / and brackets, e.g. '3000 + 1700 - 250' or '(33 - 30) * 30'.",
        "parameters": {"type": "object", "properties": {"expression": {"type": "string"}},
                       "required": ["expression"], "additionalProperties": False},
        "strict": True}},
    {"type": "function", "function": {
        "name": "submit_findings",
        "description": "Submit the final list of findings. Call once, at the end.",
        "parameters": {"type": "object", "properties": {"findings": {"type": "array", "items": {
            "type": "object", "properties": {
                "po": {"type": "string"},
                "explanation": {"type": "string"},
                "cause_category": {"type": "string", "enum": CATEGORIES},
                "problem_key": {"type": "string"},
                "explained_difference": {"type": "number"},
                "action": {"type": "string"}},
            "required": ["po", "explanation", "cause_category", "problem_key", "explained_difference", "action"],
            "additionalProperties": False}},
            "period_bill_total": {"type": "number"},
            "period_receipt_total": {"type": "number"},
            "period_difference": {"type": "number"}},
            "required": ["findings", "period_bill_total", "period_receipt_total", "period_difference"],
            "additionalProperties": False},
        "strict": True}},
]


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.USub: operator.neg, ast.UAdd: operator.pos}


def calculate(expression):
    """Safe arithmetic: numbers, + - * / and brackets only (no names, no function calls)."""
    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ValueError("only numbers, + - * / and brackets are allowed")
    try:
        result = ev(ast.parse(expression.replace(",", ""), mode="eval"))
        return {"expression": expression, "result": round(result, 6)}
    except Exception as e:
        return {"expression": expression, "error": str(e)}


def run_tool(tables, cases, name, args):
    if name == "calculate":
        return calculate(args["expression"])
    if name == "get_po_records":
        if args["po"] not in cases:
            return {"error": f"unknown PO {args['po']}", "known_pos": list(cases)}
        return cases[args["po"]]
    if name == "list_tables":
        return {t: {"columns": list(rows[0].keys()) if rows else [], "rows": len(rows)}
                for t, rows in tables.items()}
    if name == "query_table":
        if args["table"] not in tables:
            return {"error": f"unknown table {args['table']}", "tables": list(tables)}
        rows = tables[args["table"]]
        for f in args["filters"]:
            col, op, val = f["column"], f["op"], f["value"]
            if rows and col not in rows[0]:
                return {"error": f"unknown column {col}", "columns": list(rows[0])}
            if op == "eq":
                rows = [r for r in rows if r[col] == val]
            elif op == "contains":
                rows = [r for r in rows if val.lower() in r[col].lower()]
            else:
                rows = [r for r in rows if r[col].startswith(val)]
        return {"row_count": len(rows), "rows": rows[:MAX_ROWS]}
    return {"error": f"unknown tool {name}"}


def grade_submission(args, actual):
    """The grader: says what is wrong, never the correct figure. Returns (tool result, accepted?)."""
    problems = []
    if abs(args["period_bill_total"] - actual["bills"]) > 0.01:
        problems.append(f"Your {PERIOD} bill total ({args['period_bill_total']:g}) is wrong - recompute it.")
    if abs(args["period_receipt_total"] - actual["receipts"]) > 0.01:
        problems.append(f"Your {PERIOD} receipt total ({args['period_receipt_total']:g}) is wrong - recompute it.")
    if abs(args["period_difference"] - (args["period_bill_total"] - args["period_receipt_total"])) > 0.01:
        problems.append(f"Your total difference ({args['period_difference']:g}) is not your bill total minus "
                        f"your receipt total ({args['period_bill_total'] - args['period_receipt_total']:g}).")
    found = sum(fd["explained_difference"] for fd in args["findings"])
    if abs(found - args["period_difference"]) > 0.01:
        problems.append(f"Your findings' explained_difference adds up to {found:g}, but your total difference is "
                        f"{args['period_difference']:g} (gap {args['period_difference'] - found:g}). A PO may be "
                        f"missing, or a figure or sign (bill minus receipt) is wrong.")
    if problems:
        return {"status": "rejected", "problems": problems,
                "next": "Investigate further, then call submit_findings again with the COMPLETE list."}, False
    return {"status": "accepted - totals correct and findings reconcile"}, True


def run_agent(client, tables, cases, run, actual):
    """One full agent run. Returns the submitted findings (or None)."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Please do the {PERIOD} reconciliation."}]
    trace, findings, bounces, reconciled = [], None, 0, False
    submissions = []   # agent's own totals at each submission, for the report
    for step in range(1, MAX_STEPS + 1):
        resp = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS,
                                              reasoning_effort=REASONING_EFFORT, temperature=TEMPERATURE)
        msg = resp.choices[0].message
        calls = msg.tool_calls or []
        messages.append({"role": "assistant", "content": msg.content,
                         **({"tool_calls": [{"id": c.id, "type": "function",
                                             "function": {"name": c.function.name,
                                                          "arguments": c.function.arguments}}
                                            for c in calls]} if calls else {})})
        if not calls:   # model replied in text instead of using a tool: nudge it
            trace.append({"step": step, "text": msg.content})
            messages.append({"role": "user", "content": "Please continue using the tools, "
                             "and finish by calling submit_findings."})
            continue
        for c in calls:
            args = json.loads(c.function.arguments or "{}")
            if c.function.name == "submit_findings":
                result, ok = grade_submission(args, actual)
                submissions.append({"bill_total": args["period_bill_total"], "receipt_total": args["period_receipt_total"],
                                    "difference": args["period_difference"],
                                    "findings_sum": sum(fd["explained_difference"] for fd in args["findings"]),
                                    "accepted": ok})
                if ok:
                    findings, reconciled = args["findings"], True
                elif bounces < MAX_BOUNCES:
                    bounces += 1
                else:
                    findings = args["findings"]
                    result = {"status": "accepted without reconciling (rejection limit reached)"}
            else:
                result = run_tool(tables, cases, c.function.name, args)
            trace.append({"step": step, "tool": c.function.name, "args": args,
                          "result_rows": result.get("row_count") if isinstance(result, dict) else None})
            messages.append({"role": "tool", "tool_call_id": c.id, "content": json.dumps(result)})
            print(f"step {step:2}: {c.function.name} {json.dumps(args)[:100]}")
            if c.function.name == "submit_findings":
                print(f"         -> {result['status']}")
            elif c.function.name == "calculate":
                print(f"         -> {result.get('result', result.get('error'))}")
        if findings is not None:
            break

    with open(f"{RAW_DIR}/agent_trace_run{run}.json", "w", encoding="utf-8") as f:
        json.dump({"model": MODEL, "run": run, "steps": step, "bounces": bounces, "reconciled": reconciled,
                   "submissions": submissions, "trace": trace, "messages": messages}, f, indent=2, default=str)
    return findings, step, bounces, reconciled, submissions


def main():
    global OUT_PREFIX, RAW_DIR
    data_zip = DATA_ZIP
    if "--test" in sys.argv[1:]:   # same prompt, tools and grader; only the input data and output names change
        data_zip, OUT_PREFIX, RAW_DIR = TEST_DATA_ZIP, "test_" + OUT_PREFIX, "test_" + RAW_DIR
    from openai import OpenAI
    client = OpenAI()   # reads OPENAI_API_KEY
    tables = load(data_zip)
    cases = build_cases(tables)   # same per-PO record bundle the fixed workflow uses
    # true October totals - used only by the grader in submit_findings, never shown to the agent
    actual = {"bills": sum(float(b["amount_untaxed"]) for b in tables["account_move"] if b["invoice_date"].startswith(PERIOD)),
              "receipts": sum(float(m["value"]) for m in tables["stock_move"] if m["date"].startswith(PERIOD))}
    actual["difference"] = actual["bills"] - actual["receipts"]
    os.makedirs(RAW_DIR, exist_ok=True)

    n_runs = runs_requested(sys.argv[1:])
    first = next_run_number(OUT_PREFIX)
    for run in range(first, first + n_runs):
        print(f"=== run {run} (model: {MODEL})")
        findings, steps, bounces, reconciled, subs = run_agent(client, tables, cases, run, actual)
        if findings is None:
            # failed run: write an empty findings file so it is scored as all-wrong (agreed 2026-11-13)
            # and so the next run does not reuse this run number
            write_findings(f"{OUT_PREFIX}_run{run}.csv", [])
            print(f"Run {run}: agent did not submit findings within {MAX_STEPS} steps -> scored as a failed run "
                  f"(empty {OUT_PREFIX}_run{run}.csv). See {RAW_DIR}/agent_trace_run{run}.json\n")
            continue
        out = f"{OUT_PREFIX}_run{run}.csv"
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["po", "problem_key", "cause_category", "explanation", "action", "explained_difference"])
            w.writerows([fd["po"], fd["problem_key"], fd["cause_category"], fd["explanation"], fd["action"],
                         fd["explained_difference"]] for fd in findings)
        print(f"{len(findings)} findings written to {out} ({steps} steps)")
        mark = lambda a, b: "ok" if abs(a - b) < 0.01 else "WRONG"
        for k, sub in enumerate(subs, 1):
            print(f"  submission {k}: bills {sub['bill_total']:g} ({mark(sub['bill_total'], actual['bills'])}), "
                  f"receipts {sub['receipt_total']:g} ({mark(sub['receipt_total'], actual['receipts'])}), "
                  f"difference {sub['difference']:g}, findings add up to {sub['findings_sum']:g}"
                  f"{'  -> accepted' if sub['accepted'] else ''}")
        print(f"Rejected {bounces}x, {'reconciled' if reconciled else 'NOT reconciled'} "
              f"(true: bills {actual['bills']:g}, receipts {actual['receipts']:g}, difference {actual['difference']:g})\n")
    print(f"Summary across runs:  python evaluate.py --runs {OUT_PREFIX}")

if __name__ == "__main__":
    main()
