# Canonical Activity Naming Standard

## Purpose
Provide a single, provider-agnostic naming layer so a global search (e.g. “Virtual Machine Stopped”) returns matching activities across Azure, AWS, and GCP logs/metadata.

## Core Concepts

| Concept | Definition |
|--------|------------|
| CommonActivityName | Human-readable canonical string describing the object + action (and optional qualifiers). |
| CanonicalAction | Normalized past-tense action token. |
| ObjectType | Canonical object label (Virtual Machine, Disk, Snapshot, etc.). |
| Qualifiers | Optional disambiguators (Data, Admin, Billing Freed). |
| AggregationKey | Machine/grouping key (UPPER_SNAKE of CommonActivityName minus qualifiers). |
| Provider | Cloud provider source (Azure, AWS, GCP). |

## Construction
```
CommonActivityName = <ObjectType> <CanonicalAction>[ (<Qualifier1>[;Qualifier2...])]
AggregationKey = UPPER_SNAKE( CommonActivityName without parenthetical qualifiers )
```

Examples:
- `Virtual Machine Started` -> `VIRTUAL_MACHINE_STARTED`
- `Virtual Machine Stopped (Billing Freed)` -> `VIRTUAL_MACHINE_STOPPED`
- `Disk Temporary Access URL Granted (Data)` -> `DISK_TEMPORARY_ACCESS_URL_GRANTED`

## Object Normalization
Defined in `taxonomy/common_objects.yaml`. Each canonical object lists provider-specific aliases (case-insensitive substring match). If no alias matches, a fallback singular form of the source resource type is used.

## Action Normalization
Defined in `taxonomy/common_actions.yaml`. We match longest provider variant substring first. Fallback heuristics map verbs like `get/read/list` -> `Retrieved`, `create` -> `Created`, `delete` -> `Deleted`.

## Stop / Deallocate Policy
All provider stop-like events unify under `Stopped` with qualifiers distinguishing billing semantics:
- Azure `Deallocate` → `Stopped (Billing Freed)`
- Azure `Power Off` → `Stopped (Billing Continues)`
- AWS / GCP standard stop → `Stopped (Billing Freed)` (typical release of compute billing; adjust if provider nuance differs).
If you prefer explicit separate actions later, we can split them.

## Temporary Access URLs
Azure SAS, AWS Pre-signed URLs, GCP Signed URLs unify to:
- `Temporary Access URL Granted`
- `Temporary Access URL Revoked`
If provider specificity needed, add a qualifier such as `(SAS)` later.

## Data vs Control Plane
When `IsDataAction` (or equivalent) is TRUE, qualifier `Data` is appended to CommonActivityName.

## Qualifiers (Current Set)
- `Data`: Data-plane access.
- `Admin`: Administrative / elevated login.
- `Billing Freed` / `Billing Continues`: Stop state nuance.
- `All Disks`: Multi-disk reimage scope.

Avoid creating new qualifiers unless they influence security/billing semantics or materially change meaning.

## Dual Operations
Provider combined operations (e.g., “Create or Update”) retain combined form `Created or Updated`.
Likewise for “Approve or Reject” → `Approved or Rejected` if not split upstream.

## Files Generated
Running normalization produces canonical CSVs inside the `output/` directory:
- One `<original>_canonical.csv` per source CSV.
- A consolidated `all_providers_canonical.csv`.

New columns added: `CommonActivityName`, `CanonicalAction`, `ObjectType`, `Qualifiers`, `AggregationKey`, `Provider`.

## Lint / Consistency (Future Enhancements)
Potential additions:
- Detect unrecognized actions (flag to extend taxonomy).
- Detect multiple canonical names for same (object, action) pair across providers.
- Report unused taxonomy aliases.

## Extension Workflow
1. Add new aliases or actions to YAML taxonomy.
2. Re-run `scripts/run_normalization.py`.
3. Review diff in generated canonical CSVs.
4. Commit & open PR.

## Versioning
Maintain changes to taxonomy files in separate commits referencing reasoning (e.g., billing model change, new provider feature).

## Questions / Adjustments
Open an issue titled “Taxonomy Update: <short description>” for proposed vocabulary changes.
