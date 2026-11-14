"""LLM workflow for October month-end P2P reconciliation (OpenAI API).

Fixed workflow, one PO at a time:
  1. Code collects everything linked to the PO (lines, agreed prices, receipts/returns,
     bills, and the chatter notes attached to any of those records) into a "case file".
  2. The LLM reads the case file and returns findings in the SAME format as the rules,
     so both can be scored with evaluate.py.

Usage (in the project folder's terminal):
  python llm.py --list-models     # show the model IDs your API key can use
  python llm.py --dry-run         # build case files only, no API call, no cost
  python llm.py                   # one run of all 10 POs  -> results/llm_findings_v6_run<N>.csv + results/llm_worksheet_v6_run<N>.csv
  python llm.py --runs 2          # two runs in a row (run numbers continue from what already exists)
  python llm.py --test --runs 3   # held-out test set -> results/test_llm_findings_v6_run<N>.csv (prompt unchanged)
  python evaluate.py --runs results/llm_findings_v6                       # summary across all runs
  python evaluate.py results/llm_findings_v6_run1.csv results/llm_worksheet_v6_run1.csv   # one run in detail, incl. arithmetic

v2 changes (2026-11-12, decided on the 10-PO dev set):
  1. explanation is written BEFORE cause_category / problem_key ("think, then answer")
  2. the model first builds a reconciliation worksheet itself (4 fixed steps, incl. PO line + PO links)
  3. one difference = one finding, on the record that caused it; no "checked, all fine" findings
  4. every cause must cite a supporting record, otherwise insufficient_evidence

v3 change (2026-11-12) - the ONLY difference from v2:
  worksheet gets two more steps: (e) list what each chatter note says actually happened and when;
  (f) compare each real event with the system records and write down any mismatch.
  Reason: v2 labelled P00005/P00009/P00010 "timing" in all 3 runs - notes were read only after the
  worksheet, so "different months" won over "what physically happened".

v4 changes (2026-11-12) - shared category definitions (also used by agent.py v4):
  - timing vs cut_off_error: timing only when all system records are correct; if what happened
    differs from what the system shows, it cannot be timing (workflow: tied to worksheet step f)
  - unrecorded_return vs vendor_overbilled: judged on NET received quantity (reversed returns count);
    billing for goods the system already shows as returned = vendor_overbilled
  - vendor_overbilled vs insufficient_evidence: billed qty/price above what we kept/agreed with no
    justifying record = vendor_overbilled; insufficient_evidence only when records contradict each other
  - evidence rule reworded: never use a reason no record supports (no longer routes to insufficient_evidence)
  - answer key: P00010 changed to vendor_overbilled (reflects AP practice)

v5 (2026-11-12): new shared category vendor_underbilled (bill below agreed price / fewer units with no
  "billed later" record, no justification); approved_price_change now explicitly covers approved discounts.
  Added together with the rules fix (bill price below PO price was mislabelled vendor_overbilled).
  Also (same review, before any v5 run): month-end cut-off written into the shared rules (only documents up
  to 2026-10-31 count; later documents are evidence only; qty_received/qty_invoiced are run-date figures);
  worksheet step c excludes post-cut-off documents; reasoning_effort="none" (the model default, now explicit)
  and temperature=0.

v6 (2026-11-13) - fixes two side effects seen in v5 (shared text, also used by agent.py v8):
  - vendor_underbilled: not when goods were physically returned / taken back (check unrecorded_return)
    (v5 run 3 labelled P00004 underbilled while writing that 2 units were taken back)
  - rules section renamed "Month-end cut-off" -> "Month-end position" (the word clashed with the category
    cut_off_error; v5 wrote "this is a month cut-off issue" and chose timing on P00009), plus decision rule:
    goods physically arrived in October but receipt recorded after month-end -> cut_off_error, not timing

Needs:  pip install openai   and the OPENAI_API_KEY environment variable.
"""
import csv, io, json, os, sys, zipfile
from collections import defaultdict

# Always work inside this script's own folder, wherever it is run from
os.chdir(os.path.dirname(os.path.abspath(__file__)))

