Hi!

The goal here is to build a bot capable of competently playing Slay the Spire 2,
currently in open access. I have a copy of the game avaialble on Steam myself,
and am moderately willing to sacrifice it (so to speak) as a testbed for this,

* Ideally I'd like to preserve my own personal gameplay profile for my own
play later.
* Note: the best streamers currently get >90% winrates on Ascension 10, the
hardest difficulty

Broadly speaking, this is intended both as a fun little "how good can this bot
get?" exercise, but also as a test/demonstration of Fable 5 (you)'s coding
project capabilities given a reasonable level of uncertainty and a decently
challenging problem.

* Feel free to do as much internet research/use as many pre-built libraries as
possible
* This is _not_ a "Fable 5" plays each turn of the game project, which I could
hardly afford anyway. Instead, standard code/determinism should be used as much
as is reasonable, with LLMs used judiciously to make judgments that are not
easily coded.
    * Admittedly, this is a bit vague, and you may ask me for clarification, but
    your own judgment shoudl be used a decent portion of the time. A usage
    counter would be nice though!
    * My own thought: An obvious use-case for the LLM is post-run, to consider
    the outcome of a given run and make tweaks, etc. as necessary. This could
    even be Fable 5 itself, if you think it's worth it.


Game notes/commentary:

The game is in early-access and hence changes get made frequently. Currently I
have the game set to the beta branch, which is subject to much more frequent
patches to individual cards, etc. You can make the choice to go to release
baranch if you like, but let me know because I have to change this on Steam
myself. Part of the challenge here will perhaps be adapting to card changes when
they happen.

The streamer jorbs has set up a website (spirebird.com) which contains a vast
trove of information about player runs, cards and ultimate results which can
be used to ptoentially infer card qualtiy, synergies etc. Feel free to use this
(or other sites you find) but be respectful to avoid spamming wbesites with bot
traffic. One-time downalods or occasional updates are perhaps the approach
here.

I do not believe the game currently has an API or easy way to play it for a bot.
The coding of it is relatively open and I've seen plenty of mods, so I _think_
this can be figured out, but just building this input-output component will be
a key challenge and may potentially even be infeasible if the game's designers
walled it off (though I do not believe so).

Approach to Ascensions/Characters:
---

Starting from a fresh account, it will be interesting to see the bot work its
way up to Ascension 10 on each character (Assuming it is good enough), though
the exact policy on whether it focuses on one character at a time, rotates, or
what is up to you. I do think of the tower climb as a deliverable (so to
speak) for this project.

* I'm not sure whether it is possible to start from a fresh account. I assume
yes, and I am willing to set that up (ideally with backup for my own existing
account)

Misc. QoL Features:

* It will be important for historical value (and post-run analysis etc) to keep
detailed logs of gameplay and outcomes
* Not strictly necessary initially but it would be nice to be able to watch the
bot play for my own interest, and also potential twitch streaming.
* For viewing purposes, it may also be useful to have a narration of why
individual decisions get made. (e.g. even if the decision is made
deterministically perhaps a cheap model like Haiku could narrate why. However I
coudl see this getting grating so this would be contingent on feel.)
* There is no git repo for this yet but I have no problem setting one up (probably
a good idea for code history purposes). Give the word and I'll put together a remote
and link it here.