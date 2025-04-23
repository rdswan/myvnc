# Disable Automatic Git Commands

Automatic git commits have been disabled in this repository using a pre-commit hook. This prevents accidental or automated commits without explicit permission.

## How It Works

A pre-commit hook has been installed that blocks commits unless the `ALLOW_AUTO_COMMIT` environment variable is set.

## Making Commits

To make a commit, you have two options:

1. **For one-time commits**, prefix your git command with the environment variable:
   ```
   ALLOW_AUTO_COMMIT=1 git commit -m "Your commit message"
   ```

2. **For a session with multiple commits**, set the environment variable for your shell session:
   ```
   export ALLOW_AUTO_COMMIT=1
   git commit -m "First commit message"
   git commit -m "Second commit message"
   ```

## Disabling This Feature

If you want to remove this protection:

```
rm .git/hooks/pre-commit
```