MODEL = "gpt-5.4-mini"        # change to any ID shown by --list-models
REASONING_EFFORT = "none"     # gpt-5.4-mini default; temperature is only accepted with "none"
TEMPERATURE = 0               # as stable as possible (OpenAI does not guarantee identical outputs)
DATA_ZIP = "data/odoo_p2p_10po.zip"
TEST_DATA_ZIP = "data/odoo_p2p_test.zip"   # held-out test set: run with --test (outputs get a "test_" prefix)
PERIOD = "2026-10"
CUTOFF = "2026-10-31"         # month-end: only documents dated up to here count toward October figures
RUN_DATE = "2026-11-10"
OUT_PREFIX = "llm_findings_v6"          # + _run<N>.csv
WORKSHEET_PREFIX = "llm_worksheet_v6"    # + _run<N>.csv
RESULTS_DIR = "results"       # every output (findings, worksheets, raw replies) goes here
RAW_DIR = "llm_raw_v6"        # case files + raw model replies, for checking the reasoning

CATEGORIES = ["timing", "po_price_error", "vendor_overbilled", "vendor_underbilled", "approved_price_change",
              "unrecorded_return", "cut_off_error", "insufficient_evidence"]

# Shared with agent.py so both LLM versions get identical definitions
CATEGORY_TEXT = f"""Cause categories (use exactly one per finding):
- timing: all system records are correct; the receipt and the bill simply belong to different
  months (e.g. goods received in September, billed in October), or the remaining quantity
  will be billed later. Nothing is wrong.
- po_price_error: the PO unit price was entered wrongly (differs from the agreed price);
  the vendor billed correctly.
- vendor_overbilled: the vendor billed more than it should - a unit price above the agreed or
  approved price, or a quantity above what the system shows we kept (net of returns),
  including goods the system already shows as returned - and no record shows this is
  justified (e.g. an approved price change, or a note that the rest will be delivered later).
  Money should be recovered.
- vendor_underbilled: the vendor billed less than it should - a unit price below the agreed
  price (the PO price itself being correct), or a quantity below what we kept with no record
  saying the rest will be billed later - and no record shows this is justified (e.g. an
  approved discount). Confirm with the vendor; a supplementary bill may follow.
  Not this category when goods were physically returned or taken back - check unrecorded_return.
- approved_price_change: the bill price differs from the PO, but the change (increase or
  discount) was approved internally; only the PO needs updating.
- unrecorded_return: goods physically went back to the vendor, but the system's net received
  quantity (receipts minus returns, counting any reversed returns) does not reflect it,
  fully or partly.
- cut_off_error: something physically happened in one month (e.g. goods arrived) but the
  system recorded it in another month. This applies even when it looks like a timing difference.
- insufficient_evidence: only when the records contradict each other and you cannot tell
  which one to trust (e.g. a note says 40 boxes arrived, the system shows 36, the bill says 40).

Decision rules:
- If what actually happened (according to the notes) differs from what the system shows,
  the cause cannot be timing.
- If the notes show goods physically arrived in {PERIOD} but the system recorded the receipt
  after {CUTOFF}, the cause is cut_off_error, not timing.
- Before choosing unrecorded_return, compare the quantity that physically went back with the
  quantity the system's net received quantity already deducts. If the system already deducts
  all of it, it is not unrecorded_return.

Month-end position:
- Everything is judged as at {CUTOFF}. Only documents dated up to {CUTOFF} count toward the
  {PERIOD} figures - values, quantities received, quantities billed and prices.
- Documents dated after {CUTOFF} are later evidence only (e.g. a November bill shows an October
  receipt was simply billed later; a November return does not change what was received by
  {CUTOFF}). They never change the {PERIOD} figures.
- The PO line fields qty_received and qty_invoiced are as at today ({RUN_DATE}) and include
  documents after {CUTOFF}; do not use them for the month-end position.

Rules:
- Base every conclusion on the records given. Chatter notes are evidence, but some notes
  are routine and say nothing useful.
- Point at the most specific record at fault, as problem_key "<table>:<id>":
  purchase.order.line:<id> for a wrong PO line, stock.picking:<id> for a receipt or
  return, account.move.line:<id> for a bill line.
- One difference = one finding, reported on the record that caused it. Before adding a
  finding, ask: does this record cause part of the {PERIOD} difference, or does someone need
  to act on it? If neither, leave it out. (A timing difference still gets a finding; its
  action is simply that no correction is needed.)
- Evidence: every cause must rest on a specific record. Name the chatter note (author and
  date) or the document and field (name, date, quantity, price) that shows it. Never use a
  reason that no record supports (e.g. "the rest will be delivered later" when no note says so).
- Write each finding in this order: explanation first (the facts and your reasoning,
  1-4 sentences), then cause_category and problem_key, then action (what the AP team
  should do next)."""

