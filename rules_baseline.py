"""Rule-based baseline for October month-end P2P reconciliation.

Reads ONLY the structured Odoo tables (mail_message is deliberately ignored),
checks every PO line as at month-end (documents after CUTOFF are only used as later evidence),
and writes one finding per problem line to rules_findings.csv.

Output columns (shared with the LLM agent so both can be scored by evaluate.py):
    po, problem_key, cause_category, explanation, action
problem_key format: "<table>:<id>", e.g. "account.move.line:8", "stock.picking:12"
"""
import csv, os, io, sys, zipfile
from collections import defaultdict

# Always work inside this script's own folder, wherever it is run from
os.chdir(os.path.dirname(os.path.abspath(__file__)))

DATA_ZIP = "odoo_p2p_10po.zip"
PERIOD = "2026-10"          # month being reconciled
CUTOFF = "2026-10-31"       # month-end: only documents dated up to here count
OUT = "rules_findings.csv"


def load(zip_path):
    tables = {}
    with zipfile.ZipFile(zip_path) as z:
        for n in z.namelist():
            if n.endswith(".csv"):
                name = n.split("/")[-1][:-4]
                tables[name] = list(csv.DictReader(io.TextIOWrapper(z.open(n), encoding="utf-8")))
    return tables


def month(d):
    return d[:7]


