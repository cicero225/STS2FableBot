

Initial comments (random observations from before)
---

1. I have more than once since Anger drafted then played well after
any attacks. This is almost strictly suboptimal: The card gains defense for every
attack played after it is played.

2. Optimal potion usage is one of the hardest things in the game to figure out, and
honestly needs to be tailored potion by potion. The goal is roughly to maximize
the value gained by each potion, while trying not to accidentally receive
potions when already full on potions. Broadly speaking, there are five types of
potions:

    a. Immediate (or short-term) gain potions. The "value" of these potions can be
    derived on this specific turn. Here's some non-exhaustive ones I can think of
    off the bat as easy to handle:
        i. Block potion: blocks for 12. Essentially always correct to drink if you
    would otherwise take 12 or more damage. Reasonable if taking 10-11. Harder to
    judge below that. Fine to drink at end of turn after everything else
    resolves.
        ii. Fire potion: Deals 20 damage, ignores almost everything else. Almost
    always correct to play if doing so kills an enemy AND prevents >10 or so
    damage. Threshold is not exact. Check playing at the end of the turn.
        iii. Explosive Ampule: as above, but does 10 to all enemies. Check playing at
    the end of the turn.

    b. Long-term potions: The value is entire fight, and typically best saved for
    bosses/elites if possible:
        a. Strength potion
        b. Dex potion
        c. Fysh Oil

    These I would typically just go ahead and play immediately at the start of the
    Act 1 boss fight given the bot's currently difficulty with the fight. No need to
    get cute with trying to save them yet.

    c. Disguised long-term potions: Technically the effect is "one-turn" but really
    is or can easily become long-term:
        1. Power Potion
        2. Blessing of the Forge


    d. Usable immediately
        i. Blood potion:
        Heals 20% of max potion. Just drink this immediately if below 80% max hp.
        This can be slightly suboptimal, but the difference is too minor to bother.
        ii. Potion-shaped Rock: Approximately correct to just use it immediately at the
        start of every fight.
        iii. Fruit Juice: gain 5 Max Hp. Drink on the spot.

    e. Potion with potential downside to usage.
        i. Foul Potion.
        ii. Glowwater Potion


Also: Whenever the potion belt is full, there is a risk of receiving too many
potions. In that scenario, it is reasonable to deploy low-value potions for
somewhat lesser value, *especially* if facing a boss or elite.

We should probably fully reason out all the conditions for individual potions at
some point, but just fleshing out the easy cases will add decent value. Harder
cases can use simple fallback logic (drink to get rid of if potion belt full, or
in hail mary).

3. Demon Form.
Special case: This is legitimately one of the harder cards to understand how to
play. The ideal calculation is:

1. How many more turns will this probably save me this fight?
2. Will the amount of damage that saves me be worth the damage I take
*right now*?

A simplified algorithm might be:

1. Am I taking more than X damage this turn if I play Demon Form? If so, don't
play it. If not, play it.
    a. X is higher the higher the current enemy HP is, or if it is an Elite/Boss.



Run observations
---

Transform event (3): Transforming a curse is terrible value vs. transforming a strike. I know we haven't programmed events, but I'm noting everything.

Draft 2: I would have picked Hemokinesis over Shrug it Off, simply because there's a bias in early drafts for damage to get through early fights. 

Figfht 3+ These fights also contain chances to use Burning Pact to exhaust a damaging curse, which is an indirect defensive resource (and at one point, a defend is chosen to exhaust instead of Decay).

I wouldn't have drafted Rupture: This _can_ be a great card, but it falls into the class of cards that does nothing without specific other cards in the deck (bloodletting, for instance). In this case by chance there was Decay, which _can_ proc Rupture, but wouldn't be enough on its own.
- Potential suggestion: Figure out a list of cards that are not draftable without preconditions and write if-statements for those. This is definitely special casing, but I think is worthwhile. You can look through it yourself and pass any cases you are uncertain about by me?

Fight 4 + (roughly)
    a. There is the second order fact that the advantage of Rupture _can_ proc off of Decay but that would only matter in long fights, and Rupture never gets played.


Run 2 Observations:

Fight 1. Nearly a pure mathematical fight. Nothing to object to.

Draft 1: Would have taken Infernal Blade. We can consider examining this logic.

Fight 2. Straightforward.

Draft 2: Vicious is an ambitious draft with just Bash in deck. It is legitimately a very good card,
but True Grit was perhaps safer. Defensible in this case, but now should raise priority on future vulnerable applying cards. An eample of draft choices affecting other draft choices.

Fight 3: Was fine.

Draft 3: Pommel Strike is a perfectly sensible pick here.

Fight 4: Execution was sensible. Passed on playing Vicious a few times which was correct--it won't give enough value here.

Draft 4: Fiend Fire is the right pick.

Rest: is correct. I would rest here too.

Fight 5: Multiple opprtunities to play fiend fire were passed on. Notable is turn 1--it would have exhausted a handle of strikes, defends, and Vicious. Easily worth it for the 28 damage on a turn I think the enemy wasn't even attacking. An alternative is to play Vicious (1 energy) then Fiend Fire with 7 less damage. Vicious does have _some_ value (drawing 1 card when Bash is played) though it's unclear whether this will matter.

Also: A lot of effort is being spent on attacking the low-impact minion, which should honestly be ignored in this fight. Prioritizing minion over main enemy is hard, but for this specific
fight the minion is completely ignorable. (there are other fights where this problem crops up again, mainly in Act 2).

- This particular minion _also_ has the buff/status effect "Illusion", meaning it revives at the beginning of its turn after being killed (though without acting). This is particularly pernicious because it means
that the only reason to kill it on your turn (as opposed to on _its_ turn with poison or doom) is to negate its combat action, but otherwise not worth it.

Also, now stuck after drinking a Skill potion. I'm actually not sure why it was drunk tbh. Wouldn't fiend fire have been lethal on the 21 hp enemy? If not, the incoming 14 isn't even deadly after block is played. [We already discussed this at length]