SYSTEM_PROMPT = f"""You are an accounts payable analyst doing the {PERIOD} month-end reconciliation
in Odoo. Today is {RUN_DATE}. For ONE purchase order you receive every linked record:
PO lines, agreed vendor prices, receipts and returns (stock moves), vendor bill lines,
and the chatter notes written on any of those records.

Task: find every record that explains a difference between the {PERIOD} receipt value
and the {PERIOD} bill value, or that is otherwise wrong, and say why.

Work in this order:
1. Worksheet: do the reconciliation yourself, for every PO line.
   a. List every receipt and return move: picking, month, quantity, value, its PO line, its PO.
   b. List every bill line: bill, month, quantity, unit price, amount, its PO line, its PO.
   c. For each PO line, add up the {PERIOD} receipt value and the {PERIOD} bill value and
      work out the difference (bill minus receipt). Then total these for the whole PO.
      Documents dated after {CUTOFF} stay listed in a and b, but are not counted here.
   d. Compare three prices: the PO unit price, the agreed vendor price, and the unit price
      on each bill line.
   e. List every chatter note: what it says actually happened (goods arrived, returned, taken
      back, damaged, a price agreed or rejected, billing promised, ...) and when it happened.
      Mark notes with no real content as routine.
   f. For each real event, compare it with the system records: is it recorded in the system?
      Do the record's date and quantity match what actually happened? Does the bill reflect it?
      Write down every mismatch between what happened and what the system shows.
2. Findings: based on the worksheet and the notes, following the rules below. Every record
   is already listed in the worksheet, so do not add findings just to show a record was checked.
   If step f found a mismatch between what happened and what the system shows, the cause
   cannot be timing.

""" + CATEGORY_TEXT

def obj(props):
    """Strict JSON-schema object: every field required, no extras, field order kept."""
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}

NUM, STR = {"type": "number"}, {"type": "string"}

# Field order matters: the model writes fields in this order (worksheet -> explanation -> label)
FINDING = obj({
    "explanation": STR,
    "cause_category": {"type": "string", "enum": CATEGORIES},
    "problem_key": STR,
    "action": STR,
})

WORKSHEET = obj({
    "lines": {"type": "array", "items": obj({
        "po_line_id": STR,
        "product": STR,
        "receipts_and_returns": {"type": "array", "items": obj({
            "picking": STR, "month": STR, "quantity": NUM, "value": NUM, "po_line_id": STR, "po": STR})},
        "bill_lines": {"type": "array", "items": obj({
            "bill": STR, "account_move_line_id": STR, "month": STR, "quantity": NUM,
            "unit_price": NUM, "amount": NUM, "po_line_id": STR, "po": STR})},
        "period_receipt_value": NUM,
        "period_bill_value": NUM,
        "difference_bill_minus_receipt": NUM,
        "po_unit_price": NUM,
        "agreed_price": {"type": ["number", "null"]},
        "bill_unit_prices": {"type": "array", "items": NUM},
    })},
    "po_period_receipt_value": NUM,
    "po_period_bill_value": NUM,
    "po_difference_bill_minus_receipt": NUM,
    # steps e + f (v3): what actually happened vs what the system shows
    "note_events": {"type": "array", "items": obj({
        "note_on": STR,                 # record the note is attached to, e.g. WH/IN/00011
        "note_date": STR,
        "author": STR,
        "routine": {"type": "boolean"},
        "what_happened": STR,
        "when_it_happened": STR,
        "system_record": STR,           # record showing this event in the system, or "none"
        "system_record_date": STR,
        "matches_system": {"type": "boolean"},
        "mismatch": STR,                # "" if none
    })},
})

