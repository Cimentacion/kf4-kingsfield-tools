# Changelog

## FIELDIV-ENGINE Alpha 0.1 (2026-10-26)

First public release.

### Map generator / King's Field port
- Ports King's Field levels into King's Field IV (PAL, SLES-50920), replacing map 099 (where New Game starts).
- Real King's Field geometry and textures, with collision built from the models themselves.
- King's Field decor objects imported from the original MO.T models: barrels, tables, tombs, lamps, the healing fountain.
- Secret walls use the original King's Field model: the floor and ceiling stay in the map, and the wall rises when you use it, with its own textures, so it blends in with the walls around it.
- Doors become a rising slab with the texture of the original King's Field door (no more KFIV portcullis).
- The fountain heals HP only, with KFIV's own fountain script and healing effect.
- Barrels can be broken.
- Torches and lamps add a soft warm light; the fountain room has a bluish tint.
- Enemy damage capped at about 10 per hit (for the ported map only).

### HUD and gameplay patch
- HP shown as a number inside the orb.
- Cross HUD: magic on top (icon, name and MP cost), consumable item at the bottom (icon and count).
- Weapon EXP bar and level on the equipment screen; weapons level up at 70 and 140 hits.
- Optional twin-stick controls.
- Starting gear can be chosen in `equipo_inicial.txt`.

### Standalone patch
- `PARCHE_HUD.bat`: applies the HUD and/or controls patch to anyone's own ISO, without the map generator.

### Known issues
- Secret walls and doors are new and have only been checked with offline renders: report anything that looks off.
- An enemy standing between you and an object takes the X button (the game's own priority).
