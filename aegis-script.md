# AEGIS — Video Script (~5 min)

**Deck:** `aegis-deck.html`  
**Length:** 4–6 minutes. Talk over the slides. Don’t read the chips.  
**Voice:** like you’re telling another Hummingbot user how you got here. Simple. First person.

The story lives **in this video**, not on the deck. Slide 2 is just the timeline so people can follow along.

---

## Beat 1 — Cover (~35s)

**On screen:** the cover infographic. Point as you talk — left, center, right, then the bar at the bottom.

This is **AEGIS**. 
Defensive market making.

Aegis has 3 Jobs:

One — 
defend 
in the bear market.

When XRP is dumping, 
I want the dollar value of my XRP 
to hold up by automatic hedge 
or with short position.

Two — 
release 
in the bull market.

If XRP is pumping,
I still hold XRP. 
Short position will be closed. 

Three — 
always collect spread.
Bear or bull, 
I’m placing orders. 
Spread is the paycheck while I wait.

These are 
my 2 Objectives: 
keep the dollar value of my XRP. 
Grow my XRP stack.

---

## Beat 2 — How I got here (~70–80s) · §01 timeline  ← the heart

**On screen:** STARTED → DRAWDOWN → HEDGE → PROGRAM END → AEGIS  
Point at each node as you talk. Don’t rush.

Here is my story.

I started market making 
last year because of XRPLiquid. 
That was my first 
real Market Making journey. 

XRP was about three dollars forty. 

Weekly rewards was great 
and profitable.

But then the XRP price 
just kept falling.  

Even with the rewards, 
I still went negative for several times. 

I realized spreads and rewards 
don’t save me 
if the XRP itself 
is decreasing in value.

I kept seeing about
**hedging** 
in Discord 
and YouTube. 

So I tried hedging. 

But the old Hummingbot hedge 
did **not** work for me. 

This year I tried again 
with **Condor**. 

I told Condor to hedge. 

It eventually worked after few weeks. 
So that’s when 
AEGIS 
was born. 

Unfortunately, 
after a month or 2, 
XRPLiquid 
suddenly ended. 

I was really sad that time. 
The bonus was gone.

So AEGIS had to grow up. 

No more weekly paycheck. 

Now it has to defend 
the dollar value of my XRP, 

keep the stack if it moons, 
and earn spread the hard way.

It’s not easy money. 
I’m not going to pretend it is. 
But it feels promising. 

I still do pray 
that XRPLiquid 
will come back soon. 

Either way, 
Aegis and Condor 
will help me grow my XRP stack.

---

## Beat 3 — What it does now (~30s) · §02

**On screen:** two books → one pile → Gate short

Today, 
Aegis works like this.

I quote both 
at XRP-RLUSD and 
XRP-USDC pairs. 

Fills go into **XRP reserve**.

If that reserve becomes heavy, 
or XRP price is dumping, 
at Gate exchange, 
it opens a matching short. 
This is the shield.

The short is not me 
betting XRP goes down. 
This is so a crash 
will not decrease 
my XRP dollar value,
while I am still 
holding XRP.

---

## Beat 4 — Dump vs moon (~40s) · §03

**On screen:** BEAR / BULL boxes

If XRP dumps —
I leave the short on. 
I want the USD value 
of my XRP to survive.

If XRP really pumps, 
I will close my short position. 
I do **not** sell all the XRP. 
I wanted those coins. 
Now they can go to the moon.

---

## Beat 5 — Condor, not vibes (~30s) · §04

**On screen:** clerk pipe

This is how Aegis works 
with Condor Routines.

Every ten minutes, 
four scripts print a decision. 

1st: 
Health check for XRPL & Gate. 
2nd: 
Quote planner 
to determine fair value of XRP
3rd: 
Inventory of XRP
4th: 
Shield for both 
dump & pump scenarios

After cleared, 
then orders are placed.

---

## Beat 6 — The $800 (~30s) · §05

**On screen:** two wallets

This is how Builders Cup money 
of $800 is allocated.

$500 is on XRPL. 
$280 on XRP-RLUSD, 
$140 on XRP-USDC. 

$300 is on Gate
Its used only for the shield 
or short position. 

---

## Demo

Here is a short demo of Aegis
running in Condor.

We have Condor running in my laptop.

In Bots tab,
Aegis is running 
with pmm-simple controller
for both XRP pairs.

In Executors tab,
We have 1 open position 
in Gate perpetual
This is our shield.

We can see this short position 
in Gate website here.

For XRPL orders,
We can see those orders
in xmagnetic website.

And then for the Condor Routines.

Init, is part of health check.
It allows bot to start 
if verdict is go.

Venue Health checks for orderbooks,
here,
verdict is go. 
So bot started 
to place orders.

Next is Quote Planner.
This calculates order amounts 
and spreads

Next is Inventory.
It monitors the XRP balances.
It signals whether to hold or let go

And finally,
The shield.
This is the short position
in Gate perpetual.

That's how Aegis 
works in action.

## Beat 7 — Close (~20s) · §06

**On screen:** the three “how it pays” cards

As a summary, Aegis has 3 jobs:

1. Defend the coins in the bear market

2. Release them in the bull market

3. Collect spread the whole time.

Not easy profits.
Promising. 
That’s AEGIS, 
super powered by Condor & Hummingbot.

Thanks for watching.

---







## Timing

| Beat | ~s |
|---|---|
| 1 Cover | 35 |
| **2 Origin story** | **70–80** |
| 3 How it works | 30 |
| 4 Dump vs moon | 40 |
| 5 Clerks | 30 |
| 6 $800 | 30 |
| 7 Close | 20 |
| **Sum** | **~4:15–4:35** |

If you run long, shorten beat 5 and 6. **Never shorten beat 2.** That’s why someone remembers you.

---

## How to say it

- **Cover:** finger on 1 (bear), 2 (bull), 3 (spread), then the objectives bar. Don’t list pair names here — they aren’t on this graphic.  
- Talk like Discord, not like a spec. “It didn’t work for me” is better than “the legacy controller failed.”  
- Pause after “Then XRPLiquid ended.” Let that sit. A lot of XRPL people felt that.  
- Point at $3.4, then $1.01, then HEDGE, then PROGRAM END.  
- Don’t brag about the leaderboard — one quiet mention is enough (“I was up there for a while”). The struggle is the relatable part.  
- Don’t promise easy money. You already said it isn’t. End on *promising*.  
- Pair names later: **XRP-RLUSD**, **XRP-USDC**.
