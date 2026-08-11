---
name: verify
summary: Drive TrinityCore bot rotation changes through the live worldserver CLI.
---

# Verify TrinityCore bot runtime changes

For rotation snapshot changes, build the server and drive the public Pixi CLI against the test worldserver configuration:

```bash
cmake --build build --target worldserver -j2
out=$(mktemp -d /tmp/trinity-rotation-verify.XXXXXX)
pixi run bot-phase4-rotation-contract \
  --output-dir "$out" \
  --worldserver-conf trinity-worldserver-test.conf \
  --worldserver-binary build/src/server/worldserver/worldserver
```

Read `$out/contract.json` for the observed catalog count, rejected invalid reload, unchanged active generation/hash, monotonic valid reload and rollback, alias dump, and post-start database checks. Run the CLI a second time when verifying mutation restoration and idempotence: the second baseline must still report 31 profiles, 260 actions, and no unknown categories.

The launcher uses `stdbuf` because worldserver stdout is block-buffered when attached to a pipe; waiting for the `ready...` log without it times out even though startup completed.
