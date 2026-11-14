"""Held-out TEST set: 10 POs designed together with the user on 2026-11-14 (see experiment_log.md).

Writes:
  odoo_p2p_test.zip                       data for rules / workflow / agent (same tables as the dev set)
  answer_key/test_expected_findings.csv   answer key - kept OUT of the zip

Same reconciliation as the dev set: October 2026, run date 2026-11-10.
Vendors and products are all new. PO numbers (P00011-P00020) are shuffled with a fixed seed,
so the position of a PO says nothing about its answer.
"""
import csv, os, random, zipfile
from collections import defaultdict

os.chdir(os.path.dirname(os.path.abspath(__file__)))

OUT = "odoo_p2p_test"
PERIOD, CUTOFF, RUN_DATE = "2026-10", "2026-10-31", "2026-11-10"

# ---------------------------------------------------------------------------------------------
# The 10 agreed designs. lines: (code, name, qty, po_price, agreed_price)
# pickings: (kind, date, [(line_index, qty)], return_of_picking_index or None)   kind: IN / OUT
# bills: (date, vendor_ref, [(line_index, qty, unit_price)])
# notes: (target, date, author, body)   target: "po" | ("picking", i) | ("bill", i)
# answer: cause_category ("none" = nothing should be reported), problem keys as builder functions
# ---------------------------------------------------------------------------------------------
DESIGNS = [
    dict(case=1, vendor="Nordic Office Furniture Pte Ltd", date="2026-10-03",
         lines=[("FCAB-01", "Filing Cabinet", 8, 280, 280), ("BSHF-01", "Bookshelf", 6, 180, 180),
                ("LAMP-01", "Desk Lamp", 20, 45, 45)],
         pickings=[("IN", "2026-10-09", [(0, 8), (1, 6)], None), ("IN", "2026-10-20", [(2, 20)], None)],
         bills=[("2026-10-12", "NOF-1102", [(0, 8, 280), (1, 6, 180)]), ("2026-10-24", "NOF-1131", [(2, 20, 45)])],
         notes=[("po", "2026-10-03", "Purchasing - Mei Ling", "Please deliver to Level 5."),
                (("picking", 0), "2026-10-09", "Warehouse - Ahmad",
                 "Desk lamps out of stock; second delivery expected around 20 Oct.")],
         cause="none", keys=lambda ids: [],
         record="(none - nothing wrong at month-end)",
         text="Normal: multi-line PO, two receipts, two bills, all matched",
         action="No action", evidence="normal", twin=""),
    dict(case=2, vendor="Harbour Packaging Supplies Pte Ltd", date="2026-10-06",
         lines=[("CTN-50", "Shipping Carton (bundle of 50)", 80, 25, 25), ("TAPE-C", "Packing Tape (case)", 30, 40, 40)],
         pickings=[("IN", "2026-10-14", [(0, 80), (1, 30)], None)],
         bills=[("2026-10-21", "HP-2210", [(0, 80, 25)]), ("2026-11-05", "HP-2287", [(1, 30, 40)])],
         notes=[(("bill", 0), "2026-10-21", "AP - Priya",
                 "Vendor billed the cartons first; the tape will be billed separately.")],
         cause="timing", keys=lambda ids: [f"stock.picking:{ids['pick'][0]}", f"account.move.line:{ids['bline'][1][0]}"],
         record="receipt, or the November bill's tape line",
         text="Timing: tape received in October, billed in November",
         action="No error; accrue 1200 goods received not invoiced at October month-end", evidence="structured", twin=""),
    dict(case=3, vendor="Lumen Electrical Trading Pte Ltd", date="2026-10-08",
         lines=[("LED-P", "LED Panel Light", 40, 60, 60), ("TRAY-1", "Cable Tray (section)", 50, 8, 18),
                ("JBOX", "Junction Box", 100, 5, 5)],
         pickings=[("IN", "2026-10-16", [(0, 40), (1, 50), (2, 100)], None)],
         bills=[("2026-10-23", "LE-5530", [(0, 40, 60), (1, 50, 18), (2, 100, 5)])],
         notes=[("po", "2026-10-08", "Purchasing - Mei Ling", "Ordered per vendor quotation Q-5521."),
                (("bill", 0), "2026-10-23", "AP - Priya", "Bill posted as received from vendor.")],
         cause="po_price_error", keys=lambda ids: [f"purchase.order.line:{ids['line'][1]}"],
         record="PO line Cable Tray (8 entered, agreed 18)",
         text="PO price entered as 8 instead of agreed 18 on one line; vendor billed correctly",
         action="Correct PO price to 18; adjust inventory valuation (+500); pay the bill", evidence="structured", twin=""),
    dict(case=4, vendor="Pacific Safety Gear Pte Ltd", date="2026-10-02",
         lines=[("HLM-01", "Safety Helmet", 60, 35, 35)],
         pickings=[("IN", "2026-10-10", [(0, 60)], None)],
         bills=[("2026-10-15", "PS-7781", [(0, 60, 35)]), ("2026-10-28", "PS-7781A", [(0, 60, 35)])],
         notes=[(("picking", 0), "2026-10-10", "Warehouse - Ahmad", "All 60 helmets received in good condition."),
                (("bill", 1), "2026-10-28", "AP - Priya", "Bill posted as received from vendor.")],
         cause="vendor_overbilled",
         keys=lambda ids: [f"account.move.line:{ids['bline'][1][0]}", f"account.move.line:{ids['bline'][0][0]}"],
         record="second bill (duplicate); first bill also accepted",
         text="Same delivery billed twice (PS-7781 and PS-7781A): 120 billed vs 60 received",
         action="Hold the second bill; ask vendor to cancel it or issue a credit note of 2100", evidence="structured", twin=""),
    dict(case=5, vendor="GreenLeaf Pantry Supplies Pte Ltd", date="2026-10-07",
         lines=[("COF-KG", "Coffee Beans (kg)", 50, 32, 32), ("TEA-BX", "Tea Bags (box)", 40, 12, 12)],
         pickings=[("IN", "2026-10-13", [(0, 50), (1, 40)], None)],
         bills=[("2026-10-20", "GL-0412", [(0, 50, 30), (1, 40, 12)])],
         notes=[("po", "2026-10-07", "Purchasing - Mei Ling", "Q4 pantry restock.")],
         cause="vendor_underbilled", keys=lambda ids: [f"account.move.line:{ids['bline'][0][0]}"],
         record="bill line Coffee Beans (30 vs agreed 32)",
         text="Vendor billed coffee at 30 instead of agreed 32; no discount on record",
         action="Confirm with vendor; a supplementary bill of 100 may follow; PO unchanged", evidence="structured",
         twin="case 6"),
    dict(case=6, vendor="Apex Printing Services Pte Ltd", date="2026-10-09",
         lines=[("BCARD", "Business Cards (box)", 100, 20, 20)],
         pickings=[("IN", "2026-10-17", [(0, 100)], None)],
         bills=[("2026-10-24", "AP-3390", [(0, 100, 19)])],
         notes=[("po", "2026-10-09", "Purchasing - Mei Ling",
                 "Vendor offered a 5% promotional discount on this order. Approved by Head of Procurement on 9 Oct. "
                 "PO price not updated yet.")],
         cause="approved_price_change",
         keys=lambda ids: [f"account.move.line:{ids['bline'][0][0]}", f"purchase.order.line:{ids['line'][0]}"],
         record="bill line or PO line (both accepted)",
         text="Approved 5% discount (20 -> 19); PO price not updated",
         action="Update PO price to 19; adjust inventory valuation (-100); no vendor follow-up", evidence="note",
         twin="case 5"),
    dict(case=7, vendor="TechParts Computer Supplies Pte Ltd", date="2026-10-05",
         lines=[("KBD-W", "Wireless Keyboard", 30, 40, 40), ("MSE-W", "Wireless Mouse", 30, 15, 15)],
         pickings=[("IN", "2026-10-08", [(0, 30), (1, 30)], None)],
         bills=[("2026-10-20", "TP-8812", [(0, 26, 40), (1, 30, 15)])],
         notes=[(("picking", 0), "2026-10-12", "Warehouse - Ahmad",
                 "4 keyboards have broken keys; the vendor's driver collected them today.")],
         cause="unrecorded_return", keys=lambda ids: [f"stock.picking:{ids['pick'][0]}"],
         record="receipt (4 keyboards taken back, no return recorded)",
         text="4 keyboards taken back by the driver; no return in the system; vendor billed the 26 kept",
         action="Record a return of 4 keyboards (-160 stock); bill is correct, pay it", evidence="note", twin=""),
    dict(case=8, vendor="Coastal Cleaning Supplies Pte Ltd", date="2026-10-15",
         lines=[("CLN-DR", "Cleaning Detergent (drum)", 40, 30, 30)],
         pickings=[("IN", "2026-10-31", [(0, 40)], None)],
         bills=[("2026-11-04", "CC-1907", [(0, 40, 30)])],
         notes=[(("picking", 0), "2026-11-03", "Warehouse - Ahmad",
                 "The 40 drums only arrived today. The receipt was confirmed in the system on 31 Oct ahead of time "
                 "to make the month-end.")],
         cause="cut_off_error", keys=lambda ids: [f"stock.picking:{ids['pick'][0]}"],
         record="receipt dated 31 Oct (goods arrived 3 Nov)",
         text="Receipt confirmed on 31 Oct ahead of time; goods physically arrived 3 Nov",
         action="Move the receipt to November; reverse the 1200 overstated October receipt / accrual", evidence="note",
         twin=""),
    dict(case=9, vendor="Metro Stationery Wholesale Pte Ltd", date="2026-10-04",
         lines=[("NBK-A4", "A4 Notebooks (box)", 40, 18, 18)],
         pickings=[("IN", "2026-10-11", [(0, 36)], None)],
         bills=[("2026-10-18", "MS-6604", [(0, 40, 18)])],
         notes=[(("picking", 0), "2026-10-11", "Warehouse - Ahmad",
                 "All 40 boxes of notebooks delivered and checked in.")],
         cause="insufficient_evidence",
         keys=lambda ids: [f"stock.picking:{ids['pick'][0]}", f"account.move.line:{ids['bline'][0][0]}"],
         record="receipt or bill line",
         text="Records contradict: note says 40 boxes arrived, system receipt 36, bill 40",
         action="Check delivery note / recount before paying the 72 difference", evidence="note", twin=""),
    dict(case=10, vendor="Summit Kitchen Equipment Pte Ltd", date="2026-10-10",
         lines=[("MWV-01", "Microwave Oven", 10, 150, 150)],
         pickings=[("IN", "2026-10-16", [(0, 10)], None), ("OUT", "2026-11-06", [(0, -10)], 0)],
         bills=[("2026-10-22", "SK-2045", [(0, 10, 150)])],
         notes=[(("picking", 1), "2026-11-06", "Warehouse - Ahmad",
                 "All 10 microwaves returned - the model does not fit the pantry cabinets. Vendor will issue a credit note.")],
         cause="none", keys=lambda ids: [],
         record="(none - nothing wrong at 31 Oct; the November return belongs to November)",
         text="Trap: received and billed 10 in October, all returned in November",
         action="No action for October", evidence="normal", twin=""),
]


