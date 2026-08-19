# Bot content ownership

Raid and dungeon behavior is owned by the smallest content unit that can use it.
Use the same layout for both content types:

```text
Content/Raids/<Raid>/Instance/<module>
Content/Raids/<Raid>/Trash/<WingOrPack>/<module>
Content/Raids/<Raid>/Encounters/<Boss>/<module>

Content/Dungeons/<Dungeon>/Instance/<module>
Content/Dungeons/<Dungeon>/Trash/<WingOrPack>/<module>
Content/Dungeons/<Dungeon>/Encounters/<Boss>/<module>
```

`Instance` owns route-wide state and transitions. `Trash/<WingOrPack>` owns one
named trash unit. `Encounters/<Boss>` owns one boss encounter. Do not place C++
or headers directly at an instance root or directly in `Trash` or `Encounters`.
Do not create placeholder modules for content that has not been implemented.

Code that is truly reusable across instances may live below
`Content/Raids/Shared` or `Content/Dungeons/Shared`. Shared code must not contain
instance, wing, pack, or boss-specific behavior. The bot brain selects an
intent; reusable movement and native action executors carry it out.
