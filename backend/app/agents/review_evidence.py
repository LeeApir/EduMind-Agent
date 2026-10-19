"""Versioned evidence-strength and citation rules shared by prompt and policy."""

REVIEW_PROMPT_VERSION = "evidence-resource-review-v4.6"

EVIDENCE_INSTRUCTION = """\
Bound every conclusion to the strength and scope of its evidence. Separate a demonstrated
error or contradiction, an absent guarantee, and insufficient evidence. From "P is not
guaranteed" do not infer "not P". For undefined behavior, report the concrete reachable
unsafe operation and that no particular numerical result or normal return is guaranteed;
never infer a fixed result, a guaranteed different result, a guaranteed crash, or other
specific runtime outcome. A demonstrated serious safety defect still requires rejection:
uncertainty about its runtime outcome does not make the unsafe operation itself uncertain.
With genuinely insufficient premises, identify the missing support in unresolved instead
of inventing a fact contradiction. Independently inspect every finding and every assertion
inside condition_or_counterexample and impact; one valid defect does not excuse another
unsupported assertion. Keep the current severity definitions, scope, and verdict contract.

Check every cited anchor against its exact resource, digest, JSON pointer and UTF-8 span.
Use only server-supplied anchor IDs and metadata; do not calculate or invent hashes,
offsets, or substitute locations. For each claim in a finding, determine internally which
anchor locates the statement being
audited and which supplies supporting or counterexample evidence. Every listed anchor must
make a specific evidentiary contribution to that finding; field relevance, a valid ID, or
proximity to another claim is insufficient. A valid primary anchor cannot compensate for
an unrelated secondary citation. A citation supports only propositions contained in its
actual anchored content; never
borrow content from adjacent fields. Derived conclusions must follow from the cited
premises; do not attribute a computed result verbatim to a field that does not contain it.
Cite the actual source for a code-result inference. Remove
irrelevant proposed citations before returning your own newly generated review, but never
rewrite stored reviews, discard real defects, or claim certainty when necessary support is
missing. If a required claim cannot be supported by the supplied anchors/evidence, state the
exact limitation in unresolved; preserve a separately justified serious reject. This is an
internal checking procedure, not a request for extra output fields or a chain of thought.

Return only the existing schema object: schema_version, scope, verdict, findings, coverage,
and unresolved. unresolved and coverage.unchecked remain arrays of strings. Do not add an
explanation, reasoning, evidence map, confidence score, new category, or new protocol field.
These rules apply to new findings in both resource and unit scope, across topics and values;
they do not replace the original goal coverage, fact, safety or mandatory-check obligations.
"""
