# CRITICAL: No Onboarding Frontend

**Date:** 2026-04-22
**Round:** Round 10 red team
**Severity:** CRITICAL

## Finding

Backend `OnboardingRouter` exists (4-step state machine with proper sequencing gates) but no frontend wizard to drive it. New users land in a shell with a sidebar pointing to surfaces they cannot populate.

## Impact

A Singapore investor who just downloaded the app sees "No positions" and "No pending decisions" with no path to set up their brokerage connection, risk profile, or paper trading account.

## Spec Coverage

- Spec 02 (Value Chain): Front office onboarding surface promised
- Spec 09 (Surfaces): Onboarding wizard in 7 surfaces

## Resolution Path

Build frontend onboarding wizard that:

1. Drives the OnboardingRouter state machine
2. Collects: brokerage credentials, risk profile, paper trading setup
3. Wires into the regime-adaptive shell

## Status

OPEN — requires frontend implementation
