"""
Bring the deployed rule engine in line with Appendix B of the report.

PROBLEM
    Report Section 3.3 and Appendix B: "an event is flagged when delay >= 30
    minutes or retry count >= 3."

    Artefact as shipped:
      configs/rules.yaml            HIGH_RETRY threshold: 5
      services/rule_engine/...py    comparison uses > (strictly greater)

    So the deployed rule was "delay > 30 or retry > 5". The evaluation harness
    (evaluation/run_experiment.py) uses >= with thresholds 30 and 3 and is
    correct, so no reported number is affected. Only the demonstrator differed.

FIX
    rules.yaml   HIGH_RETRY threshold 5 -> 3
    rule_engine  >  ->  >=

    After this the deployed detection layer matches the documented and
    evaluated configuration exactly.

Run from the repo root:
    python fix_artefact_report_mismatch.py
"""

import sys
from pathlib import Path

YAML = Path("configs/rules.yaml")
ENGINE = Path("services/rule_engine/rule_engine.py")


def main():
    if not YAML.exists() or not ENGINE.exists():
        sys.exit("Run this from the repo root (the folder containing configs/ and services/).")

    y = YAML.read_text()
    if "name: HIGH_RETRY" not in y:
        sys.exit("HIGH_RETRY rule not found in configs/rules.yaml")

    # only touch the threshold that belongs to HIGH_RETRY
    lines = y.splitlines(keepends=True)
    out, in_high_retry, changed_yaml = [], False, False
    for line in lines:
        if "name: HIGH_RETRY" in line:
            in_high_retry = True
        elif line.lstrip().startswith("- name:"):
            in_high_retry = False
        if in_high_retry and line.lstrip().startswith("threshold:"):
            if "3" in line.split(":")[1]:
                print("  rules.yaml: HIGH_RETRY already 3, leaving alone")
            else:
                indent = line[: len(line) - len(line.lstrip())]
                line = f"{indent}threshold: 3\n"
                changed_yaml = True
        out.append(line)
    if changed_yaml:
        YAML.write_text("".join(out))
        print("  rules.yaml: HIGH_RETRY threshold 5 -> 3")

    e = ENGINE.read_text()
    old = 'if event.get(field, 0) > threshold:'
    new = ('# Inclusive comparison, matching Section 3.3 and the evaluation\n'
           '        # harness: an event is flagged at the threshold, not above it.\n'
           '        if event.get(field, 0) >= threshold:')
    if 'field, 0) >= threshold' in e:
        print("  rule_engine.py: already inclusive, leaving alone")
    elif old not in e:
        sys.exit("  rule_engine.py: comparison line not found, check manually")
    else:
        ENGINE.write_text(e.replace(old, new, 1))
        print("  rule_engine.py: > -> >=")

    print("\nDeployed rule is now: delay >= 30 OR retry >= 3")
    print("This matches Section 3.3, Appendix B and evaluation/run_experiment.py.")
    print("\nExpect the demo to flag slightly more events than before. That is the")
    print("documented behaviour; the previous settings were the undocumented ones.")


if __name__ == "__main__":
    main()
