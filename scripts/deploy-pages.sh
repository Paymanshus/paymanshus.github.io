#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: deploy-pages.sh -m "commit message" [options]

Options:
  -m, --message MESSAGE   Commit message for the deployment commit.
  -r, --repo PATH         Target clone of paymanshus.github.io.
                           Default: <master-dir>/deployed
  -s, --source PATH       Source project directory to sync.
                           Default: parent directory of this script
      --skip-build        Skip npm build before syncing.
  -h, --help              Show this help message.
EOF
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$1" >&2
    exit 1
  fi
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TARGET_REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)/deployed"
COMMIT_MESSAGE=""
SKIP_BUILD=0
NO_PUSH=0

while (($# > 0)); do
  case "$1" in
    -m|--message)
      COMMIT_MESSAGE="${2:-}"
      shift 2
      ;;
    -r|--repo)
      TARGET_REPO_DIR="${2:-}"
      shift 2
      ;;
    -s|--source)
      SOURCE_DIR="${2:-}"
      shift 2
      ;;
    --skip-build)
      SKIP_BUILD=1
      shift
      ;;
    --no-push)
      NO_PUSH=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$COMMIT_MESSAGE" ]]; then
  printf 'A commit message is required.\n\n' >&2
  usage >&2
  exit 1
fi

require_command git
require_command npm
require_command rsync

if ! git -C "$TARGET_REPO_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  printf 'Target path is not a git repository: %s\n' "$TARGET_REPO_DIR" >&2
  exit 1
fi

TARGET_BRANCH="$(git -C "$TARGET_REPO_DIR" branch --show-current)"
if [[ "$TARGET_BRANCH" != "main" ]]; then
  printf 'Target repo must be on main, found: %s\n' "$TARGET_BRANCH" >&2
  exit 1
fi

if [[ -n "$(git -C "$TARGET_REPO_DIR" status --porcelain)" ]]; then
  printf 'Target repo has uncommitted changes: %s\n' "$TARGET_REPO_DIR" >&2
  exit 1
fi

printf 'Fast-forwarding target repo from origin/main\n'
git -C "$TARGET_REPO_DIR" pull --ff-only origin main

if ((SKIP_BUILD == 0)); then
  printf 'Building source app in %s\n' "$SOURCE_DIR"
  (
    cd "$SOURCE_DIR"
    npm run clean >/dev/null 2>&1 || true
    npm run build
  )
else
  printf 'Skipping local build, refreshing generated SEO files in %s\n' "$SOURCE_DIR"
  (
    cd "$SOURCE_DIR"
    npm run generate:seo
  )
fi

RSYNC_EXCLUDES=(
  --exclude='.git'
  --exclude='node_modules'
  --exclude='.next'
  --exclude='out'
  --exclude='tsconfig.tsbuildinfo'
  --exclude='.env.local'
  --exclude='.env.*.local'
  --exclude='deployed'
  --exclude='stitch_assets'
  --exclude='paymanshu-sharma-portfolio.zip'
  --exclude='metadata.json'
  --exclude='LICENSE'
  --exclude='scripts'
  # ── Private planning/docs — never publish (owner request) ──
  --exclude='readmes'
  --exclude='left.md'
  --exclude='promptlatest.md'
  --exclude='docs'
  --exclude='AGENTS.md'
  --exclude='CLAUDE.md'
  --exclude='.claude'
  --exclude='Setup.sh'
  --exclude='HYGIENE_REPORT.md'
  # ── Local runtime junk ──
  --exclude='.venv'
  --exclude='__pycache__'
  --exclude='.pytest_cache'
  --exclude='nohup.out'
  --exclude='tests/voicetest-*'
)

# Paths that must not exist in the public repo even if previously committed.
PRIVATE_PATHS=(readmes left.md promptlatest.md docs AGENTS.md CLAUDE.md .claude Setup.sh)

printf 'Syncing %s -> %s\n' "$SOURCE_DIR" "$TARGET_REPO_DIR"
rsync -a --delete "${RSYNC_EXCLUDES[@]}" "$SOURCE_DIR/" "$TARGET_REPO_DIR/"

printf 'Purging private paths from target repo\n'
for p in "${PRIVATE_PATHS[@]}"; do
  rm -rf "${TARGET_REPO_DIR:?}/$p"
done

if [[ -z "$(git -C "$TARGET_REPO_DIR" status --porcelain)" ]]; then
  printf 'No changes to deploy.\n'
  exit 0
fi

printf 'Committing deployment changes\n'
git -C "$TARGET_REPO_DIR" add -A
git -C "$TARGET_REPO_DIR" commit -m "$COMMIT_MESSAGE"

if ((NO_PUSH == 1)); then
  printf 'Committed locally (--no-push). Review with: git -C %s show --stat\n' "$TARGET_REPO_DIR"
  exit 0
fi

printf 'Pushing to origin/main\n'
git -C "$TARGET_REPO_DIR" push origin main
