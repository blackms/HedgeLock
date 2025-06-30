#!/bin/bash
set -euo pipefail

# Release Protocol Script for HedgeLock
# Uses vW.X.Y.Z versioning scheme

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
log() {
    echo -e "${GREEN}[RELEASE]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
    exit 1
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if feature branch is provided
if [ $# -eq 0 ]; then
    error "Usage: $0 <feature-branch-name>"
fi

FEATURE_BRANCH=$1

# 1. Merge to Main
log "Step 1: Merging feature branch to main"
git checkout main || error "Failed to checkout main"
git pull origin main || error "Failed to pull main"
git merge --no-ff --no-edit "$FEATURE_BRANCH" || error "Failed to merge $FEATURE_BRANCH"

# 2. Determine New Version
log "Step 2: Determining new version"

# Get the latest tag
LATEST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0.0")
log "Current version: $LATEST_TAG"

# Parse current version
if [[ $LATEST_TAG =~ ^v([0-9]+)\.([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
    W=${BASH_REMATCH[1]}
    X=${BASH_REMATCH[2]}
    Y=${BASH_REMATCH[3]}
    Z=${BASH_REMATCH[4]}
else
    warn "Could not parse version from tag: $LATEST_TAG"
    W=0; X=1; Y=0; Z=0
fi

# Get commits since last tag (non-interactive)
COMMITS=$(git --no-pager log --oneline "${LATEST_TAG}..HEAD" 2>/dev/null || git --no-pager log --oneline)

# Determine version bump
HAS_BREAKING=false
HAS_FEAT=false
HAS_FIX=false

while IFS= read -r commit; do
    if [[ $commit == *"BREAKING CHANGE:"* ]]; then
        HAS_BREAKING=true
    elif [[ $commit == *"feat("* ]] || [[ $commit == *"feat:"* ]]; then
        HAS_FEAT=true
    elif [[ $commit == *"fix("* ]] || [[ $commit == *"fix:"* ]] || \
         [[ $commit == *"perf("* ]] || [[ $commit == *"perf:"* ]] || \
         [[ $commit == *"docs("* ]] || [[ $commit == *"docs:"* ]]; then
        HAS_FIX=true
    fi
done <<< "$COMMITS"

# Apply version bump
if [ "$HAS_BREAKING" = true ]; then
    ((W++))
    X=0; Y=0; Z=0
    log "Breaking change detected - major version bump"
elif [ "$HAS_FEAT" = true ]; then
    ((Y++))
    Z=0
    log "Feature detected - feature version bump"
elif [ "$HAS_FIX" = true ]; then
    ((Z++))
    log "Fix/perf/docs detected - patch version bump"
else
    ((Z++))
    log "No conventional commits found - patch version bump"
fi

NEW_VERSION="v${W}.${X}.${Y}.${Z}"
log "New version: $NEW_VERSION"

# 3. Update Release Files
log "Step 3: Updating release files"

# Generate changelog
CHANGELOG_ENTRY="## ${NEW_VERSION} - $(date +%Y-%m-%d)\n\n"
CHANGELOG_ENTRY+=$(git --no-pager log --pretty=format:"- %s (%h)" "${LATEST_TAG}..HEAD" 2>/dev/null || git --no-pager log --pretty=format:"- %s (%h)" --max-count=10)
CHANGELOG_ENTRY+="\n\n"

# Update CHANGELOG.md
if [ -f CHANGELOG.md ]; then
    # Create temp file with new entry
    echo -e "$CHANGELOG_ENTRY" > CHANGELOG.tmp
    cat CHANGELOG.md >> CHANGELOG.tmp
    mv CHANGELOG.tmp CHANGELOG.md
    log "Updated CHANGELOG.md"
else
    # Create new CHANGELOG.md
    echo "# Changelog" > CHANGELOG.md
    echo "" >> CHANGELOG.md
    echo -e "$CHANGELOG_ENTRY" >> CHANGELOG.md
    log "Created CHANGELOG.md"
fi

# Update version in pyproject.toml
if [ -f pyproject.toml ]; then
    # Remove 'v' prefix for pyproject.toml
    VERSION_NUMBER="${W}.${X}.${Y}.${Z}"
    sed -i "s/^version = \".*\"/version = \"$VERSION_NUMBER\"/" pyproject.toml
    log "Updated version in pyproject.toml to $VERSION_NUMBER"
fi

# Update version in package.json if it exists
if [ -f package.json ]; then
    VERSION_NUMBER="${W}.${X}.${Y}.${Z}"
    sed -i "s/\"version\": \".*\"/\"version\": \"$VERSION_NUMBER\"/" package.json
    log "Updated version in package.json to $VERSION_NUMBER"
fi

# 4. Commit, Tag, and Release
log "Step 4: Committing, tagging, and releasing"

# Stage all changes
git add -A

# Commit with release message
git commit -m "chore(release): ${NEW_VERSION}" --no-edit || error "Failed to commit release"

# Create annotated tag
git tag -a "${NEW_VERSION}" -m "Release ${NEW_VERSION}" || error "Failed to create tag"

# Push to remote
git push origin main --tags || error "Failed to push to remote"

# 5. Create GitHub release using gh CLI
log "Step 5: Creating GitHub release"

# Generate release notes
RELEASE_NOTES="## What's Changed\n\n"
RELEASE_NOTES+=$(git --no-pager log --pretty=format:"* %s by @%an" "${LATEST_TAG}..${NEW_VERSION}" 2>/dev/null || echo "* Initial release")

# Create the release
gh release create "${NEW_VERSION}" \
    --title "Release ${NEW_VERSION}" \
    --notes "$(echo -e "$RELEASE_NOTES")" \
    --target main || warn "Failed to create GitHub release (gh CLI might not be configured)"

log "✅ Release ${NEW_VERSION} completed successfully!"
log "View the release at: https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/releases/tag/${NEW_VERSION}"