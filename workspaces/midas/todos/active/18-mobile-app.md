# M18 — Mobile App (Flutter)

**Spec anchors:** 09, 10.
**Framework:** Flutter + Riverpod.
**Depends on:** M17 (API contracts).

## T-18-01 — Flutter project scaffold + design system

**Objective:** Flutter app with bottom tab bar (Pulse / Decisions / Debate / Portfolio / More), dark-mode design tokens, tabular-figures for financial values.
**Acceptance:** builds iOS + Android.

## T-18-02 — Build Pulse (mobile, regime-adaptive)

**Objective:** mobile Pulse with band-adaptive reshape; kill-switch button always present.
**Acceptance:** playback renders bands.

## T-18-03 — Wire Pulse to Nexus API

**Objective:** live data via the same endpoints as web.

## T-18-04 — Build Decisions surface (mobile)

**Objective:** decision cards with top-of-fold; approve button biometric-gated; approve/reject spatially separated (T-00-08, `10-` §2).

## T-18-05 — Biometric gate integration

**Objective:** Face ID / fingerprint via platform channels; every high-stakes action calls it.
**Acceptance:** Tier 2 confirms biometric fails block the action.

## T-18-06 — Wire Decisions to backend

**Objective:** live decision events + approve/modify/reject path.

## T-18-07 — Build Debate (mobile bottom-sheet)

**Objective:** overlay from any screen; thread persistence; tool-action buttons render.

## T-18-08 — Wire Debate to agents + tools

**Objective:** same as web T-17-08.

## T-18-09 — Build Portfolio (mobile)

**Objective:** collapsed horizontal bars view; swipe-for-details.

## T-18-10 — Wire Portfolio (mobile)

## T-18-11 — Push notifications (tiered)

**Objective:** APNs (iOS) + FCM (Android) with tiers per `09- §7`; rich notification payloads; sound + haptic for Urgent.
**Acceptance:** test pushes render correctly.

## T-18-12 — Widgets (home screen)

**Objective:** small (NAV + regime dot), medium (+ pending), large (mini Pulse).
**Acceptance:** widgets render sample data.

## T-18-13 — Offline handling

**Objective:** last-known state with timestamp; decisions visible but not actionable.
**Acceptance:** airplane-mode test.

## T-18-14 — Kill-switch mobile affordance

**Objective:** one-tap access from Pulse header; biometric confirm; clears with T-00-09 process lock.
**Acceptance:** end-to-end trip + clear.

## T-18-15 — Paper-trading banner

**Objective:** unmissable banner across all screens when `state.paper_trading` is on.
**Acceptance:** visible on all screens.

**Gate out:** mobile app runs end-to-end, biometric on all high-stakes paths, notifications tiered correctly, widgets working.
