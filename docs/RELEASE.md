# Release Protocol

This document describes the release process for HedgeLock using four-digit semantic versioning (vW.X.Y.Z).

## Version Numbering

- **W (Major)**: Breaking changes that require user migration
- **X (Minor)**: Major new capabilities (strategic decision)
- **Y (Feature)**: New features and enhancements
- **Z (Patch)**: Bug fixes, performance improvements, documentation

## Automated Release Process

Use the release script to automate the entire process:

```bash
./scripts/release.sh <feature-branch-name>
```

The script will:
1. Merge the feature branch into main
2. Determine the new version based on commit messages
3. Update CHANGELOG.md and version files
4. Create a tagged release
5. Push to GitHub and create a release

## Manual Release Process

If you need to release manually, follow these steps:

### 1. Merge to Main

```bash
git checkout main
git pull origin main
git merge --no-ff --no-edit feature/your-feature
```

### 2. Determine New Version

Check commits since last release:
```bash
# Get latest tag
LATEST_TAG=$(git describe --tags --abbrev=0)

# View commits since last tag (non-interactive)
git log --oneline --no-pager "${LATEST_TAG}..HEAD"
```

Version bumping rules:
- `BREAKING CHANGE:` → Increment W, reset X.Y.Z to 0.0.0
- `feat:` → Increment Y, reset Z to 0
- `fix:`, `perf:`, `docs:` → Increment Z
- No conventional commits → Increment Z

### 3. Update Release Files

#### Update CHANGELOG.md
Add new version section at the top:
```markdown
## vW.X.Y.Z - YYYY-MM-DD

- feat(component): description (commit-hash)
- fix(component): description (commit-hash)
```

#### Update Version Files
- **pyproject.toml**: `version = "W.X.Y.Z"` (no 'v' prefix)
- **package.json**: `"version": "W.X.Y.Z"` (no 'v' prefix)

### 4. Commit and Tag

```bash
# Stage all changes
git add -A

# Commit release
git commit -m "chore(release): vW.X.Y.Z"

# Create annotated tag
git tag -a vW.X.Y.Z -m "Release vW.X.Y.Z"

# Push everything
git push origin main --tags
```

### 5. Create GitHub Release

```bash
gh release create vW.X.Y.Z \
    --title "Release vW.X.Y.Z" \
    --notes "## What's Changed
    
* feat: new feature description
* fix: bug fix description

**Full Changelog**: https://github.com/blackms/HedgeLock/compare/vW.X.Y.Z-1...vW.X.Y.Z"
```

## Commit Message Format

Follow conventional commits for automatic version detection:

```
type(scope): description

[optional body]

[optional footer(s)]
```

Types that affect versioning:
- `feat`: New feature (bumps Y)
- `fix`: Bug fix (bumps Z)
- `perf`: Performance improvement (bumps Z)
- `docs`: Documentation (bumps Z)
- `BREAKING CHANGE`: Breaking change (bumps W)

## Example Release Flow

Current version: `v1.2.5.3`

1. Feature branch has commits:
   - `feat(hedger): add stop-loss protection`
   - `fix(treasury): correct rounding error`

2. Run release:
   ```bash
   ./scripts/release.sh feature/stop-loss
   ```

3. Script determines: feat detected → `v1.2.6.0`

4. Automatically:
   - Merges branch
   - Updates CHANGELOG.md
   - Updates pyproject.toml
   - Commits as `chore(release): v1.2.6.0`
   - Tags as `v1.2.6.0`
   - Pushes and creates GitHub release

## Rollback Procedure

If a release needs to be rolled back:

```bash
# Delete local tag
git tag -d vW.X.Y.Z

# Delete remote tag
git push origin :refs/tags/vW.X.Y.Z

# Delete GitHub release
gh release delete vW.X.Y.Z

# Revert the release commit
git revert HEAD
git push origin main
```

## Best Practices

1. Always release from main branch
2. Ensure CI/CD passes before releasing
3. Review the changelog before committing
4. Test the release in staging first
5. Document any manual version bumps (X increments)