#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# git-push.sh — Automated git commit & push for ERP Billing Engine
#
# Usage:
#   ./git-push.sh                        # auto-generates commit message
#   ./git-push.sh "your commit message"  # uses provided message
#   ./git-push.sh -b feature/my-branch   # push to a specific branch
#   ./git-push.sh --dry-run              # show what would happen, don't push
#
# Options:
#   -b, --branch <name>   Target branch (default: current branch)
#   -d, --dry-run         Show staged files and commit message, skip push
#   -h, --help            Show this help
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
RESET='\033[0m'

# ── Defaults ─────────────────────────────────────────────────────────────────
BRANCH=""
DRY_RUN=false
COMMIT_MSG=""

# ── Helpers ──────────────────────────────────────────────────────────────────
info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
die()     { error "$*"; exit 1; }

usage() {
    sed -n '/^# Usage:/,/^# ─/p' "$0" | sed 's/^# \?//'
    exit 0
}

# ── Auto-generate a smart commit message ─────────────────────────────────────
# Analyses the staged diff to produce a conventional-commit style message.
# Logic:
#   1. Collect all changed app directories (e.g. apps/billing, apps/accounts)
#   2. Detect the dominant change type from file status codes
#   3. Pick a conventional-commit prefix (feat/fix/refactor/chore/style/docs)
#   4. Build a concise summary line + optional body listing touched modules
generate_commit_msg() {
    local status_output
    status_output=$(git status --short)

    # ── Count status codes ────────────────────────────────────────────────────
    local added modified deleted renamed
    added=$(echo "$status_output"   | grep -c '^[A?]' || true)
    modified=$(echo "$status_output" | grep -c '^.M\|^M' || true)
    deleted=$(echo "$status_output"  | grep -c '^.D\|^D' || true)
    renamed=$(echo "$status_output"  | grep -c '^R' || true)

    # ── Collect touched apps/modules ─────────────────────────────────────────
    # Extract unique top-level app names from changed paths
    local touched_apps=()
    while IFS= read -r line; do
        # Strip status prefix (2 chars + space), grab the path
        local filepath="${line:3}"
        # Handle rename format "old -> new"
        filepath="${filepath## }"
        filepath="${filepath%% ->*}"

        # Derive module name: apps/<name>/... → <name>, else top-level dir
        if [[ "$filepath" == apps/* ]]; then
            local app
            app=$(echo "$filepath" | cut -d'/' -f2)
            touched_apps+=("$app")
        elif [[ "$filepath" == templates/* ]]; then
            touched_apps+=("templates")
        elif [[ "$filepath" == static/* ]]; then
            touched_apps+=("static")
        elif [[ "$filepath" == erp_billing_engine/* ]]; then
            touched_apps+=("config")
        fi
    done <<< "$status_output"

    # Deduplicate and sort
    local unique_apps
    unique_apps=$(printf '%s\n' "${touched_apps[@]}" | sort -u | tr '\n' ',' | sed 's/,$//')

    # ── Detect change type from file names ───────────────────────────────────
    local has_migration=false has_template=false has_model=false
    local has_view=false has_form=false has_signal=false
    local has_service=false has_test=false has_config=false
    local has_static=false has_url=false

    echo "$status_output" | awk '{print $2}' | while read -r f; do
        [[ "$f" == */migrations/* ]]  && echo "migration"
        [[ "$f" == */templates/* ]]   && echo "template"
        [[ "$f" == */models.py ]]     && echo "model"
        [[ "$f" == */views*.py ]]     && echo "view"
        [[ "$f" == */forms.py ]]      && echo "form"
        [[ "$f" == */signals.py ]]    && echo "signal"
        [[ "$f" == */services/* ]]    && echo "service"
        [[ "$f" == */tests/* || "$f" == *test*.py ]] && echo "test"
        [[ "$f" == erp_billing_engine/config/* || "$f" == */settings.py ]] && echo "config"
        [[ "$f" == static/* || "$f" == */static/* ]] && echo "static"
        [[ "$f" == */urls.py ]]       && echo "url"
    done > /tmp/_git_push_types.txt

    [[ -s /tmp/_git_push_types.txt ]] && {
        grep -q "migration" /tmp/_git_push_types.txt && has_migration=true
        grep -q "template"  /tmp/_git_push_types.txt && has_template=true
        grep -q "model"     /tmp/_git_push_types.txt && has_model=true
        grep -q "view"      /tmp/_git_push_types.txt && has_view=true
        grep -q "form"      /tmp/_git_push_types.txt && has_form=true
        grep -q "signal"    /tmp/_git_push_types.txt && has_signal=true
        grep -q "service"   /tmp/_git_push_types.txt && has_service=true
        grep -q "test"      /tmp/_git_push_types.txt && has_test=true
        grep -q "config"    /tmp/_git_push_types.txt && has_config=true
        grep -q "static"    /tmp/_git_push_types.txt && has_static=true
        grep -q "url"       /tmp/_git_push_types.txt && has_url=true
    }
    rm -f /tmp/_git_push_types.txt

    # ── Pick conventional-commit prefix ──────────────────────────────────────
    local prefix scope summary body_parts=()

    # Scope = first touched app (most significant)
    scope=$(echo "$unique_apps" | cut -d',' -f1)
    [[ -z "$scope" ]] && scope="core"

    # Determine prefix by priority
    if $has_test; then
        prefix="test"
    elif $has_config; then
        prefix="chore"
    elif $has_migration && $has_model; then
        prefix="feat"
    elif $has_migration && ! $has_model; then
        prefix="chore"
    elif $has_model && ($has_view || $has_service); then
        prefix="feat"
    elif $has_model; then
        prefix="feat"
    elif $has_view || $has_service || $has_form; then
        if [[ $modified -gt $added ]]; then
            prefix="fix"
        else
            prefix="feat"
        fi
    elif $has_template || $has_static; then
        prefix="style"
    elif $has_url; then
        prefix="refactor"
    elif [[ $deleted -gt 0 && $added -eq 0 ]]; then
        prefix="chore"
    else
        prefix="refactor"
    fi

    # ── Build summary line ────────────────────────────────────────────────────
    local total_files
    total_files=$(echo "$status_output" | wc -l | tr -d ' ')

    # Describe what changed
    local change_desc=""
    local parts=()
    $has_model    && parts+=("models")
    $has_view     && parts+=("views")
    $has_service  && parts+=("services")
    $has_form     && parts+=("forms")
    $has_template && parts+=("templates")
    $has_signal   && parts+=("signals")
    $has_url      && parts+=("urls")
    $has_migration && parts+=("migrations")
    $has_config   && parts+=("config")
    $has_static   && parts+=("static")

    if [[ ${#parts[@]} -gt 0 ]]; then
        change_desc=$(printf '%s, ' "${parts[@]}" | sed 's/, $//')
    else
        change_desc="miscellaneous files"
    fi

    # Scope label
    local scope_label=""
    if [[ -n "$unique_apps" ]]; then
        scope_label="(${unique_apps})"
    fi

    summary="${prefix}${scope_label}: update ${change_desc} — ${total_files} file(s) changed"

    # ── Build body ────────────────────────────────────────────────────────────
    local body=""
    [[ $added -gt 0 ]]    && body_parts+=("${added} added")
    [[ $modified -gt 0 ]] && body_parts+=("${modified} modified")
    [[ $deleted -gt 0 ]]  && body_parts+=("${deleted} deleted")
    [[ $renamed -gt 0 ]]  && body_parts+=("${renamed} renamed")

    if [[ ${#body_parts[@]} -gt 0 ]]; then
        body=$(printf '%s, ' "${body_parts[@]}" | sed 's/, $//')
        echo "${summary}

Changes: ${body}
Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
    else
        echo "${summary}

Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
    fi
}

# ── Argument parsing ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        -b|--branch)
            [[ -n "${2:-}" ]] || die "--branch requires a value"
            BRANCH="$2"; shift 2 ;;
        -d|--dry-run)
            DRY_RUN=true; shift ;;
        -h|--help)
            usage ;;
        -*)
            die "Unknown option: $1" ;;
        *)
            COMMIT_MSG="$1"; shift ;;
    esac
done

# ── Sanity checks ─────────────────────────────────────────────────────────────
command -v git >/dev/null 2>&1 || die "git is not installed or not in PATH"
git rev-parse --git-dir >/dev/null 2>&1 || die "Not inside a git repository"

# ── Resolve branch ────────────────────────────────────────────────────────────
CURRENT_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "HEAD")
[[ -z "$BRANCH" ]] && BRANCH="$CURRENT_BRANCH"

# Safety guard: never push directly to main/master unless explicitly confirmed
if [[ "$BRANCH" == "main" || "$BRANCH" == "master" ]]; then
    warn "You are about to push to ${BOLD}${BRANCH}${RESET}${YELLOW} (protected branch)."
    read -rp "$(echo -e "${YELLOW}Are you sure? [y/N]: ${RESET}")" confirm
    [[ "${confirm,,}" == "y" ]] || { info "Aborted."; exit 0; }
fi

# ── Check for changes ─────────────────────────────────────────────────────────
if git diff --quiet && git diff --cached --quiet; then
    if [[ -z "$(git ls-files --others --exclude-standard)" ]]; then
        warn "Nothing to commit — working tree is clean."
        exit 0
    fi
fi

# ── Show status summary ───────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}── Changed files ────────────────────────────────────────${RESET}"
git status --short
echo -e "${BOLD}─────────────────────────────────────────────────────────${RESET}"
echo ""

CHANGED_COUNT=$(git status --short | wc -l | tr -d ' ')
info "Total changed/untracked files: ${BOLD}${CHANGED_COUNT}${RESET}"
echo ""

# ── Commit message: auto-generate if not provided ────────────────────────────
if [[ -z "$COMMIT_MSG" ]]; then
    echo -e "${MAGENTA}[AUTO]${RESET}  Generating commit message from diff..."
    AUTO_MSG=$(generate_commit_msg)

    echo ""
    echo -e "${BOLD}── Suggested commit message ─────────────────────────────${RESET}"
    echo -e "${YELLOW}${AUTO_MSG}${RESET}"
    echo -e "${BOLD}─────────────────────────────────────────────────────────${RESET}"
    echo ""

    # Let the user accept, edit, or type their own
    echo -e "${CYAN}Options:${RESET}"
    echo -e "  ${BOLD}[Enter]${RESET}  Accept the suggested message"
    echo -e "  ${BOLD}[e]${RESET}      Edit it"
    echo -e "  ${BOLD}[m]${RESET}      Type a custom message"
    echo ""
    read -rp "$(echo -e "${CYAN}Choice [Enter/e/m]: ${RESET}")" choice

    case "${choice,,}" in
        e)
            # Open in $EDITOR (fallback to nano, then vi)
            EDITOR="${EDITOR:-$(command -v nano 2>/dev/null || echo vi)}"
            TMPFILE=$(mktemp /tmp/git_commit_msg.XXXXXX)
            echo "$AUTO_MSG" > "$TMPFILE"
            "$EDITOR" "$TMPFILE"
            COMMIT_MSG=$(cat "$TMPFILE")
            rm -f "$TMPFILE"
            ;;
        m)
            read -rp "$(echo -e "${CYAN}Enter commit message: ${RESET}")" COMMIT_MSG
            ;;
        *)
            COMMIT_MSG="$AUTO_MSG"
            ;;
    esac
fi

[[ -n "$COMMIT_MSG" ]] || die "Commit message cannot be empty"

# ── Dry run ───────────────────────────────────────────────────────────────────
if $DRY_RUN; then
    echo ""
    info "DRY RUN — no changes will be committed or pushed."
    info "Branch:  ${BOLD}${BRANCH}${RESET}"
    echo -e "${CYAN}[INFO]${RESET}  Message:"
    echo -e "${YELLOW}${COMMIT_MSG}${RESET}"
    exit 0
fi

# ── Stage all changes ─────────────────────────────────────────────────────────
info "Staging all changes..."
git add -A
success "All changes staged."

# ── Commit ────────────────────────────────────────────────────────────────────
info "Committing..."
git commit -m "$COMMIT_MSG"
success "Committed."

# ── Push ──────────────────────────────────────────────────────────────────────
if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
    info "Pushing to origin/${BRANCH}..."
    git push origin "$BRANCH"
else
    info "Branch '${BRANCH}' not found on remote — pushing and setting upstream..."
    git push -u origin "$BRANCH"
fi

echo ""
success "Done! Changes pushed to ${BOLD}origin/${BRANCH}${RESET}."
echo ""
