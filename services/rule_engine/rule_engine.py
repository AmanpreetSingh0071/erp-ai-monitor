import yaml
import os

# -------------------------
# Resolve absolute path to configs/rules.yaml
# -------------------------
BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

rules_path = os.path.join(BASE_DIR, "configs", "rules.yaml")

print("📄 Rules path:", rules_path)
print("Exists:", os.path.exists(rules_path))

# -------------------------
# Load rules safely
# -------------------------
if not os.path.exists(rules_path):
    raise FileNotFoundError(f"rules.yaml not found at {rules_path}")

with open(rules_path, "r") as f:
    config = yaml.safe_load(f)

rules = config.get("rules", [])


# -------------------------
# Rule Evaluation
# -------------------------
def evaluate_rules(event):

    violations = []

    for rule in rules:
        field = rule["field"]
        threshold = rule["threshold"]

        if event.get(field, 0) > threshold:
            violations.append(rule["name"])

    return violations