SCHEMA = obj({"worksheet": WORKSHEET, "findings": {"type": "array", "items": FINDING}})


def load(zip_path):
    tables = {}
    with zipfile.ZipFile(zip_path) as z:
        for n in z.namelist():
            if n.endswith(".csv"):
                tables[n.split("/")[-1][:-4]] = list(
                    csv.DictReader(io.TextIOWrapper(z.open(n), encoding="utf-8")))
    return tables


def build_cases(t):
    """Step 1 (code, not LLM): gather every record linked to each PO."""
    partner = {r["id"]: r["name"] for r in t["res_partner"]}
    product = {r["id"]: r for r in t["product_product"]}
    picking = {r["id"]: r for r in t["stock_picking"]}
    bill = {r["id"]: r for r in t["account_move"]}
    agreed = {(r["partner_id"], r["product_id"]): r for r in t["product_supplierinfo"]}
    notes = defaultdict(list)
    for m in t["mail_message"]:
        notes[(m["model"], m["res_id"])].append(m)

    cases = {}
    for po in t["purchase_order"]:
        lines = [l for l in t["purchase_order_line"] if l["order_id"] == po["id"]]
        line_ids = {l["id"] for l in lines}
        moves = [m for m in t["stock_move"] if m["purchase_line_id"] in line_ids]
        blines = [b for b in t["account_move_line"] if b["purchase_line_id"] in line_ids]
        pick_ids = sorted({m["picking_id"] for m in moves}, key=int)
        bill_ids = sorted({b["move_id"] for b in blines}, key=int)

        def notes_for(model, rid):
            return [{"date": n["date"], "author": n["author"], "body": n["body"]}
                    for n in notes[(model, rid)]]

        cases[po["name"]] = {
            "purchase_order": {"id": po["id"], "name": po["name"], "vendor": partner[po["partner_id"]],
                               "date_order": po["date_order"], "amount_untaxed": po["amount_untaxed"],
                               "notes": notes_for("purchase.order", po["id"])},
            "purchase_order_lines": [{
                "id": l["id"], "product": l["name"], "product_code": product[l["product_id"]]["default_code"],
                "ordered_qty": l["product_qty"], "po_unit_price": l["price_unit"],
                "agreed_vendor_price": (agreed.get((po["partner_id"], l["product_id"])) or {}).get("price"),
                "qty_received": l["qty_received"], "qty_invoiced": l["qty_invoiced"]} for l in lines],
            "receipts_and_returns": [{
                "picking_id": pid, "name": picking[pid]["name"], "type": picking[pid]["picking_type"],
                "origin": picking[pid]["origin"], "date_done": picking[pid]["date_done"],
                "moves": [{"stock_move_id": m["id"], "purchase_line_id": m["purchase_line_id"],
                           "quantity": m["quantity"], "unit_price": m["price_unit"], "value": m["value"]}
                          for m in moves if m["picking_id"] == pid],
                "notes": notes_for("stock.picking", pid)} for pid in pick_ids],
            "vendor_bills": [{
                "bill_id": bid, "name": bill[bid]["name"], "vendor_ref": bill[bid]["ref"],
                "invoice_date": bill[bid]["invoice_date"], "amount_untaxed": bill[bid]["amount_untaxed"],
                "lines": [{"account_move_line_id": b["id"], "purchase_line_id": b["purchase_line_id"],
                           "product": b["name"], "quantity": b["quantity"], "unit_price": b["price_unit"],
                           "subtotal": b["price_subtotal"]} for b in blines if b["move_id"] == bid],
                "notes": notes_for("account.move", bid)} for bid in bill_ids],
        }
    return cases


# ---- helpers shared with agent.py: repeated runs ----
def runs_requested(args):
    """'--runs 3' -> 3; default 1."""
    if "--runs" in args:
        return int(args[args.index("--runs") + 1])
    return 1


