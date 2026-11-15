"""Score a findings file (from rules or from the LLM agent) against the answer key.

Usage:  python evaluate.py results/rules_findings.csv
        python evaluate.py results/llm_findings_v6_run1.csv results/llm_worksheet_v6_run1.csv   # also checks worksheet arithmetic
        python evaluate.py --runs results/llm_findings_v6      # summary across results/llm_findings_v6_run1.csv, _run2.csv, ...
        python evaluate.py --runs results/agent_findings_v8
        python evaluate.py --test --runs results/test_llm_findings_v6   # held-out test set (uses the test answer key)
        python evaluate.py --test results/test_rules_findings.csv
For each PO it checks:
  - cause_ok:     a finding for this PO has the expected cause_category
  - location_ok:  that same finding points at an accepted problem_key
  - extra:        findings beyond the one the PO needs (false alarms and repeats):
                  every finding that points at a record other than the accepted problem_key(s), plus
                  every additional finding on the accepted record(s) - one problem = one finding
A PO whose expected cause_category is "none" should get NO finding: it is right only if nothing was
reported, and every finding on it counts as extra. Findings on PO numbers that are not in the answer
key also count as extra.
A failed run (the agent ended without accepted findings and left an empty findings file) scores
every PO as wrong, including the POs that expect no finding.

Scoring change 2026-11-14: repeats on the accepted record, findings on unknown POs and the failed-run
rule above were added (before, a repeated finding on the right record was not counted, and an empty
file scored the "none" POs as right).
"""
import csv, glob, os, re, sys
from collections import defaultdict

# Always work inside this script's own folder, wherever it is run from
os.chdir(os.path.dirname(os.path.abspath(__file__)))

KEY = "answer_key/expected_findings.csv"
if "--test" in sys.argv:
    KEY = "answer_key/test_expected_findings.csv"
    sys.argv.remove("--test")


def norm(key):
    """'account_move_line:1' and 'account.move.line:1' mean the same record."""
    table, _, rid = key.strip().partition(":")
    return table.replace("_", ".") + ":" + rid.strip()


