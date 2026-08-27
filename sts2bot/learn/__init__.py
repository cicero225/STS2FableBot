"""Learning-direction (PLAN §9) training-time modules.

Feature extraction and tiny dependency-free model baselines live here —
deliberately OUTSIDE sts2bot/policy/ (policies stay pure functions with no
model state until a trained evaluator is explicitly wired in at stage 1+).
"""
