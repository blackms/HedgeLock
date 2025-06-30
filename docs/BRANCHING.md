# HedgeLock Git Branching Model

## Branch Types

### Main Branches
- **main**: Production-ready code. Only accepts merge requests from release branches.
- **develop**: Integration branch for features. All feature branches merge here.

### Supporting Branches

#### Feature Branches
- **Naming**: `feature/HL-XX-Y-description`
- **Created from**: `develop`
- **Merge back to**: `develop`
- **Example**: `feature/HL-01-1-loan-monitoring`

#### Release Branches
- **Naming**: `release/sprint-X`
- **Created from**: `develop`
- **Merge to**: `main` and `develop`
- **Purpose**: Prepare for production release

#### Hotfix Branches
- **Naming**: `hotfix/HL-XX-Y-description`
- **Created from**: `main`
- **Merge to**: `main` and `develop`
- **Purpose**: Critical production fixes

## Workflow

1. Create feature branch from `develop`
2. Work on feature with atomic commits
3. Create PR to merge back to `develop`
4. At sprint end, create `release/sprint-X` from `develop`
5. After testing, merge release to `main` and tag
6. Merge release back to `develop`

## Protection Rules

- **main**: Requires PR approval, no direct pushes
- **develop**: Requires PR approval for merges
- All PRs must pass CI/CD checks before merge