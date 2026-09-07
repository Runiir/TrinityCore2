# Worker task packet

Give the worker one self-contained packet. Link only the few files needed to
understand it; do not substitute a dump of the program charter or old handoffs.

1. **Outcome.** What should change for the bot, boss, or controller?
2. **Evidence.** Exact source and compact observed counterexample. Label the
   cause as established or suspected; distinguish it from the terminal symptom.
3. **Production path.** Relevant caller -> state owner -> candidate/executor ->
   outcome, including the identity and lifecycle rules involved. Explain why the
   present behavior is wrong and which old expectations must change.
4. **Scope.** Owned production files AND directly affected callers/tests.
   Read-only inspection is allowed. List concrete forbidden changes. Tell the
   coordinator if a necessary edit falls outside ownership; do not silently
   expand production scope.
5. **Proof.** A behavioral failure before the patch and expected result after it;
   one focused command covering affected tests. State what the test does not
   prove, especially native terrain, actual encounter fidelity, or live success.
6. **Return.** Changed files, cause/fix, executed tests, remaining uncertainty,
   and whether review/build/live validation is still needed.

Before dispatch, the coordinator checks that the packet includes the relevant
callers, lifecycle boundary and duplicate/legacy test expectations. Include the
small concrete examples, not just filenames. Do not assign Luna a causal guess
as an exact implementation task. Resolve ambiguity locally or with Sol first.
Search for sibling candidates and fallback calls that can mutate the same target
or movement state; reading only the named candidate is not a complete caller check.
For optional targets or assignments, include the case where selection succeeds
but execution becomes ineligible. Specify the ordinary fallback and incompatible
assignments that must remain excluded; test both through the production caller.

Workers implement the bounded hypothesis and correct implementation/test errors
within that scope until the focused checks pass. A disproven hypothesis means
return the contradictory evidence; it does not mean invent a broader repair.
No nested agents, live server actions, provisioning, builds, DVC mutation, or
artifact deletion unless explicitly assigned. Preserve pre-existing user edits.

Preserve the typed arbiter, native movement safety, and ownership of effects.
Deferred callbacks must own captured values or reference state that outlives
resolution. Keep stable identity separate from transient alive/summoned/combat
state. Observation paths must not silently normalize provisioned identity.

Tests should execute the production behavior affected by the hypothesis. Use a
small dependency stub where it makes a lifecycle transition deterministic, and
say what is stubbed. Real terrain/spell/encounter fidelity still needs matched
live evidence. A source-shape assertion or fabricated successful outcome cannot
prove that the boss died or a native movement completed.

Independent review checks the cause, preserved invariants, affected callers,
and actual test boundary together. The coordinator resumes the next action
after review; a worker handoff is not a request for the user to say continue.
