# Mod patches

`external/STS2MCP/` is a **gitignored reference clone** (re-cloned on demand), so fixes made there
don't live in this repo. Patches that we need to survive a re-clone are saved here.

## STS2MCP-newbuild-fix.patch

The StS2 game auto-updated (~2026-06-23) and broke the deployed mod (`MissingMethodException` reading
combat state). Three game-API drifts, fixed against the new `sts2.dll`:

1. **`CombatManager.IsPlayPhase` removed** — phase is now per-player on `PlayerCombatState.Phase`
   (enum `PlayerTurnPhase.Play`). Added a `PlayerInPlayPhase(Player?)` helper; the 7 call sites now
   pass the local player (`LocalContext.GetMe(runState)` in the state builders).
2. **`Creature.CombatState` now returns `ICombatState`** (was `CombatState`) — widened
   `ResolveTarget`'s parameter to `ICombatState` (it only uses `GetCreature` / `Enemies`, both on the
   interface).
3. **`MerchantRoom.Inventory` removed** — the game added multi-inventory support; use
   `MerchantRoom.GetLocalInventory()`.

### Apply after a re-clone
Clone **our fork** (`cicero225/STS2MCP`), not upstream — upstream lacks the `deck`/`set_time_scale`/
`set_ascension`/`actions_disabled` commits the bot needs. (Rebuilding from upstream on 2026-06-23
silently dropped `player.deck`, no-op'ing drafting + the elite gate for a whole batch.)
```
git clone https://github.com/cicero225/STS2MCP external/STS2MCP
git -C external/STS2MCP apply ../../patches/STS2MCP-newbuild-fix.patch
external/STS2MCP/build.ps1 -GameDir "I:\SteamLibrary\steamapps\common\Slay the Spire 2"
# deploy: out/STS2_MCP/STS2_MCP.dll -> "<game dir>/mods/STS2_MCP.dll"
#         mod_manifest.json        -> "<game dir>/mods/STS2_MCP.json"
```
The patch applies cleanly except `McpMod.StateBuilder.cs` (one conflict at `is_play_phase`: keep the
`PlayerInPlayPhase(...)` fix **and** the fork's `actions_disabled` lines). Consider upstreaming the
v0.107.1 API fixes to `Gennadiyev/STS2MCP` (they're not fork-specific).