def build():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs("answer_key", exist_ok=True)
    # shuffle PO numbers so the order says nothing about the answer
    order = list(range(len(DESIGNS)))
    random.Random(20261114).shuffle(order)
    designs = [DESIGNS[i] for i in order]   # designs[k] gets PO name P000(11+k)

    partners, products, supplierinfo, pos, polines = [], [], [], [], []
    pickings_raw, moves_raw, bills_raw, notes_raw, answers = [], [], [], [], []

    for k, d in enumerate(designs):
        po_id, po_name = k + 1, f"P000{11 + k}"
        partners.append([po_id, d["vendor"], 1])
        d["_po"] = (po_id, po_name)
        line_ids = []
        for code, name, qty, price, agreed in d["lines"]:
            pid = len(products) + 1
            products.append([pid, code, name, "Units"])
            supplierinfo.append([len(supplierinfo) + 1, po_id, pid, f"{agreed:.2f}", "SGD", "2026-01-01"])
            lid = len(polines) + 1
            polines.append(dict(id=lid, order_id=po_id, product_id=pid, name=name, qty=qty, price=price))
            line_ids.append(lid)
        d["_lines"] = line_ids
        pos.append([po_id, po_name, po_id, d["date"], d["date"], "purchase", "SGD",
                    f"{sum(q * p for _, _, q, p, _ in d['lines']):.2f}"])
        for i, (kind, date, mv, ret) in enumerate(d["pickings"]):
            pickings_raw.append(dict(design=d, idx=i, kind=kind, date=date, moves=mv, ret=ret))
        for i, (date, ref, bl) in enumerate(d["bills"]):
            bills_raw.append(dict(design=d, idx=i, date=date, ref=ref, lines=bl))

    # pickings: ids/names in date order (IN and OUT numbered separately, like Odoo)
    pickings_raw.sort(key=lambda p: (p["date"], p["design"]["_po"][0], p["idx"]))
    n_in = n_out = 0
    for pid, p in enumerate(pickings_raw, 1):
        p["id"] = pid
        if p["kind"] == "IN":
            n_in += 1; p["name"] = f"WH/IN/{n_in:05d}"
        else:
            n_out += 1; p["name"] = f"WH/OUT/{n_out:05d}"
        p["design"].setdefault("_pick", {})[p["idx"]] = p
    pickings, moves = [], []
    for p in pickings_raw:
        d = p["design"]
        if p["ret"] is None:
            ptype, origin, ret_id = "Receipts", d["_po"][1], ""
        else:
            src = d["_pick"][p["ret"]]
            ptype, origin, ret_id = "Delivery Orders", f"Return of {src['name']}", src["id"]
        pickings.append([p["id"], p["name"], ptype, d["_po"][0], origin, ret_id, p["date"], "done"])
        for li, q in p["moves"]:
            lid = d["_lines"][li]; price = d["lines"][li][3]
            moves.append([len(moves) + 1, p["id"], lid, polines[lid - 1]["product_id"], p["date"], q,
                          f"{price:.2f}", f"{q * price:.2f}", "done"])

    # bills: names in date order per month
    bills_raw.sort(key=lambda b: (b["date"], b["design"]["_po"][0], b["idx"]))
    per_month = defaultdict(int)
    bills, blines = [], []
    for bid, b in enumerate(bills_raw, 1):
        d = b["design"]; ym = b["date"][:7]
        per_month[ym] += 1
        b["id"], b["name"] = bid, f"BILL/{ym[:4]}/{ym[5:]}/{per_month[ym]:04d}"
        total = sum(q * p for _, q, p in b["lines"])
        bills.append([bid, b["name"], "in_invoice", d["_po"][0], b["date"], b["date"], b["ref"], d["_po"][1],
                      "posted", f"{total:.2f}", f"{total:.2f}"])
        ids = []
        for li, q, p in b["lines"]:
            lid = d["_lines"][li]
            blines.append([len(blines) + 1, bid, lid, polines[lid - 1]["product_id"], d["lines"][li][1], q,
                           f"{p:.2f}", f"{q * p:.2f}"])
            ids.append(len(blines))
        d.setdefault("_bill", {})[b["idx"]] = b
        d.setdefault("_bline", {})[b["idx"]] = ids

    # notes, in date order
    for d in designs:
        for target, date, author, body in d["notes"]:
            if target == "po":
                model, rid, rname = "purchase.order", d["_po"][0], d["_po"][1]
            elif target[0] == "picking":
                p = d["_pick"][target[1]]; model, rid, rname = "stock.picking", p["id"], p["name"]
            else:
                b = d["_bill"][target[1]]; model, rid, rname = "account.move", b["id"], b["name"]
            notes_raw.append([model, rid, rname, date, author, body])
    notes_raw.sort(key=lambda n: (n[3], n[0], n[1]))
    notes = [[i + 1] + n for i, n in enumerate(notes_raw)]

    # PO lines with qty_received / qty_invoiced as at RUN_DATE (all documents, as Odoo shows them)
    rec_q, inv_q = defaultdict(float), defaultdict(float)
    for m in moves:
        rec_q[m[2]] += m[5]
    for bl in blines:
        inv_q[bl[2]] += bl[5]
    polines_rows = [[l["id"], l["order_id"], l["product_id"], l["name"], l["qty"], f"{l['price']:.2f}",
                     f"{l['qty'] * l['price']:.2f}", int(rec_q[l["id"]]), int(inv_q[l["id"]])] for l in polines]

    tables = {
        "res_partner": (["id", "name", "supplier_rank"], partners),
        "product_product": (["id", "default_code", "name", "uom"], products),
        "product_supplierinfo": (["id", "partner_id", "product_id", "price", "currency", "date_start"], supplierinfo),
        "purchase_order": (["id", "name", "partner_id", "date_order", "date_approve", "state", "currency",
                            "amount_untaxed"], pos),
        "purchase_order_line": (["id", "order_id", "product_id", "name", "product_qty", "price_unit",
                                 "price_subtotal", "qty_received", "qty_invoiced"], polines_rows),
        "stock_picking": (["id", "name", "picking_type", "partner_id", "origin", "return_of_picking_id",
                           "date_done", "state"], pickings),
        "stock_move": (["id", "picking_id", "purchase_line_id", "product_id", "date", "quantity", "price_unit",
                        "value", "state"], moves),
        "account_move": (["id", "name", "move_type", "partner_id", "invoice_date", "date", "ref", "invoice_origin",
                          "state", "amount_untaxed", "amount_total"], bills),
        "account_move_line": (["id", "move_id", "purchase_line_id", "product_id", "name", "quantity", "price_unit",
                               "price_subtotal"], blines),
        "mail_message": (["id", "model", "res_id", "record_name", "date", "author", "body"], notes),
    }
    for name, (header, rows) in tables.items():
        with open(f"{OUT}/{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(header); w.writerows(rows)
    with zipfile.ZipFile(f"{OUT}.zip", "w") as z:
        for name in tables:
            z.write(f"{OUT}/{name}.csv", f"{OUT}/{name}.csv")

    # answer key (October figures computed from the generated tables)
    line_po = {l["id"]: l["order_id"] for l in polines}
    rec_v, bill_v = defaultdict(float), defaultdict(float)
    for m in moves:
        if m[4][:7] == PERIOD:
            rec_v[line_po[m[2]]] += float(m[7])
    for b in bills:
        if b[4][:7] == PERIOD:
            bill_v[b[3]] += float(b[9])
    for d in designs:
        po_id, po_name = d["_po"]
        ids = {"pick": {i: p["id"] for i, p in d["_pick"].items()}, "line": d["_lines"], "bline": d["_bline"]}
        answers.append([po_name, f"{rec_v[po_id]:g}", f"{bill_v[po_id]:g}", f"{bill_v[po_id] - rec_v[po_id]:g}",
                        d["cause"], "|".join(d["keys"](ids)), d["record"], d["text"], d["action"],
                        d["evidence"], d["twin"], d["case"]])
    with open("answer_key/test_expected_findings.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["po", "oct_receipt_value", "oct_bill_value", "difference_bill_minus_receipt", "cause_category",
                    "problem_keys", "problem_record", "cause", "expected_action", "key_evidence", "twin_of",
                    "design_case"])
        w.writerows(answers)
    return answers, tables


if __name__ == "__main__":
    answers, tables = build()
    print(f"{'PO':7} {'case':>4} {'rec':>6} {'bill':>6} {'diff':>6}  {'cause':22} keys")
    for a in answers:
        print(f"{a[0]:7} {a[11]:>4} {a[1]:>6} {a[2]:>6} {a[3]:>6}  {a[4]:22} {a[5]}")
    tr = sum(float(a[1]) for a in answers); tb = sum(float(a[2]) for a in answers)
    print(f"TOTAL October: receipts {tr:g}, bills {tb:g}, difference {tb - tr:g}")