def next_run_number(prefix):
    """Next free run number, so new runs never overwrite earlier ones."""
    folder, name = os.path.split(prefix)
    folder = folder or "."
    files = os.listdir(folder) if os.path.isdir(folder) else []
    done = [int(f[len(name) + 4:-4]) for f in files
            if f.startswith(name + "_run") and f.endswith(".csv") and f[len(name) + 4:-4].isdigit()]
    return max(done, default=0) + 1


def write_findings(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["po", "problem_key", "cause_category", "explanation", "action"])
        w.writerows(rows)


def ask_llm(client, case):
    """Step 2 (LLM): judge one PO."""
    resp = client.chat.completions.create(
        model=MODEL,
        reasoning_effort=REASONING_EFFORT,
        temperature=TEMPERATURE,
        messages=[{"role": "system", "content": SYSTEM_PROMPT},
                  {"role": "user", "content": json.dumps(case, indent=2)}],
        response_format={"type": "json_schema",
                         "json_schema": {"name": "findings", "strict": True, "schema": SCHEMA}},
    )
    return resp.choices[0].message.content


def main():
    global DATA_ZIP, OUT_PREFIX, WORKSHEET_PREFIX, RAW_DIR
    args = sys.argv[1:]
    if "--test" in args:   # same prompt and logic; only the input data and output names change
        DATA_ZIP, OUT_PREFIX = TEST_DATA_ZIP, "test_" + OUT_PREFIX
        WORKSHEET_PREFIX, RAW_DIR = "test_" + WORKSHEET_PREFIX, "test_" + RAW_DIR
    OUT_PREFIX, WORKSHEET_PREFIX, RAW_DIR = (f"{RESULTS_DIR}/{p}" for p in (OUT_PREFIX, WORKSHEET_PREFIX, RAW_DIR))
    os.makedirs(RAW_DIR, exist_ok=True)
    cases = build_cases(load(DATA_ZIP))
    for po, case in cases.items():
        with open(f"{RAW_DIR}/{po}_case.json", "w", encoding="utf-8") as f:
            json.dump(case, f, indent=2)
    if "--dry-run" in args:
        print(f"{len(cases)} case files written to {RAW_DIR}/ (no API call made)")
        return

    from openai import OpenAI
    client = OpenAI()   # reads OPENAI_API_KEY
    if "--list-models" in args:
        for m in sorted(m.id for m in client.models.list()):
            print(m)
        return

    n_runs = runs_requested(args)
    first = next_run_number(OUT_PREFIX)
    for run in range(first, first + n_runs):
        print(f"=== run {run} (model: {MODEL})")
        raw_dir = f"{RAW_DIR}/run{run}"
        os.makedirs(raw_dir, exist_ok=True)
        rows, ws_rows = [], []
        for po, case in cases.items():
            print(f"{po} ...", end=" ", flush=True)
            raw = ask_llm(client, case)
            with open(f"{raw_dir}/{po}_reply.json", "w", encoding="utf-8") as f:
                f.write(raw)
            reply = json.loads(raw)
            for fd in reply["findings"]:
                rows.append([po, fd["problem_key"], fd["cause_category"], fd["explanation"], fd["action"]])
            ws = reply["worksheet"]
            ws_rows.append([po, ws["po_period_receipt_value"], ws["po_period_bill_value"],
                            ws["po_difference_bill_minus_receipt"]])
            print(f"{len(reply['findings'])} finding(s)")

        out, ws_out = f"{OUT_PREFIX}_run{run}.csv", f"{WORKSHEET_PREFIX}_run{run}.csv"
        with open(ws_out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["po", "period_receipt_value", "period_bill_value", "difference_bill_minus_receipt"])
            w.writerows(ws_rows)
        write_findings(out, rows)
        print(f"{len(rows)} findings written to {out}, worksheet totals to {ws_out}\n")
    print(f"Summary across runs:  python evaluate.py --runs {OUT_PREFIX}")

if __name__ == "__main__":
    main()
