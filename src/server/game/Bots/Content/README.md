# Bot content ownership

Raid and dungeon-specific bot code belongs to an instance-owned section:

```text
Content/Raids/<Raid>/{Instance,Trash/<WingOrPack>,Encounters/<Boss>}/...
Content/Dungeons/<Dungeon>/{Instance,Trash/<WingOrPack>,Encounters/<Boss>}/...
```

`Instance` contains instance-wide code. `Trash` and `Encounters` always name a
second owner directory for the wing/pack or boss. Do not place C++ or header
files directly under an instance root, `Trash`, or `Encounters`; do not add
other section names. A `Shared` directory may appear only at the category
level (for example `Content/Raids/Shared`) so reusable code is not mistaken
for ownership by one instance.

The `Bots/` root remains the home of generic runtime and manager glue. Moving
that code into content ownership folders is a separate refactor and is not
required by this layout contract.
