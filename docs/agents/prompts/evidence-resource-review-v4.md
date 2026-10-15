# evidence-resource-review-v4

Runtime instructions: `app.agents.hybrid_resource_review.INSTRUCTION`. Protocol is
resource-review-v4, explicitly separate from legacy v3. Each finding selects server
anchor IDs and identifies its actual condition/counterexample and consequence.
Categories follow actual impact; unused includes/style and hypothetical deletion of
existing guards do not establish defects. Coverage and unresolved facts are explicit.
The proposed plan is a claim, not independent evidence; full reference context is sent.
Missing references, incomplete coverage or recognized empty evidence route to human.

The stored model result remains unchanged; local_routing separately records disposition.
Schema/anchor/call/budget faults fail, actual reject cannot be human-approved. Revise
allows two full resource corrections and re-reviews, then needs_human. Historical
candidate bodies remain available for audit. Every call uses the same operation bound.

`TransportAudit` carries exact request/response body digests from the adapter and a
non-secret configuration digest. New review rejects missing transport audit; it never
substitutes a reserialized result for the actual response bytes. DeepSeek support is
covered with mock HTTP bytes; other adapters retain legacy behavior until they expose
this capability. No raw reasoning, authorization headers or Provider keys are persisted.