def run(t):
    """Month-end view: every comparison is made as at CUTOFF (end of PERIOD).
    Documents dated after CUTOFF never enter the October figures; they are only used as
    later evidence (e.g. a November bill shows an October receipt was simply billed later)."""
    po = {r["id"]: r for r in t["purchase_order"]}
    picking = {r["id"]: r for r in t["stock_picking"]}
    bill = {r["id"]: r for r in t["account_move"]}
    agreed = {(r["partner_id"], r["product_id"]): float(r["price"]) for r in t["product_supplierinfo"]}

    moves_by_line, bill_lines_by_line = defaultdict(list), defaultdict(list)
    for m in t["stock_move"]:
        moves_by_line[m["purchase_line_id"]].append(m)
    for bl in t["account_move_line"]:
        bill_lines_by_line[bl["purchase_line_id"]].append(bl)

    bdate = lambda bl: bill[bl["move_id"]]["invoice_date"]
    qty = lambda rows: sum(float(x["quantity"]) for x in rows)

    findings = []
    for line in t["purchase_order_line"]:
        order = po[line["order_id"]]
        po_name = order["name"]
        po_price = float(line["price_unit"])
        agreed_price = agreed.get((order["partner_id"], line["product_id"]))

        # split every document into "up to month-end" and "after month-end"
        moves = [m for m in moves_by_line[line["id"]] if m["date"] <= CUTOFF]
        later_moves = [m for m in moves_by_line[line["id"]] if m["date"] > CUTOFF]
        blines = [b for b in bill_lines_by_line[line["id"]] if bdate(b) <= CUTOFF]
        later_blines = [b for b in bill_lines_by_line[line["id"]] if bdate(b) > CUTOFF]

        def add(key, cat, expl, action):
            findings.append([po_name, key, cat, expl, action])

        # ---- Rule 1: price checks on bills up to month-end (bill price vs PO price vs agreed price) ----
        price_hit = False
        for bl in blines:
            bp = float(bl["price_unit"])
            if bp == po_price:
                continue
            price_hit = True
            if agreed_price is not None and po_price != agreed_price and bp == agreed_price:
                add(f"purchase.order.line:{line['id']}", "po_price_error",
                    f"{line['name']}: PO price {po_price:g} differs from agreed price {agreed_price:g}; "
                    f"vendor billed agreed price {bp:g}.",
                    "Correct PO price and adjust inventory valuation.")
            elif bp > po_price:
                add(f"account.move.line:{bl['id']}", "vendor_overbilled",
                    f"{line['name']}: bill price {bp:g} is above PO/agreed price {po_price:g}.",
                    f"Dispute bill {bill[bl['move_id']]['name']}; request credit note for "
                    f"{(bp - po_price) * float(bl['quantity']):g}.")
            else:
                add(f"account.move.line:{bl['id']}", "vendor_underbilled",
                    f"{line['name']}: bill price {bp:g} is below PO/agreed price {po_price:g}.",
                    f"Confirm with vendor; a supplementary bill of "
                    f"{(po_price - bp) * float(bl['quantity']):g} may follow.")
        if price_hit:
            continue

        # ---- Rule 2: quantity checks as at month-end ----
        received = qty(moves)                    # net of returns, up to CUTOFF
        billed = qty(blines)                     # up to CUTOFF
        has_return = any(float(m["quantity"]) < 0 for m in moves)
        last_bl = max(blines, key=bdate) if blines else None
        first_receipt = next((m for m in moves if float(m["quantity"]) > 0), None)

        if billed > received:
            later_received = sum(float(m["quantity"]) for m in later_moves if float(m["quantity"]) > 0)
            if later_received > 0 and received + later_received >= billed:
                pk = next(m for m in later_moves if float(m["quantity"]) > 0)["picking_id"]
                add(f"stock.picking:{pk}", "timing",
                    f"{line['name']}: billed {billed:g} by {CUTOFF} but received {received:g}; "
                    f"receipt {picking[pk]['name']} followed after month-end.",
                    "No error; goods billed before receipt, received next month.")
            else:
                why = "goods were returned but vendor billed the returned quantity" if has_return \
                    else "vendor billed more than was received"
                add(f"account.move.line:{last_bl['id']}", "vendor_overbilled",
                    f"{line['name']}: billed {billed:g} vs net received {received:g} at {CUTOFF}; {why}.",
                    f"Request credit note for {(billed - received) * po_price:g}.")
            continue
        if received > billed:
            gap_value = (received - billed) * po_price
            if later_blines:
                key = f"stock.picking:{first_receipt['picking_id']}" if first_receipt else \
                      f"account.move.line:{later_blines[0]['id']}"
                add(key, "timing",
                    f"{line['name']}: received {received:g} but billed {billed:g} at {CUTOFF}; "
                    f"bill {bill[later_blines[0]['move_id']]['name']} arrived after month-end.",
                    f"No error; accrue {gap_value:g} goods received not invoiced at month-end.")
            else:
                key = f"account.move.line:{last_bl['id']}" if last_bl else \
                      f"stock.picking:{first_receipt['picking_id']}"
                add(key, "timing",
                    f"{line['name']}: received {received:g} but billed {billed:g} at {CUTOFF}; "
                    f"remaining quantity not yet billed.",
                    f"No error; accrue {gap_value:g} goods received not invoiced.")
            continue

        # ---- Rule 3: quantities agree at month-end, but receipt and bill fell in different months ----
        rec_in_period = [m for m in moves if month(m["date"]) == PERIOD]
        bill_in_period = [b for b in blines if month(bdate(b)) == PERIOD]
        if bill_in_period and not rec_in_period:
            add(f"account.move.line:{bill_in_period[0]['id']}", "timing",
                f"{line['name']}: received before {PERIOD}, billed in {PERIOD}.",
                "No error; clear prior-month accrual.")
        elif rec_in_period and not bill_in_period:
            add(f"stock.picking:{rec_in_period[0]['picking_id']}", "timing",
                f"{line['name']}: billed before {PERIOD}, received in {PERIOD}.",
                "No error; clear prior-month prepayment / billed-not-received balance.")
    return findings

if __name__ == "__main__":
    if "--test" in sys.argv[1:]:   # held-out test set; same logic
        path, OUT = "odoo_p2p_test.zip", "test_" + OUT
    else:
        path = sys.argv[1] if len(sys.argv) > 1 else DATA_ZIP
    findings = run(load(path))
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["po", "problem_key", "cause_category", "explanation", "action"])
        w.writerows(findings)
    print(f"{len(findings)} findings written to {OUT}")
