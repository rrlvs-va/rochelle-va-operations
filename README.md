# Rochelle V. Silvestre | Independent VA + Operations

This repository is the production source for Rochelle's standalone website.

## Deployment
Connect this repository to one Wasmer Edge app and use the `main` branch as the production branch.

Wasmer can auto-detect this as a static site because `index.html` is at the repository root.

## Update workflow
1. Edit `index.html`
2. Commit the change
3. Push to `main`
4. Wasmer deploys the updated production site

## Before going live
Replace `your-email@example.com` inside `index.html` with the preferred business email.
