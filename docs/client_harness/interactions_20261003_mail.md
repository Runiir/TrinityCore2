# Player mail qualification, October 3

The isolated 4.4.2 lab now sends and returns a real player letter through ordinary
keyboard and mouse inputs. The successful `ui17/mail_return_04` trial makes 14
code-controlled choices across Harnessone and Harnesstwo. Native mail rows,
displayed sender/subject/body, one attached copper, 30-copper postage, return
delivery, collection and deletion agree. Both characters' complete original
mail, attachments, inventory, balances and positions are restored. The native
worldserver is unchanged; both owned clients remain on HDMI-1.

The separate `ui17/mail_reply_01` trial passes 17 code-controlled choices. It
verifies the stock Reply button's recipient and `RE:` subject, two real deliveries,
both displayed bodies and exact 30-copper postage on each send. Both disposable
letters are deleted and the complete original two-character baseline is restored.

New trials use the code controller under the updated AGENTS.md retirement of
Laya and Jev. Earlier failed trials retain their actual model identities.
These checks qualify client behavior and do not evaluate learned autonomy.

## Bridge changes

`CMSG_SEND_MAIL` and `CMSG_MAIL_RETURN_TO_SENDER` arrive on the modern Realm
channel. They require an authoritative created character and its active World
session, rather than requiring the request itself to arrive on World. Other mail
requests retain their World-channel requirement. Mailbox, sender, letter and
inventory provenance checks still apply. Native gameplay owns postage, balance,
delivery and item rules.

The stock recipient autocomplete displays the local realm suffix, while the
actual send packet contains the bare local name. The UI expectation reflects
this; the bridge does not strip names. Composition uses the stock anonymous body
EditBox and `MailEditBox:GetInputText()` for passive observation.

The modern client supports up to 16 attachments; the native server permits 12.
The bridge accepts valid modern counts so the native gameplay error can reach the
client for 13–16 attachments. This content difference still needs a live UI trial.

## Validation and preserved failures

The final regression suite passes 578 tests: 561 world/codec and 17 authentication
checks. The selected ASan/UBSan suite passes 114 tests. These counts measure
protocol regressions, not unique game features.

- The first compose probe incorrectly expected a nested compose frame in the
  top-level panel list. The corrected probe checks the observed compose fields.
- `mail_return_01` rejected the normal realm-qualified autocomplete value before
  sending. The UI oracle was corrected; no mail or postage was spent.
- `mail_return_02` exposed the Realm-channel send rejection. The native server
  received no send request and no resources changed.
- `mail_return_03` sent correctly, then exposed the same routing restriction for
  Return. Its disposable letter and postage were restored separately.
- The first restoration compared an inventory snapshot containing both actors'
  balances before restoring the second balance. The corrected restoration first
  restores both balances, then verifies every baseline. Both failure receipts remain.
- The first focused routing test used the mailbox DB spawn ID instead of its
  actual native runtime GUID and reported 23 passes and one failure. The captured
  packet fixture was corrected and the expanded final suite passes. The initial
  direct `pytest` invocation also failed import collection; the supported command
  is `python -m pytest` through pixi.

COD, text-copy, invoice/HTML, gems, attachment
limits, delayed delivery and negative gameplay paths remain open. Auction-house
qualification follows this batch; opening a panel alone does not qualify its
transactions. The broader 891-operation inventory remains a plan, not coverage.

## Reproduction

Initialize a new batch, then run trials serially. These points refer to reviewed
1280×720 views of the existing mailbox and must be rechecked after camera changes.

```bash
pixi run python -m tools.client_compatibility.checkpoint_interactions --initialize --directory ~/.local/share/trinity-client442-lab/evidence/<new-batch>
pixi run --manifest-path tools/client_compatibility/auth/pixi.toml python -m tools.client_compatibility.interaction_mail_roundtrip --output ~/.local/share/trinity-client442-lab/evidence/<new-batch>/mail_return_01 --mode return --controller code --primary-point 640 248 --scout-point 614 276
```

Use `--mode reply` for the separate reply trial. The runner creates uniquely tagged
owned letters, uses ordinary UI controls, and restores the full fixture. A closed
failed trial with a leftover owned letter can be restored through
`--restore-source <failed-trial>` into a new output directory without rewriting
the failed verdict. Inspect its cleanup result before starting another trial.

Commit code/configuration before checkpointing. Upload the closed batch through
DVC, verify the remote and file hashes, prune its PNGs, then evict only its named
archive/cache object. Preserve small receipts locally and avoid global DVC cache
collection; other worktrees share the cache.

Closed UI17 evidence is checkpointed as
[`442_interactions_20261003_18.tar.gz.dvc`](../../artifacts/client_harness/442_interactions_20261003_18.tar.gz.dvc).
It retains failures, restoration receipts, safe mail packet bodies, rendered-frame
reviews, build receipts and regression/sanitizer results.
