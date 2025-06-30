# Codecov Setup Guide

This guide explains how to set up Codecov for the HedgeLock project to enable code coverage reporting.

## Why Codecov?

Codecov provides:
- Visual coverage reports
- PR coverage checks
- Coverage trend analysis
- Badge for README

## Setup Steps

### 1. Create Codecov Account

1. Go to [codecov.io](https://codecov.io)
2. Sign in with GitHub
3. Authorize Codecov to access your repositories

### 2. Add Repository

1. In Codecov dashboard, click "Add a repository"
2. Find and select `blackms/HedgeLock`
3. Copy the repository upload token

### 3. Add Token to GitHub Secrets

1. Go to your GitHub repository settings
2. Navigate to Settings → Secrets and variables → Actions
3. Click "New repository secret"
4. Add secret:
   - Name: `CODECOV_TOKEN`
   - Value: Your Codecov upload token

### 4. Update Badge (Optional)

Add the coverage badge to your README:

```markdown
[![codecov](https://codecov.io/gh/blackms/HedgeLock/branch/main/graph/badge.svg?token=YOUR_TOKEN)](https://codecov.io/gh/blackms/HedgeLock)
```

## CI/CD Configuration

The GitHub Actions workflow is already configured to use Codecov. Once you add the token, coverage reports will be automatically uploaded on each push.

The relevant configuration in `.github/workflows/ci.yml`:

```yaml
- name: Upload coverage to Codecov
  uses: codecov/codecov-action@v3
  with:
    file: ./coverage.xml
    fail_ci_if_error: true
    token: ${{ secrets.CODECOV_TOKEN }}
```

## Troubleshooting

### Rate Limit Errors

If you see "Rate limit reached" errors, ensure:
1. The `CODECOV_TOKEN` secret is properly set
2. The token is valid and not expired
3. The repository is activated in Codecov

### Missing Coverage

If coverage reports are missing:
1. Check that tests are running successfully
2. Verify `pytest-cov` is generating `coverage.xml`
3. Ensure the file path in the workflow is correct

## Local Testing

To generate coverage reports locally:

```bash
# Run tests with coverage
make test-cov

# View HTML report
open htmlcov/index.html
```

## Coverage Goals

Recommended coverage targets:
- Overall: 80%+
- New code: 90%+
- Critical paths: 95%+

Configure these in Codecov's project settings.