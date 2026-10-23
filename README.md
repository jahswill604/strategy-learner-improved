# Strategy Learner

Teach an AI model your forex strategy in plain words, test it, correct it, and then let it watch the market and send you signals for **your own** strategy.

You don't need to be technical. You explain things the way you would to a friend, and send screenshots.

## How it works

1. **Teach.** You explain your strategy. The AI behaves like a curious student:
   - It asks about every term you use ("what is a key level?", "what is an FVG?") until it can say it back in simple words.
   - For every concept, however small, it asks for one **valid** screenshot and one **invalid** screenshot, and why.
   - It asks what makes a concept stop being valid, what looks similar but doesn't count, and how it can fail.
   - Then it thinks like a trader afraid of losing: "how could I lose on this?" and logs when **not** to trade.
   - It explains each concept back to you. A concept only counts as **learned** when you said "yes, that's right".
2. **Test.** Give it a chart it has never seen. It labels everything it learned, with a reason for each label.
3. **Correct.** Tell it what's wrong in plain words. It saves the chart as a new example, updates its understanding, and labels the same chart again to prove it learned.
4. **Ready.** Once every concept is learned and has been right often enough on new charts, the strategy is marked **ready**.
5. **Signals.** The AI scans live FX charts and sends you a signal (entry, stop, targets, which of your rules matched, a chart image) when your setup appears. It also tells you what is missing when something is close.

The AI model is **not retrained**. Everything it learns is saved as plain files in `strategies/`, and the model reads those files every time it works. So you can switch to a different model at any time and lose nothing.

## The /trade skill: every concept becomes its own small skill

Teaching can also happen inside Claude itself, with no API key. Copy `skills/trade` into `.claude/skills/` (or `~/.claude/skills/`) and type `/trade`. Claude then plays the student, and the repo's commands save what it learns.

Each time a concept is confirmed by the trader, the repo builds:

- **one small skill per concept** (definition, valid and invalid pictures, what invalidates it, look-alikes, how it fails)
- **one strategy skill** (rules, no-trade rules, and the list of concept skills)

The strategy skill tells the AI to read **every** concept skill before it looks at a chart or makes any decision, and to ask instead of guessing when it meets a term with no skill. Put the generated skills where Claude loads them with:

```bash
python -m strategy_learner build-skills ada/candle-range --out .claude/skills
```

## Setup

```bash
pip install -e ".[anthropic,data]"      # or .[openai,data]
cp config.example.yaml config.yaml      # then edit it
export ANTHROPIC_API_KEY=...            # whichever model you chose
```

Any model that can read images works: Claude, GPT, Gemini (through its OpenAI-compatible endpoint), or a local vision model. Change it in `config.yaml`.

## Using it

Strategies are named `trader/strategy-name`, for example `ada/candle-range`.

```bash
python -m strategy_learner teach ada/candle-range
```

Just talk. When the AI asks for a picture, send it with:

```
/valid  C:\charts\fvg_good.png   price left a gap and came back to it, nothing closed through it
/invalid C:\charts\fvg_bad.png   this gap was already filled by the next candle
```

You can leave any time with `/quit` and resume later; it remembers everything.

```bash
python -m strategy_learner test ada/candle-range new_chart.png     # label, correct, repeat
python -m strategy_learner status ada/candle-range                 # what is learned, accuracy per concept
python -m strategy_learner scan ada/candle-range                   # one scan of the market
python -m strategy_learner watch ada/candle-range                  # scan every 15 minutes
```

Signals go to your terminal, or to Telegram if you set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

## What gets saved

```
strategies/ada/candle-range/
  strategy.json      summary, rules, no-trade rules, open questions, status
  concepts.json      every concept: definition, what invalidates it, how it fails
  examples/          your valid and invalid screenshots, plus corrected test charts
  examples.json      why each example is valid or invalid
  chat.jsonl         the whole teaching conversation
  scores.json        accuracy per concept on test charts
  corrections.jsonl  every correction you made
  signals.jsonl      every scan result
```

You can read and edit these by hand, and commit them to GitHub.

## Honest limits

- It sends **signals only**. It does not place trades.
- Models can misread charts. That is why every concept needs your confirmation, and why the AI is also given exact prices as text (previous day high/low, recent candles) when scanning.
- Parts of a strategy that are pure gut feel are logged as **judgment calls** and flagged in signals for you to check, not turned into invented rules.
- The "ready" label means it has been accurate on your test charts. It does **not** mean the strategy is profitable. This tool has no backtester yet, and nothing here is financial advice.
- Free data (yfinance) is slightly delayed and has limited history on lower timeframes. Use a broker or paid data feed for faster signals.
- Each scan sends several chart images to the model, which costs API credits. Lower the number of pairs or timeframes, or scan less often, to spend less.

## Tests

```bash
pip install -e ".[dev]" && pytest
```
