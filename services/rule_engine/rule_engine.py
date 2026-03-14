import yaml

with open("configs/rules.yaml", "r") as f:
    config = yaml.safe_load(f)

rules = config["rules"]


def evaluate_rules(event):

    violations = []

    for rule in rules:

        field = rule["field"]
        threshold = rule["threshold"]

        if event.get(field, 0) > threshold:
            violations.append(rule["name"])

    return violations