import csv, os, zipfile
from collections import defaultdict

# Always work inside this script's own folder, wherever it is run from
os.chdir(os.path.dirname(os.path.abspath(__file__)))

OUT = "odoo_p2p_10po"
DATA_DIR = f"data/{OUT}"      # unzipped tables; the zip goes to data/{OUT}.zip
os.makedirs(DATA_DIR, exist_ok=True)

def write(name, header, rows, folder=DATA_DIR):
    with open(f"{folder}/{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)

# res.partner (vendors)
write("res_partner", ["id", "name", "supplier_rank"], [
    [1, "Comfort Seating Pte Ltd", 1],
    [2, "PaperMart Supplies Pte Ltd", 1],
    [3, "Bolt & Nut Trading Pte Ltd", 1],
    [4, "Vision Display Co Pte Ltd", 1],
    [5, "InkJet Solutions Pte Ltd", 1],
    [6, "DeskPro Furniture Pte Ltd", 1],
    [7, "CableLink Electronics Pte Ltd", 1],
    [8, "SafeHands Industrial Pte Ltd", 1],
    [9, "PrintWorks Equipment Pte Ltd", 1],
    [10, "OfficeHub Stationery Pte Ltd", 1],
])

# product.product
write("product_product", ["id", "default_code", "name", "uom"], [
    [1, "CHAIR-01", "Office Chair", "Units"],
    [2, "PAPER-A4", "A4 Paper (box)", "Box"],
    [3, "BOLT-M8", "M8 Steel Bolt (box)", "Box"],
    [4, "MON-24", "24-inch Monitor", "Units"],
    [5, "TONER-01", "Printer Toner Cartridge", "Units"],
    [6, "DESK-STD", "Standing Desk", "Units"],
    [7, "CBL-HDMI", "HDMI Cable 2m", "Units"],
    [8, "GLOVE-BX", "Safety Gloves (box)", "Box"],
    [9, "PRN-LSR", "Laser Printer", "Units"],
    [10, "MRK-WB", "Whiteboard Marker (box)", "Box"],
    [11, "WSH-M8", "M8 Washer (box)", "Box"],
    [12, "NUT-M8", "M8 Hex Nut (box)", "Box"],
    [13, "ADP-USBC", "USB-C to HDMI Adapter", "Units"],
])

# product.supplierinfo (agreed vendor prices)
write("product_supplierinfo", ["id", "partner_id", "product_id", "price", "currency", "date_start"], [
    [1, 1, 1, 150.00, "SGD", "2026-01-01"],
    [2, 2, 2, 40.00, "SGD", "2026-01-01"],
    [3, 3, 3, 10.00, "SGD", "2026-01-01"],
    [4, 4, 4, 200.00, "SGD", "2026-01-01"],
    [5, 5, 5, 50.00, "SGD", "2026-01-01"],
    [6, 6, 6, 400.00, "SGD", "2026-01-01"],
    [7, 7, 7, 20.00, "SGD", "2026-01-01"],
    [8, 8, 8, 30.00, "SGD", "2026-01-01"],
    [9, 9, 9, 300.00, "SGD", "2026-01-01"],
    [10, 10, 10, 15.00, "SGD", "2026-01-01"],
    [11, 3, 11, 6.00, "SGD", "2026-01-01"],
    [12, 3, 12, 8.00, "SGD", "2026-01-01"],
    [13, 7, 13, 25.00, "SGD", "2026-01-01"],
])

# purchase.order
write("purchase_order", ["id", "name", "partner_id", "date_order", "date_approve", "state", "currency", "amount_untaxed"], [
    [1, "P00001", 1, "2026-09-15", "2026-09-15", "purchase", "SGD", 3000.00],
    [2, "P00002", 2, "2026-10-20", "2026-10-20", "purchase", "SGD", 2000.00],
    [3, "P00003", 3, "2026-10-02", "2026-10-02", "purchase", "SGD", 1900.00],
    [4, "P00004", 4, "2026-10-01", "2026-10-01", "purchase", "SGD", 2000.00],
    [5, "P00005", 5, "2026-09-28", "2026-09-28", "purchase", "SGD", 1500.00],
    [6, "P00006", 6, "2026-10-05", "2026-10-05", "purchase", "SGD", 4000.00],
    [7, "P00007", 7, "2026-10-06", "2026-10-06", "purchase", "SGD", 3000.00],
    [8, "P00008", 8, "2026-10-07", "2026-10-07", "purchase", "SGD", 1800.00],
    [9, "P00009", 9, "2026-10-12", "2026-10-12", "purchase", "SGD", 1500.00],
    [10, "P00010", 10, "2026-10-09", "2026-10-09", "purchase", "SGD", 600.00],
])

# purchase.order.line (qty_received / qty_invoiced as at run date 2026-11-10)
po_lines = [
    [1, 1, 1, "Office Chair", 20, 150.00, 3000.00, 20, 20],
    [2, 2, 2, "A4 Paper (box)", 50, 40.00, 2000.00, 50, 50],
    [3, 3, 3, "M8 Steel Bolt (box)", 100, 12.00, 1200.00, 100, 100],
    [4, 4, 4, "24-inch Monitor", 10, 200.00, 2000.00, 10, 8],
    [5, 5, 5, "Printer Toner Cartridge", 30, 50.00, 1500.00, 25, 30],
    [6, 6, 6, "Standing Desk", 10, 400.00, 4000.00, 10, 6],
    [7, 7, 7, "HDMI Cable 2m", 100, 20.00, 2000.00, 100, 100],
    [8, 8, 8, "Safety Gloves (box)", 60, 30.00, 1800.00, 60, 60],
    [9, 9, 9, "Laser Printer", 5, 300.00, 1500.00, 5, 5],
    [10, 10, 10, "Whiteboard Marker (box)", 40, 15.00, 600.00, 36, 40],
    # extra normal lines (multi-line POs)
    [11, 3, 11, "M8 Washer (box)", 50, 6.00, 300.00, 50, 50],
    [12, 3, 12, "M8 Hex Nut (box)", 50, 8.00, 400.00, 50, 50],
    [13, 7, 13, "USB-C to HDMI Adapter", 40, 25.00, 1000.00, 40, 40],
]
write("purchase_order_line", ["id", "order_id", "product_id", "name", "product_qty", "price_unit", "price_subtotal", "qty_received", "qty_invoiced"], po_lines)

# stock.picking (receipts and returns)
write("stock_picking", ["id", "name", "picking_type", "partner_id", "origin", "return_of_picking_id", "date_done", "state"], [
    [1, "WH/IN/00001", "Receipts", 1, "P00001", "", "2026-09-26", "done"],
    [2, "WH/IN/00002", "Receipts", 2, "P00002", "", "2026-10-29", "done"],
    [3, "WH/IN/00003", "Receipts", 3, "P00003", "", "2026-10-10", "done"],
    [4, "WH/IN/00004", "Receipts", 4, "P00004", "", "2026-10-08", "done"],
    [5, "WH/IN/00005", "Receipts", 5, "P00005", "", "2026-10-05", "done"],
    [6, "WH/OUT/00001", "Delivery Orders", 5, "Return of WH/IN/00005", 5, "2026-10-09", "done"],
    [7, "WH/IN/00006", "Receipts", 6, "P00006", "", "2026-10-13", "done"],
    [8, "WH/IN/00007", "Receipts", 7, "P00007", "", "2026-10-14", "done"],
    [9, "WH/IN/00008", "Receipts", 8, "P00008", "", "2026-10-15", "done"],
    [10, "WH/IN/00009", "Receipts", 9, "P00009", "", "2026-11-02", "done"],
    [11, "WH/IN/00010", "Receipts", 10, "P00010", "", "2026-10-16", "done"],
    [12, "WH/IN/00011", "Receipts", 4, "P00004", "", "2026-10-15", "done"],  # 2nd batch of P00004
])

# stock.move (value: + for receipt, - for return; valued at PO unit price)
moves = [
    [1, 1, 1, 1, "2026-09-26", 20, 150.00, 3000.00, "done"],
    [2, 2, 2, 2, "2026-10-29", 50, 40.00, 2000.00, "done"],
    [3, 3, 3, 3, "2026-10-10", 100, 12.00, 1200.00, "done"],
    [4, 4, 4, 4, "2026-10-08", 6, 200.00, 1200.00, "done"],
    [5, 5, 5, 5, "2026-10-05", 30, 50.00, 1500.00, "done"],
    [6, 6, 5, 5, "2026-10-09", -5, 50.00, -250.00, "done"],
    [7, 7, 6, 6, "2026-10-13", 10, 400.00, 4000.00, "done"],
    [8, 8, 7, 7, "2026-10-14", 100, 20.00, 2000.00, "done"],
    [9, 9, 8, 8, "2026-10-15", 60, 30.00, 1800.00, "done"],
    [10, 10, 9, 9, "2026-11-02", 5, 300.00, 1500.00, "done"],
    [11, 11, 10, 10, "2026-10-16", 36, 15.00, 540.00, "done"],
    [12, 12, 4, 4, "2026-10-15", 4, 200.00, 800.00, "done"],   # P00004 2nd batch (the problem receipt)
    [13, 3, 11, 11, "2026-10-10", 50, 6.00, 300.00, "done"],
    [14, 3, 12, 12, "2026-10-10", 50, 8.00, 400.00, "done"],
    [15, 8, 13, 13, "2026-10-14", 40, 25.00, 1000.00, "done"],
]
write("stock_move", ["id", "picking_id", "purchase_line_id", "product_id", "date", "quantity", "price_unit", "value", "state"], moves)

# account.move (vendor bills, tax ignored)
bills = [
    [1, "BILL/2026/10/0001", "in_invoice", 1, "2026-10-03", "2026-10-03", "CS-INV-8812", "P00001", "posted", 3000.00, 3000.00],
    [2, "BILL/2026/10/0002", "in_invoice", 3, "2026-10-15", "2026-10-15", "BN-24577", "P00003", "posted", 1700.00, 1700.00],
    [3, "BILL/2026/10/0003", "in_invoice", 5, "2026-10-18", "2026-10-18", "IJ-10093", "P00005", "posted", 1500.00, 1500.00],
    [4, "BILL/2026/10/0004", "in_invoice", 4, "2026-10-20", "2026-10-20", "VD-3301", "P00004", "posted", 1600.00, 1600.00],
    [5, "BILL/2026/11/0001", "in_invoice", 2, "2026-11-04", "2026-11-04", "PM-55120", "P00002", "posted", 2000.00, 2000.00],
    [6, "BILL/2026/10/0005", "in_invoice", 6, "2026-10-22", "2026-10-22", "DP-0457", "P00006", "posted", 2400.00, 2400.00],
    [7, "BILL/2026/10/0006", "in_invoice", 7, "2026-10-24", "2026-10-24", "CL-77810", "P00007", "posted", 3200.00, 3200.00],
    [8, "BILL/2026/10/0007", "in_invoice", 8, "2026-10-27", "2026-10-27", "SH-2026-1190", "P00008", "posted", 990.00, 990.00],
    [9, "BILL/2026/10/0008", "in_invoice", 9, "2026-10-30", "2026-10-30", "PW-6021", "P00009", "posted", 1500.00, 1500.00],
    [10, "BILL/2026/10/0009", "in_invoice", 10, "2026-10-24", "2026-10-24", "OH-31402", "P00010", "posted", 600.00, 600.00],
    [11, "BILL/2026/10/0010", "in_invoice", 8, "2026-10-31", "2026-10-31", "SH-2026-1215", "P00008", "posted", 900.00, 900.00],
]
write("account_move", ["id", "name", "move_type", "partner_id", "invoice_date", "date", "ref", "invoice_origin", "state", "amount_untaxed", "amount_total"], bills)

# account.move.line (bill lines)
write("account_move_line", ["id", "move_id", "purchase_line_id", "product_id", "name", "quantity", "price_unit", "price_subtotal"], [
    [1, 1, 1, 1, "Office Chair", 20, 150.00, 3000.00],
    [2, 2, 3, 3, "M8 Steel Bolt (box)", 100, 10.00, 1000.00],
    [3, 3, 5, 5, "Printer Toner Cartridge", 30, 50.00, 1500.00],
    [4, 4, 4, 4, "24-inch Monitor", 8, 200.00, 1600.00],
    [5, 5, 2, 2, "A4 Paper (box)", 50, 40.00, 2000.00],
    [6, 6, 6, 6, "Standing Desk", 6, 400.00, 2400.00],
    [7, 7, 7, 7, "HDMI Cable 2m", 100, 22.00, 2200.00],
    [8, 8, 8, 8, "Safety Gloves (box)", 30, 33.00, 990.00],      # the problem bill
    [9, 9, 9, 9, "Laser Printer", 5, 300.00, 1500.00],
    [10, 10, 10, 10, "Whiteboard Marker (box)", 40, 15.00, 600.00],
    [11, 2, 11, 11, "M8 Washer (box)", 50, 6.00, 300.00],
    [12, 2, 12, 12, "M8 Hex Nut (box)", 50, 8.00, 400.00],
    [13, 7, 13, 13, "USB-C to HDMI Adapter", 40, 25.00, 1000.00],
    [14, 11, 8, 8, "Safety Gloves (box)", 30, 30.00, 900.00],     # normal 2nd bill
])

# mail.message (chatter notes; includes clues and ordinary noise)
write("mail_message", ["id", "model", "res_id", "record_name", "date", "author", "body"], [
    [1, "purchase.order", 1, "P00001", "2026-09-16", "Purchasing - Mei Ling", "Please deliver before end of September."],
    [2, "purchase.order", 2, "P00002", "2026-10-29", "Warehouse - Ahmad", "Received 50 boxes. Vendor said the invoice will be sent in early November."],
    [3, "purchase.order", 3, "P00003", "2026-10-03", "Purchasing - Mei Ling", "Vendor asked us to expedite; delivery confirmed for 10 Oct."],
    [4, "stock.picking", 12, "WH/IN/00011", "2026-10-15", "Warehouse - Ahmad", "Received the remaining 4 monitors. 2 units have cracked screens; the vendor's driver took them back on the spot."],
    [5, "stock.picking", 6, "WH/OUT/00001", "2026-10-09", "Warehouse - Ahmad", "Returned 5 cartridges - wrong model delivered. Vendor to issue a credit note."],
    [6, "account.move", 3, "BILL/2026/10/0003", "2026-10-18", "AP - Priya", "Bill posted as received from vendor."],
    # P00006: same pattern as P00004 (received 10, billed fewer), but this one is just split billing
    [7, "purchase.order", 6, "P00006", "2026-10-13", "Warehouse - Ahmad", "All 10 desks received in good condition. Stored at Level 2."],
    [8, "account.move", 6, "BILL/2026/10/0005", "2026-10-22", "AP - Priya", "Vendor confirmed the remaining 4 desks will be invoiced in November together with the installation fee."],
    # P00007: bill price above PO price on one line, but the increase was approved
    [9, "purchase.order", 7, "P00007", "2026-10-06", "Purchasing - Mei Ling", "Vendor quoted +10% on the HDMI cables for express shipping. Approved by Head of Procurement by email on 6 Oct. Will update PO price later."],
    [10, "purchase.order", 7, "P00007", "2026-10-14", "Warehouse - Ahmad", "100 cables and 40 adapters received."],
    # P00008: same pattern as P00007 (bill price above PO price), but NOT approved; only the first of two bills
    [11, "account.move", 8, "BILL/2026/10/0007", "2026-10-27", "AP - Priya", "Vendor says their new price list took effect on 1 Oct. Not sure if Purchasing agreed to this - please check."],
    [12, "purchase.order", 8, "P00008", "2026-10-28", "Purchasing - Mei Ling", "We did not accept any price increase. Contract price is fixed until Dec 2026."],
    # P00009: looks like normal "billed before received", but goods physically arrived in October
    [13, "purchase.order", 9, "P00009", "2026-10-31", "Warehouse - Ahmad", "5 printers arrived this afternoon. Could not validate the receipt - system down for maintenance. Will validate next week."],
    [14, "stock.picking", 10, "WH/IN/00009", "2026-11-02", "Warehouse - Ahmad", "Receipt validated today."],
    # P00010: control case - short receipt, no explanation anywhere
    [15, "purchase.order", 10, "P00010", "2026-10-09", "Purchasing - Mei Ling", "Please deliver to Level 3 store room."],
    [16, "account.move", 10, "BILL/2026/10/0009", "2026-10-24", "AP - Priya", "Bill posted as received from vendor."],
    # noise on the normal records
    [17, "stock.picking", 4, "WH/IN/00004", "2026-10-08", "Warehouse - Ahmad", "First batch: 6 monitors received, all in good condition."],
    [18, "account.move", 11, "BILL/2026/10/0010", "2026-10-31", "AP - Priya", "Bill posted as received from vendor."],
])

# Expected answers (for evaluation only - kept OUTSIDE the agent's data folder and zip)
# cause_category: timing | po_price_error | vendor_overbilled | vendor_underbilled | approved_price_change |
#                 unrecorded_return | cut_off_error | insufficient_evidence (none in this 10-PO set since 2026-11-12)
# problem_keys: "<table>:<id>" of the record at fault; several accepted answers separated by "|"
os.makedirs("answer_key", exist_ok=True)
write("expected_findings",
      ["po", "oct_receipt_value", "oct_bill_value", "difference_bill_minus_receipt", "cause_category", "problem_keys", "problem_record", "cause", "expected_action", "key_evidence", "twin_of"], [
    ["P00001", 0, 3000, 3000, "timing", "account.move.line:1|stock.picking:1", "BILL/2026/10/0001 (receipt WH/IN/00001 was in Sep)", "Timing: goods received in September, billed in October", "No error; reverse/clear September accrual", "structured", ""],
    ["P00002", 2000, 0, -2000, "timing", "stock.picking:2|account.move.line:5", "WH/IN/00002 (bill came in Nov)", "Timing: goods received in October, billed in November", "No error; accrue goods received not invoiced at October month-end", "structured", ""],
    ["P00003", 1900, 1700, -200, "po_price_error", "purchase.order.line:3", "PO line: M8 Steel Bolt (box); washer and nut lines are fine", "PO unit price entered as 12 instead of agreed 10; vendor billed correctly", "Correct PO price; adjust inventory valuation", "structured", ""],
    ["P00004", 2000, 1600, -400, "unrecorded_return", "stock.picking:12", "WH/IN/00011 (2nd receipt); WH/IN/00004 is fine", "2 damaged units in the 2nd delivery taken back by vendor driver, but no return recorded in system", "Create return for 2 units against WH/IN/00011 to reduce stock", "note", "P00006"],
    ["P00005", 1250, 1500, 250, "vendor_overbilled", "account.move.line:3", "BILL/2026/10/0003", "5 units returned with return document, but vendor still billed 30 units", "Request credit note from vendor for 250", "structured", ""],
    ["P00006", 4000, 2400, -1600, "timing", "account.move.line:6|stock.picking:7", "BILL/2026/10/0005 (partial bill)", "Timing: split billing; remaining 4 desks to be billed in November", "No error; accrue 1600 goods received not invoiced at October month-end", "note", "P00004"],
    ["P00007", 3000, 3200, 200, "approved_price_change", "account.move.line:7|purchase.order.line:7", "BILL/2026/10/0006, line HDMI Cable 2m; adapter line is fine", "Approved 10% express-shipping surcharge on HDMI cables; PO price not yet updated", "No vendor dispute; update PO price to 22 and adjust inventory valuation", "note", "P00008"],
    ["P00008", 1800, 1890, 90, "vendor_overbilled", "account.move.line:8", "BILL/2026/10/0007; BILL/2026/10/0010 is fine", "Vendor applied unapproved price increase on the first bill; contract price fixed at 30", "Dispute BILL/2026/10/0007; request credit note for 90", "note", "P00007"],
    ["P00009", 0, 1500, 1500, "cut_off_error", "stock.picking:10", "WH/IN/00009", "Cut-off error: goods physically arrived 31 Oct but receipt validated 2 Nov (system down)", "October inventory and accrual understated by 1500; adjust October receipt cut-off", "note", ""],
    ["P00010", 540, 600, 60, "vendor_overbilled", "stock.picking:11|account.move.line:10", "BILL/2026/10/0009 (vs receipt WH/IN/00010)", "Vendor billed 40 boxes but only 36 were received; no record justifies the extra 4 (answer changed 2026-11-12 from insufficient_evidence to reflect AP practice)", "Query vendor; request credit note or hold payment of the 60 difference", "structured", ""],
], folder="answer_key")

# ---- verification: recompute October figures per PO ----
po_name = {i: f"P{i:05d}" for i in range(1, 11)}
po_by_line = {l[0]: po_name[l[1]] for l in po_lines}
rec, ap = defaultdict(float), defaultdict(float)
for m in moves:
    if m[4].startswith("2026-10"):
        rec[po_by_line[m[2]]] += m[7]
for b in bills:
    if b[4].startswith("2026-10"):
        ap[b[7]] += b[9]
print(f"{'PO':8}{'receipt':>10}{'bill':>10}{'diff':>10}")
for po in sorted(po_name.values()):
    print(f"{po:8}{rec[po]:>10.0f}{ap[po]:>10.0f}{ap[po]-rec[po]:>10.0f}")
print(f"{'TOTAL':8}{sum(rec.values()):>10.0f}{sum(ap.values()):>10.0f}{sum(ap.values())-sum(rec.values()):>10.0f}")

with zipfile.ZipFile(f"data/{OUT}.zip", "w") as z:
    for f in sorted(os.listdir(DATA_DIR)):
        z.write(f"{DATA_DIR}/{f}", f"{OUT}/{f}")
print(sorted(os.listdir(DATA_DIR)))
