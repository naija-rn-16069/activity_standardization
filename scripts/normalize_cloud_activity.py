import pandas as pd
import yaml
import re
from pathlib import Path
from typing import Dict, Any, List

TAXON_OBJECTS = Path("taxonomy/common_objects.yaml")
TAXON_ACTIONS = Path("taxonomy/common_actions.yaml")

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

QUAL_DATA = "Data"
QUAL_ADMIN = "Admin"
QUAL_ALL_DISKS = "All Disks"
QUAL_BILLING_FREED = "Billing Freed"
QUAL_BILLING_CONTINUES = "Billing Continues"

STOP_FREED_SUBSTRINGS = {"deallocate", "stop instance", "stop instances", "stopped"}
STOP_CONTINUE_SUBSTRINGS = {"power off", "poweroff"}

COL_HINTS = {
    "operation": ["operation name", "operation", "action performed", "event", "action"],
    "resource_type": ["resource type", "resource", "resource_name", "resource category"],
    "service": ["service", "provider", "namespace"],
    "description": ["description", "details", "detail"],
    "is_data": ["isdataaction", "is_data_action", "is_data", "data action", "data_action"],
    "origin": ["origin", "source"],
}

def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())

def build_object_lookup(objects_yaml):
    lookup = {}
    for _, data in objects_yaml.items():
        label = data["canonical_label"]
        for provider, aliases in data.get("provider_aliases", {}).items():
            for alias in aliases:
                lookup[norm(alias)] = label
    return lookup

def build_action_variants(actions_yaml):
    variants = []
    for key, data in actions_yaml.items():
        label = data["label"]
        for variant in data.get("provider_variants", []):
            variants.append((norm(variant), key, label))
    variants.sort(key=lambda x: len(x[0]), reverse=True)
    return variants

def map_columns(df: pd.DataFrame):
    mapping = {}
    lower_map = {c.lower(): c for c in df.columns}
    for canonical, hints in COL_HINTS.items():
        for h in hints:
            if h in lower_map:
                mapping[canonical] = lower_map[h]
                break
    if "operation" not in mapping:
        raise ValueError("Could not identify operation column.")
    if "resource_type" not in mapping:
        mapping["resource_type"] = mapping["operation"]
    return mapping

def classify_object(resource_type: str, op_name: str, lookup) -> str:
    combo = f"{resource_type} {op_name}".lower()
    for alias, label in lookup.items():
        if alias in combo:
            return label
    rt = resource_type.strip()
    if rt.endswith("s") and len(rt) > 3:
        rt = rt[:-1]
    return rt or "Resource"

def classify_action(op_name: str, action_variants):
    low = norm(op_name)
    for phrase, key, label in action_variants:
        if phrase and phrase in low:
            return key, label
    if low.startswith("get") or low.startswith("read") or low.startswith("list") or " list" in low:
        return "retrieved", "Retrieved"
    if low.startswith("create"):
        return "created", "Created"
    if low.startswith("update"):
        return "updated", "Updated"
    if low.startswith("delete"):
        return "deleted", "Deleted"
    return "other", low.split(" ")[0].capitalize()

def derive_stop_qualifier(op_name: str) -> str:
    low = norm(op_name)
    for s in STOP_FREED_SUBSTRINGS:
        if s in low:
            return QUAL_BILLING_FREED
    for s in STOP_CONTINUE_SUBSTRINGS:
        if s in low:
            return QUAL_BILLING_CONTINUES
    return ""

def derive_qualifiers(row, action_key, op_name: str) -> str:
    q: List[str] = []
    if str(row.get("IsDataAction", row.get("is_data", ""))).upper() == "TRUE":
        q.append(QUAL_DATA)
    low = norm(op_name)
    if "admin" in low and "login" in low:
        q.append(QUAL_ADMIN)
    if "all disks" in low:
        q.append(QUAL_ALL_DISKS)
    if action_key == "stopped":
        stop_q = derive_stop_qualifier(op_name)
        if stop_q:
            q.append(stop_q)
    return ";".join(q) if q else ""

def build_common_name(obj_label: str, action_label: str, qualifiers: str) -> str:
    base = f"{obj_label} {action_label}"
    return base + (f" ({qualifiers})" if qualifiers else "")

def aggregation_key(common_name: str) -> str:
    base = re.sub(r"\s+\(.*\)$", "", common_name)
    base = base.replace(" or ", " OR ")
    base = re.sub(r"[^A-Za-z0-9 ]", "", base)
    return base.upper().replace(" ", "_")

def normalize_file(path: Path, provider: str, object_lookup, action_variants):
    df = pd.read_csv(path)
    mapping = map_columns(df)
    op_col = mapping["operation"]
    rt_col = mapping["resource_type"]

    common_names = []
    canon_actions = []
    object_types = []
    qualifiers = []
    agg_keys = []

    for _, row in df.iterrows():
        op_name = str(row[op_col])
        resource_type = str(row[rt_col])
        obj_label = classify_object(resource_type, op_name, object_lookup)
        action_key, action_label = classify_action(op_name, action_variants)
        qs = derive_qualifiers(row, action_key, op_name)
        common = build_common_name(obj_label, action_label, qs)
        agg = aggregation_key(common)
        common_names.append(common)
        canon_actions.append(action_label)
        object_types.append(obj_label)
        qualifiers.append(qs)
        agg_keys.append(agg)

    df["CommonActivityName"] = common_names
    df["CanonicalAction"] = canon_actions
    df["ObjectType"] = object_types
    df["Qualifiers"] = qualifiers
    df["AggregationKey"] = agg_keys
    df["Provider"] = provider.capitalize()

    out_path = OUTPUT_DIR / f"{path.stem}_canonical.csv"
    df.to_csv(out_path, index=False)
    return out_path, len(df)

def discover_provider(file_name: str) -> str:
    f = file_name.lower()
    if f.startswith("azure"):
        return "azure"
    if f.startswith("aws"):
        return "aws"
    if f.startswith("gcp"):
        return "gcp"
    return "generic"

def main():
    objects_yaml = load_yaml(TAXON_OBJECTS)
    actions_yaml = load_yaml(TAXON_ACTIONS)
    object_lookup = build_object_lookup(objects_yaml)
    action_variants = build_action_variants(actions_yaml)

    csv_files = [p for p in Path('.').glob('*.csv') if not p.name.endswith('_canonical.csv')]
    if not csv_files:
        print('No CSV files found.')
        return

    summary = []
    for csv_path in sorted(csv_files):
        provider = discover_provider(csv_path.name)
        try:
            out_path, count = normalize_file(csv_path, provider, object_lookup, action_variants)
            summary.append((csv_path.name, out_path.name, count))
            print(f"[OK] {csv_path.name} -> {out_path.name} ({count} rows)")
        except Exception as e:
            print(f"[FAIL] {csv_path.name}: {e}")

    combined_frames = []
    for _, out_name, _ in summary:
        df = pd.read_csv(OUTPUT_DIR / out_name)
        combined_frames.append(df)
    if combined_frames:
        combined = pd.concat(combined_frames, ignore_index=True)
        combined.to_csv(OUTPUT_DIR / 'all_providers_canonical.csv', index=False)
        print('Wrote output/all_providers_canonical.csv')

if __name__ == '__main__':
    main()