# Conventional Commits Guidelines

## Commit Message Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

## Types

- **feat**: New feature (correlates with MINOR in SemVer)
- **fix**: Bug fix (correlates with PATCH in SemVer)
- **docs**: Documentation only changes
- **style**: Code style changes (formatting, semicolons, etc)
- **refactor**: Code refactoring without feature/fix
- **perf**: Performance improvements
- **test**: Adding or updating tests
- **build**: Changes to build system or dependencies
- **ci**: CI/CD configuration changes
- **chore**: Other changes that don't modify src or test files

## Scope

Reference the story ID from sprint planning:
- Example: `feat(HL-01-1): implement loan monitoring endpoint`

## Subject

- Use imperative mood: "add" not "adds" or "added"
- Don't capitalize first letter
- No period at the end
- Max 50 characters

## Body

- Use to explain **what** and **why** vs. **how**
- Wrap at 72 characters
- Reference story details and acceptance criteria

## Footer

- Reference issues: `Refs: HL-01-1`
- Breaking changes: Start with `BREAKING CHANGE:`

## Examples

```
feat(HL-01-1): add loan health monitoring endpoint

Implement REST endpoint to retrieve current loan health metrics
including LTV ratio, collateral value, and liquidation risk score.

Refs: HL-01-1
```

```
fix(HL-02-3): correct margin calculation in volatile markets

The previous implementation didn't account for rapid price movements
within the calculation window, leading to incorrect margin requirements.

BREAKING CHANGE: margin calculation now requires volatility parameter
Refs: HL-02-3
```