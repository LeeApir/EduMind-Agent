# shared-learning-plan-v1

Runtime: `app.agents.shared_learning_plan.PLAN_INSTRUCTION`.

Generate only `plan_generation` fields from the supplied versioned node/reference and
learner evidence snapshot. The server supplies source identity, profile version (null
when unknown), goal, language and all digests, then validates the complete plan.
Unknown reference IDs, changed scene order, missing conventions and >8KiB plans fail.
The proposed example and trace are claims for later independent review.

One request, total output limit 2048, no transport retry or implicit fallback; it consumes
the same operation's 180-second / 20-call bound (22 only with the two optional stages).
The gateway remains responsible for pre-send persistent request/cost reservation.
Tests use only an injected synthetic gateway; no real quality claim is made.