def read_findings(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def is_failed_run(path):
    """agent.py saves a run that ended without accepted findings as an empty findings file."""
    return not read_findings(path)


def unknown_po_findings(findings_path):
    """Findings on PO numbers that are not in the answer key (they count as extra)."""
    expected = {r["po"] for r in csv.DictReader(open(KEY, encoding="utf-8"))}
    return [f for f in read_findings(findings_path) if f["po"] not in expected]


def score(findings_path):
    """Per-PO results for one findings file."""
    expected = {r["po"]: r for r in csv.DictReader(open(KEY, encoding="utf-8"))}
    findings = read_findings(findings_path)
    failed = not findings
    found = defaultdict(list)
    for r in findings:
        found[r["po"]].append(r)

    rows, n_cause, n_loc, n_extra = [], 0, 0, 0
    for po, exp in expected.items():
        keys = [norm(k) for k in exp["problem_keys"].split("|") if k.strip()]
        fs = found.get(po, [])
        if failed:                                   # no accepted findings at all: every PO is wrong
            cause_ok = loc_ok = False
            extra = 0
        elif exp["cause_category"] == "none":        # nothing should be reported on this PO
            cause_ok = loc_ok = not fs
            extra = len(fs)
        else:
            cause_ok = any(f["cause_category"] == exp["cause_category"] for f in fs)
            loc_ok = any(f["cause_category"] == exp["cause_category"] and norm(f["problem_key"]) in keys for f in fs)
            off_key = sum(1 for f in fs if norm(f["problem_key"]) not in keys)
            on_key = len(fs) - off_key
            extra = off_key + max(on_key - 1, 0)    # one problem = one finding: repeats count as extra
        got = "; ".join(f"{f['cause_category']} @ {f['problem_key']}" for f in fs) or "(no finding)"
        n_cause += cause_ok; n_loc += loc_ok; n_extra += extra
        rows.append((po, exp["key_evidence"], exp["cause_category"], got,
                     "Y" if cause_ok else "N", "Y" if loc_ok else "N", extra))
    n_extra += len(unknown_po_findings(findings_path))
    return rows, n_cause, n_loc, n_extra


def main(findings_path):
    rows, n_cause, n_loc, n_extra = score(findings_path)
    n = len(rows)
    print(f"{'PO':7} {'evidence':10} {'expected':22} {'cause':5} {'loc':4} {'extra':5} got")
    for po, ev, ec, got, c, l, x in rows:
        print(f"{po:7} {ev:10} {ec:22} {c:5} {l:4} {x:<5} {got}")
    if is_failed_run(findings_path):
        print("\nFAILED RUN (no findings submitted): every PO scored as wrong")
    for f in unknown_po_findings(findings_path):
        print(f"Finding on a PO not in the answer key (counted as extra): {f['po']} {f['cause_category']} @ {f['problem_key']}")
    print(f"\nCause correct:     {n_cause}/{n}")
    print(f"Cause + location:  {n_loc}/{n}")
    print(f"Extra findings:    {n_extra}")
    for ev in ("structured", "note", "none", "normal"):
        sub = [r for r in rows if r[1] == ev]
        if sub:
            print(f"  key_evidence={ev:10}: cause correct {sum(r[4] == 'Y' for r in sub)}/{len(sub)}")


def worksheet_ok(path):
    """{po: True/False} - are the LLM's own October totals all correct?"""
    expected = {r["po"]: r for r in csv.DictReader(open(KEY, encoding="utf-8"))}
    res = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        exp = expected[r["po"]]
        res[r["po"]] = all(abs(float(r[a]) - float(exp[b])) < 0.01 for a, b in [
            ("period_receipt_value", "oct_receipt_value"), ("period_bill_value", "oct_bill_value"),
            ("difference_bill_minus_receipt", "difference_bill_minus_receipt")])
    return res


def summarize_runs(prefix):
    """One table across all runs: which POs are always right, always wrong, or unstable."""
    files = sorted(glob.glob(f"{prefix}_run*.csv"), key=lambda f: int(re.search(r"_run(\d+)\.csv$", f).group(1)))
    if not files:
        print(f"No files matching {prefix}_run*.csv"); return
    results = [score(f) for f in files]
    n_runs = len(files)
    print(f"{n_runs} runs: " + ", ".join(files))
    print(f"\n{'PO':7} {'evidence':10} {'expected':22} {'cause per run':>14} {'cause+loc':>10}  verdict")
    rows0 = results[0][0]
    for i, (po, ev, ec, *_rest) in enumerate(rows0):
        causes = "".join(r[0][i][4] for r in results)
        locs = "".join(r[0][i][5] for r in results)
        verdict = "always right" if set(causes) == {"Y"} else "always wrong" if set(causes) == {"N"} else "UNSTABLE"
        print(f"{po:7} {ev:10} {ec:22} {' '.join(causes):>14} {' '.join(locs):>10}  {verdict}")
        if verdict != "always right":
            for k, r in enumerate(results, 1):
                print(f"{'':42}run {k}: {r[0][i][3]}")
    print(f"\n{'':7} {'run':>4} {'cause':>6} {'cause+loc':>10} {'extra':>6}")
    for k, (rows, c, l, x) in enumerate(results, 1):
        failed = is_failed_run(files[k - 1])
        print(f"{'':7} {k:>4} {c:>4}/10 {l:>8}/10 {x:>6}" + ("   <- failed run (no findings submitted)" if failed else ""))
    mean = lambda j: sum(r[j] for r in results) / n_runs
    print(f"{'':7} {'mean':>4} {mean(1):>7.1f} {mean(2):>10.1f} {mean(3):>6.1f}")

    ws_files = [f.replace("findings", "worksheet") for f in files]
    if all(os.path.exists(f) for f in ws_files) and "findings" in prefix:
        oks = [worksheet_ok(f) for f in ws_files]
        print("\nWorksheet arithmetic, POs with all totals correct: "
              + ", ".join(f"run {k}: {sum(o.values())}/10" for k, o in enumerate(oks, 1)))


def check_worksheet(path):
    """Compare the LLM's own October totals per PO with the true figures."""
    expected = {r["po"]: r for r in csv.DictReader(open(KEY, encoding="utf-8"))}
    ok_all = 0
    print(f"\nWorksheet arithmetic (LLM's own totals vs true figures):")
    print(f"{'PO':7} {'receipt (llm/true)':>20} {'bill (llm/true)':>18} {'diff (llm/true)':>18}  ok")
    for r in csv.DictReader(open(path, encoding="utf-8")):
        exp = expected[r["po"]]
        pairs = [(float(r["period_receipt_value"]), float(exp["oct_receipt_value"])),
                 (float(r["period_bill_value"]), float(exp["oct_bill_value"])),
                 (float(r["difference_bill_minus_receipt"]), float(exp["difference_bill_minus_receipt"]))]
        ok = all(abs(a - b) < 0.01 for a, b in pairs)
        ok_all += ok
        print(f"{r['po']:7} " + " ".join(f"{f'{a:g}/{b:g}':>19}" for a, b in pairs) + f"  {'Y' if ok else 'N'}")
    print(f"POs with all three totals correct: {ok_all}/{len(expected)}")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--runs":
        summarize_runs(sys.argv[2])
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else "results/rules_findings.csv")
        if len(sys.argv) > 2:
            check_worksheet(sys.argv[2])
