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
```
git clone --depth 1 https://github.com/Gennadiyev/STS2MCP external/STS2MCP
git -C external/STS2MCP apply ../../patches/STS2MCP-newbuild-fix.patch
dotnet build external/STS2MCP/STS2_MCP.csproj -c Release -p:STS2GameDir="<game dir>"
# deploy bin/Release/net9.0/STS2_MCP.dll -> "<game dir>/mods/STS2_MCP.dll"
```
The fix is already built + deployed; this patch is for reproducibility. Consider upstreaming it to
`Gennadiyev/STS2MCP` (it's not specific to our fork).
