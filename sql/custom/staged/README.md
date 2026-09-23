# Staged SQL migrations

The world DB updater applies every file in `sql/custom/world/` when a
worldserver starts (`updates_include`: `$/sql/custom/world` RELEASED). A
tuning migration therefore stays here until its measurement batch: move it to
`sql/custom/world/` (or apply it with `mysql ... world < file`) right before
that batch, so it cannot leak into a baseline. Each file carries its reverse.
