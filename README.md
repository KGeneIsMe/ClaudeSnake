# ClaudeSnake

A classic Snake game written in Python with [pygame-ce](https://pyga.me/). Guide a rattlesnake around the board, eat rats to grow, and try to set a high score without hitting a wall or yourself.

## Features

- Snake with an animated head, flicking tongue and a rattlesnake tail that shakes when it eats
- Sound effects made in code, so there are no audio files: a beep and rattle when you eat, and a low pulse that speeds up as you do
- Speed increases as your score grows
- Top-10 high score table with three-letter initials, saved between sessions
- Sharp graphics: the window sizes itself to your screen, adapts to Windows display scaling and can be resized freely
- Cross-platform: runs anywhere pygame-ce does (Windows, macOS, Linux)

## Requirements

- Python 3.9 or newer
- [pygame-ce](https://pypi.org/project/pygame-ce/) 2.5.8, installed from `requirements.txt`

## Installation

```bash
git clone https://github.com/KGeneIsMe/ClaudeSnake.git
cd ClaudeSnake
python -m venv .venv
```

Activate the virtual environment:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

Then install the dependencies:

```bash
pip install -r requirements.txt
```

> **Note:** This project uses `pygame-ce` (Community Edition), not the original `pygame`. The two can't be installed side by side, so if `pygame` is already installed in your environment, uninstall it first.

## Running the game

```bash
python snake.py
```

## How to play

Steer the snake to eat the rats. Each rat adds one segment to the snake and one point to your score. The game ends when the snake runs into a wall or its own body.

### Controls

| Key | Action |
| --- | --- |
| `↑` `↓` `←` `→` | Change direction |
| `Space` | Start, pause / resume, play again after game over |
| `M` | Mute / unmute sound |
| `Esc` | Quit |

### Rules and tips

- **You can't reverse.** Pressing the direction opposite to the one you're moving in is ignored.
- **Quick turns are queued.** You can press two arrows in quick succession, for example `↑` then `←` to make a tight U-turn, and each turn is applied on its own move.
- **The snake speeds up.** It starts at 5 moves per second and gets 1 move per second faster for every 5 points, up to a maximum of 25.
- **Listen to the pulse.** The low pulse quickens with the snake's speed, so you can hear the game getting faster.
- **The score hides when you're under it.** The score and "Muted" labels disappear while the snake or a rat is underneath them, so they don't get in your way.

### High scores

If your score makes the top 10, you'll be asked for your initials:

- Type three letters (`A`–`Z`). `Backspace` corrects mistakes.
- Press `Enter` to save.

The leaderboard appears on the game-over screen, with your new entry marked by `>`.

Scores are saved to `high_scores.json` next to `snake.py`. The file is created automatically and isn't tracked by Git, so each player keeps their own scores. Delete it to reset the leaderboard.

## Running the tests

The game logic is covered by a `unittest` suite that runs without opening a window or playing sound:

```bash
python -m unittest -v
```

The tests never modify your real high score file.

## Project structure

```text
ClaudeSnake/
├── snake.py           # The game
├── test_snake.py      # Unit tests
├── requirements.txt   # Python dependencies
└── high_scores.json   # Your saved scores (created on first high score, not tracked)
```
