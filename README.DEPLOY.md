## Deployment Process Guide

### Introduction

This document outlines our standardized deployment process to ensure smooth, reliable releases. Following these procedures helps maintain consistency across environments and minimizes deployment-related issues.

### Pre-Deployment Checklist

### 1. Requirements Management

    - Always update `requirements.production.txt` with current package versions
    - Verify all dependencies work correctly in your local development environment before updating production requirements
    - Use: `pip freeze > requirements.production.txt` (after testing locally)

### 2. Branch Policy
    - Only create deployment tags from the main branch
    - Ensure `main` branch is stable and all tests pass before tagging


## Tagging Convention

### Version Format: V<MAJOR>.<MINOR>.<PATCH>

    - Major (V1.0.0): Breaking changes
    - Minor (V1.1.0): New features (backwards compatible)
    - Patch (V1.0.1): Bug fixes

```bash
    # List existing tags
    git tag --list

    # Create new tag (from main branch)
    git tag V1.0.1 -m "Description of changes"

    # Push tag to remote
    git push origin V1.0.1

    # View tag details
    git show V1.0.1
```
> **Important:** Always verify the next version number follows semantic versioning rules before tagging.

## 🔁 Rollback Procedure

If any issues arise after deployment, follow these steps to safely revert to a stable version:

1. **Access cPanel**
   - Go to the **Python App** section.
   - Open the associated **Virtual Environment Terminal**.

2. **Checkout Stable Git Tag**
   - Run the following command:
     ```bash
     git checkout V1.0.1
     ```

3. **Restart the Application**
   - Return to the **Python App** page.
   - Click **Restart** or **Reload** to apply the changes.

   tag local clear
   git tag -l | xargs git tag -d

## Delete local tags.
```bash
git tag -d $(git tag -l)
```
## Fetch remote tags.
```bash
git fetch
```
## Delete remote tags.
```bash
git push origin --delete $(git tag -l) 
```
- Pushing once should be faster than multiple times

## Delete local tags.
```bash
git tag -d $(git tag -l)
```

   