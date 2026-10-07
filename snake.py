import json
import math
import os
import random
import sys
from array import array
from enum import Enum, auto

import pygame

# The game is designed on a 600x400 logical board. Layout scales it to the real window, so CELL_SIZE and the
# pixel sizes below (fonts, margins) only set proportions, not the final on-screen size.
CELL_SIZE = 10
GRID_WIDTH = 60
GRID_HEIGHT = 40
WINDOW_WIDTH = CELL_SIZE * GRID_WIDTH
WINDOW_HEIGHT = CELL_SIZE * GRID_HEIGHT
# Snake speed in moves per second. The FPS names date from when the whole loop ran at the snake's speed.
BASE_FPS = 5
MAX_FPS = 25
FPS_STEP = 1
# Speed up every few points so difficulty ramps gradually instead of with every rat.
SCORE_STEP = 5
# Enough to buffer quick combos like a U-turn, but small enough that mashing keys doesn't keep steering the
# snake long after the player stops.
MAX_QUEUED_TURNS = 3
# Leave room for taskbars, docks and window borders.
SCREEN_FILL = 0.8
# Redraw much faster than the snake moves so animations and input stay smooth at low speeds.
RENDER_FPS = 60
FONT_SIZE = 24
SMALL_FONT_SIZE = 20

# Sounds are synthesized at startup so the game needs no audio files.
SAMPLE_RATE = 44100
EAT_BEEP_FREQ = 880
EAT_BEEP_MS = 80
# The pulse is tied to moves rather than time, so it quickens on its own as the snake speeds up.
PULSE_FREQ = 110
PULSE_MS = 70
PULSE_EVERY_MOVES = 2
RATTLE_MS = 350
RATTLE_CLICKS_PER_SEC = 45

MAX_HIGH_SCORES = 10
# Kept beside the script rather than in the working directory, so scores persist however the game is launched.
HIGH_SCORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "high_scores.json")

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (0, 200, 0)
LETTERBOX = (40, 40, 40)
HEAD_GREEN = (0, 160, 0)
TONGUE = (255, 70, 110)
RATTLE = (205, 175, 115)
RATTLE_OUTLINE = (110, 80, 40)
TONGUE_FLICK_MS = 900
RATTLE_SHAKE_MS = 30
RAT_FUR = (120, 105, 95)
RAT_DARK = (85, 72, 65)
RAT_PINK = (215, 150, 150)
RAT_WHISKER = (200, 200, 200)

UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)
# Used to reject 180-degree turns, which would always run the snake into its own neck.
OPPOSITE = {UP: DOWN, DOWN: UP, LEFT: RIGHT, RIGHT: LEFT}

DIRECTION_KEYS = {
    pygame.K_UP: UP,
    pygame.K_DOWN: DOWN,
    pygame.K_LEFT: LEFT,
    pygame.K_RIGHT: RIGHT,
}


class State(Enum):
    WAITING = auto()
    PLAYING = auto()
    PAUSED = auto()
    ENTER_INITIALS = auto()
    GAME_OVER = auto()


def make_tone(freq, duration_ms, volume=0.5):
    mixer_init = pygame.mixer.get_init()
    if mixer_init is None:
        return None
    # The mixer may open in stereo even though mono was requested, so write one copy per actual channel.
    sample_rate, _, channels = mixer_init
    n_samples = int(sample_rate * duration_ms / 1000)
    # A brief fade-in and a fade-out avoid the audible click of a waveform starting or stopping abruptly.
    attack = max(1, int(sample_rate * 0.005))
    samples = array("h")
    for i in range(n_samples):
        envelope = min(1.0, i / attack) * (1 - i / n_samples)
        value = int(32767 * volume * envelope * math.sin(2 * math.pi * freq * i / sample_rate))
        samples.extend([value] * channels)
    return pygame.mixer.Sound(buffer=samples.tobytes())


def make_rattle(duration_ms, clicks_per_sec, volume=0.35):
    """Rapid bursts of decaying noise, like a rattlesnake's tail."""
    mixer_init = pygame.mixer.get_init()
    if mixer_init is None:
        return None
    sample_rate, _, channels = mixer_init
    n_samples = int(sample_rate * duration_ms / 1000)
    click_len = sample_rate / clicks_per_sec
    # A fixed seed makes the rattle sound the same every run and leaves the game's global RNG untouched.
    noise = random.Random(0)
    samples = array("h")
    smoothed = 0.0
    for i in range(n_samples):
        click_phase = (i % click_len) / click_len
        click_env = math.exp(-click_phase * 6)
        fade = 1 - i / n_samples
        # A light low-pass filter takes the harsh hiss off raw white noise.
        smoothed += 0.5 * (noise.uniform(-1, 1) - smoothed)
        value = int(32767 * volume * fade * click_env * smoothed)
        samples.extend([value] * channels)
    return pygame.mixer.Sound(buffer=samples.tobytes())


def load_sounds():
    try:
        pygame.mixer.init()
        return (
            make_tone(EAT_BEEP_FREQ, EAT_BEEP_MS, 0.4),
            make_rattle(RATTLE_MS, RATTLE_CLICKS_PER_SEC),
            make_tone(PULSE_FREQ, PULSE_MS, 0.6),
        )
    except pygame.error:
        # No audio device (remote desktop, CI, ...) shouldn't stop the game; it just runs silently.
        return None, None, None


def play(sound, then=None):
    if sound is None:
        return
    channel = sound.play()
    # Queueing on the same channel starts the follow-up exactly when the first sound ends, with no gap or overlap.
    if channel is not None and then is not None:
        channel.queue(then)


def random_food_position(snake):
    while True:
        # Excluding the last column and row makes food land on the board's edge less often.
        pos = (random.randrange(GRID_WIDTH - 1), random.randrange(GRID_HEIGHT - 1))
        if pos not in snake:
            return pos


def new_game():
    start = (GRID_WIDTH // 2, GRID_HEIGHT // 2)
    snake = [start, (start[0] - 1, start[1]), (start[0] - 2, start[1])]
    direction = RIGHT
    food = random_food_position(snake)
    return snake, direction, food


def get_score(snake):
    # The snake starts with 3 segments and grows by exactly one per rat, so length is the score.
    return len(snake) - 3


def load_high_scores():
    try:
        with open(HIGH_SCORE_FILE) as f:
            scores = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # A missing or corrupt file just means no scores yet; it's not worth crashing the game over.
        return []
    # Re-sort and trim in case the file was edited by hand.
    scores.sort(key=lambda entry: entry["score"], reverse=True)
    return scores[:MAX_HIGH_SCORES]


def save_high_scores(scores):
    with open(HIGH_SCORE_FILE, "w") as f:
        json.dump(scores, f, indent=2)


def is_high_score(scores, score):
    # Don't ask for initials after a game where nothing was eaten.
    if score <= 0:
        return False
    if len(scores) < MAX_HIGH_SCORES:
        return True
    return score > scores[-1]["score"]


def format_leaderboard(scores, highlight=None):
    if not scores:
        return "No high scores yet"
    lines = []
    for i, entry in enumerate(scores, start=1):
        marker = ">" if entry is highlight else " "
        lines.append(f"{marker}{i}. {entry['initials']}  {entry['score']}")
    return "\n".join(lines)


def enable_dpi_awareness():
    # Without this, Windows display scaling (125%, 150%, ...) bitmap-stretches the window and blurs it.
    # It is an SDL hint, so it must be set before pygame.init() creates the window.
    if sys.platform == "win32":
        os.environ.setdefault("SDL_WINDOWS_DPI_AWARENESS", "permonitorv2")


def initial_window_size():
    # Size the window from the desktop resolution so the game is a sensible size on anything from a laptop to a
    # 4K monitor, rather than a fixed 600x400 that is tiny on high-resolution screens.
    try:
        desktop_w, desktop_h = pygame.display.get_desktop_sizes()[0]
    except (pygame.error, IndexError):
        return WINDOW_WIDTH, WINDOW_HEIGHT
    fit = min(desktop_w * SCREEN_FILL / WINDOW_WIDTH, desktop_h * SCREEN_FILL / WINDOW_HEIGHT)
    # Whole-pixel cells keep the snake's squares crisp and evenly sized.
    cell = max(CELL_SIZE, int(CELL_SIZE * fit))
    return cell * GRID_WIDTH, cell * GRID_HEIGHT


class Layout:
    """Maps the logical game grid onto the real window size so everything renders at native resolution.

    Drawing small and stretching (pygame.SCALED) made text blocky and blurry, so instead every size is
    scaled here and things are drawn directly at full resolution.
    """

    def __init__(self, window_size):
        self.window_size = window_size
        window_w, window_h = window_size
        fit = min(window_w / WINDOW_WIDTH, window_h / WINDOW_HEIGHT)
        # Whole-pixel cells so neighbouring segments line up with no seams or uneven widths.
        self.cell = max(1, int(CELL_SIZE * fit))
        self.scale = self.cell / CELL_SIZE
        board_w, board_h = self.cell * GRID_WIDTH, self.cell * GRID_HEIGHT
        # Center the board; leftover space becomes a letterbox when the window's shape doesn't match.
        self.board = pygame.Rect((window_w - board_w) // 2, (window_h - board_h) // 2, board_w, board_h)
        self.font = pygame.font.SysFont(None, self.px(FONT_SIZE))
        self.small_font = pygame.font.SysFont(None, self.px(SMALL_FONT_SIZE))

    def px(self, n):
        return max(1, round(n * self.scale))

    def cell_rect(self, pos):
        return pygame.Rect(self.board.x + pos[0] * self.cell, self.board.y + pos[1] * self.cell, self.cell, self.cell)


def facing(from_pos, to_pos):
    return (to_pos[0] - from_pos[0], to_pos[1] - from_pos[1])


def draw_snake(screen, layout, snake, direction, shaking=False):
    cell = layout.cell
    # Face the head and tail from actual segment positions: the tail follows the body rather than `direction`,
    # and on a crash `direction` has already turned while the head never moved.
    head_dir = facing(snake[1], snake[0]) if len(snake) > 1 else direction
    tail_dir = facing(snake[-2], snake[-1]) if len(snake) > 1 else OPPOSITE[direction]

    for segment in snake[1:-1]:
        pygame.draw.rect(screen, GREEN, layout.cell_rect(segment))

    # Shapes are described in cell units relative to a cell's center (`ahead` along the facing direction, `side`
    # across it) so one description scales with the window and rotates to any of the four directions.
    def point(rect, facing_dir, ahead, side):
        fx, fy = facing_dir
        return (rect.centerx + cell * (ahead * fx - side * fy), rect.centery + cell * (ahead * fy + side * fx))

    # Rattle: tapering beads, like a rattlesnake's tail. After eating, they swing side to side while the rattle
    # sound plays, more toward the tip, as a real rattle would.
    tail_rect = layout.cell_rect(snake[-1])
    sway = 0.0
    if shaking:
        sway = 0.06 if (pygame.time.get_ticks() // RATTLE_SHAKE_MS) % 2 else -0.06
    for i, (ahead, width) in enumerate([(-0.3, 0.8), (0.05, 0.62), (0.35, 0.44)]):
        length = 0.38 - i * 0.04
        center = point(tail_rect, tail_dir, ahead, sway * (i + 1))
        # Directions are always axis-aligned, so swapping width and height is enough to lay a bead along the tail.
        size = (length * cell, width * cell) if tail_dir[0] else (width * cell, length * cell)
        bead = pygame.Rect(0, 0, *size)
        bead.center = center
        pygame.draw.ellipse(screen, RATTLE, bead)
        pygame.draw.ellipse(screen, RATTLE_OUTLINE, bead, max(1, cell // 14))

    # Head: square at the neck so it joins the body seamlessly, rounded at the snout so it reads as a head.
    head_rect = layout.cell_rect(snake[0])
    radius = cell // 2
    front = {
        RIGHT: ("border_top_right_radius", "border_bottom_right_radius"),
        LEFT: ("border_top_left_radius", "border_bottom_left_radius"),
        UP: ("border_top_left_radius", "border_top_right_radius"),
        DOWN: ("border_bottom_left_radius", "border_bottom_right_radius"),
    }[head_dir]
    pygame.draw.rect(screen, HEAD_GREEN, head_rect, **{corner: radius for corner in front})

    if pygame.time.get_ticks() % TONGUE_FLICK_MS < TONGUE_FLICK_MS // 3:
        tongue_width = max(1, cell // 10)
        fork = point(head_rect, head_dir, 0.75, 0)
        pygame.draw.line(screen, TONGUE, point(head_rect, head_dir, 0.45, 0), fork, tongue_width)
        for side in (-0.15, 0.15):
            pygame.draw.line(screen, TONGUE, fork, point(head_rect, head_dir, 0.95, side), tongue_width)

    for side in (-0.22, 0.22):
        pygame.draw.circle(screen, WHITE, point(head_rect, head_dir, 0.1, side), max(1, cell * 0.13))
        pygame.draw.circle(screen, BLACK, point(head_rect, head_dir, 0.15, side), max(1, cell * 0.07))


def draw_rat(screen, layout, pos):
    cell = layout.cell
    rect = layout.cell_rect(pos)

    # Cell units relative to the cell's center, so the rat scales with the window. It always faces left,
    # since it doesn't move and a fixed pose is easier to recognise. The tail and whiskers spill a little
    # past the cell because their length is what makes it read as a rat rather than a mouse.
    def at(x, y):
        return (rect.centerx + x * cell, rect.centery + y * cell)

    def ellipse(color, x, y, w, h):
        shape = pygame.Rect(0, 0, w * cell, h * cell)
        shape.center = at(x, y)
        pygame.draw.ellipse(screen, color, shape)

    line_width = max(1, cell // 20)

    # The tail is drawn first so the body hides its root and it appears to grow out of the rump.
    tail = [at(0.3, 0.15), at(0.5, 0.25), at(0.68, 0.18), at(0.78, 0.0), at(0.8, -0.18)]
    pygame.draw.lines(screen, RAT_PINK, False, tail, max(1, cell // 9))

    for x in (-0.08, 0.22):
        ellipse(RAT_PINK, x, 0.3, 0.12, 0.07)

    # Proportions are what separate a rat from a mouse at this size: heavy haunches, a long wedge-shaped head
    # and a small ear. The darker spine gives the flat body some depth.
    ellipse(RAT_FUR, 0.05, 0.08, 0.78, 0.44)
    ellipse(RAT_FUR, 0.2, 0.08, 0.42, 0.5)
    ellipse(RAT_DARK, 0.08, -0.04, 0.55, 0.16)

    ellipse(RAT_FUR, -0.25, 0.05, 0.34, 0.3)
    pygame.draw.polygon(screen, RAT_FUR, [at(-0.28, -0.08), at(-0.28, 0.2), at(-0.53, 0.08)])

    pygame.draw.circle(screen, RAT_DARK, at(-0.17, -0.12), cell * 0.09)
    pygame.draw.circle(screen, RAT_PINK, at(-0.17, -0.12), cell * 0.05)

    pygame.draw.circle(screen, BLACK, at(-0.3, 0.0), max(1, cell * 0.04))
    pygame.draw.circle(screen, RAT_PINK, at(-0.53, 0.08), max(1, cell * 0.04))

    for end_y in (-0.04, 0.08, 0.2):
        pygame.draw.line(screen, RAT_WHISKER, at(-0.45, 0.08), at(-0.66, end_y), line_width)


def draw_center_text(screen, layout, font, text, color=WHITE):
    lines = text.split("\n")
    surfaces = [font.render(line, True, color) for line in lines]

    line_height = font.get_linesize()
    total_height = line_height * len(lines)
    max_width = max(s.get_width() for s in surfaces)
    center_x, center_y = layout.board.center
    top = center_y - total_height // 2

    # A semi-transparent backdrop keeps text readable over the snake while still showing the board behind it.
    padding = layout.px(20)
    backdrop = pygame.Surface((max_width + padding, total_height + padding), pygame.SRCALPHA)
    backdrop.fill((0, 0, 0, 180))
    screen.blit(backdrop, backdrop.get_rect(center=(center_x, center_y)))

    for i, surface in enumerate(surfaces):
        line_center_y = top + line_height * i + line_height // 2
        rect = surface.get_rect(center=(center_x, line_center_y))
        screen.blit(surface, rect)


class Game:
    """All game state plus input handling, per-frame updates and drawing."""

    def __init__(self, sounds):
        # Sounds are passed in so tests can run without an audio device.
        self.eat_sound, self.rattle_sound, self.pulse_sound = sounds
        # High scores and mute carry over between games, so they live outside reset().
        self.high_scores = load_high_scores()
        self.muted = False
        self.reset()
        # Only the very first game waits for SPACE; restarting from game over goes straight into play.
        self.state = State.WAITING

    def reset(self):
        self.snake, self.direction, self.food = new_game()
        self.state = State.PLAYING
        self.moves_per_sec = BASE_FPS
        self.turn_queue = []
        self.move_timer = 0
        self.move_count = 0
        self.rattle_shake_ms = 0
        self.initials = ""
        self.new_entry = None

    @property
    def score(self):
        return get_score(self.snake)

    def play(self, sound, then=None):
        if not self.muted:
            play(sound, then)

    def toggle_mute(self):
        self.muted = not self.muted
        # Cut off anything already playing so muting takes effect immediately, not after the rattle finishes.
        if self.muted and pygame.mixer.get_init():
            pygame.mixer.stop()

    def handle_key(self, key):
        # M is a valid initial, so it can't toggle mute on the initials screen.
        if key == pygame.K_m and self.state != State.ENTER_INITIALS:
            self.toggle_mute()
        elif self.state == State.WAITING:
            if key == pygame.K_SPACE:
                self.state = State.PLAYING
        elif self.state == State.PLAYING:
            if key == pygame.K_SPACE:
                self.state = State.PAUSED
            elif key in DIRECTION_KEYS:
                self.queue_turn(DIRECTION_KEYS[key])
        elif self.state == State.PAUSED:
            if key == pygame.K_SPACE:
                self.state = State.PLAYING
        elif self.state == State.ENTER_INITIALS:
            self.handle_initials_key(key)
        elif self.state == State.GAME_OVER and key == pygame.K_SPACE:
            self.reset()

    def queue_turn(self, new_direction):
        # Queue turns so fast key presses are each applied on their own move, and validate
        # against the last queued turn so the snake can never reverse into itself.
        last_direction = self.turn_queue[-1] if self.turn_queue else self.direction
        if (
            new_direction not in (last_direction, OPPOSITE[last_direction])
            and len(self.turn_queue) < MAX_QUEUED_TURNS
        ):
            self.turn_queue.append(new_direction)

    def handle_initials_key(self, key):
        if key == pygame.K_BACKSPACE:
            self.initials = self.initials[:-1]
        elif key == pygame.K_RETURN and len(self.initials) == 3:
            self.new_entry = {"initials": self.initials, "score": self.score}
            self.high_scores.append(self.new_entry)
            self.high_scores.sort(key=lambda entry: entry["score"], reverse=True)
            del self.high_scores[MAX_HIGH_SCORES:]
            save_high_scores(self.high_scores)
            self.state = State.GAME_OVER
        elif pygame.K_a <= key <= pygame.K_z and len(self.initials) < 3:
            self.initials += chr(key).upper()

    def update(self, dt):
        # Timers run on dt rather than the system clock so game logic can be tested without real time passing.
        # The shake counts down in every state so it doesn't freeze if the game ends mid-rattle.
        self.rattle_shake_ms = max(0, self.rattle_shake_ms - dt)
        if self.state != State.PLAYING:
            return
        self.move_timer += dt
        move_interval = 1000 / self.moves_per_sec
        if self.move_timer >= move_interval:
            # Cap the carry-over so a stall (e.g. dragging the window) can't cause a burst of moves.
            self.move_timer = min(self.move_timer - move_interval, move_interval)
            self.step()

    def step(self):
        # Only one queued turn per move, so each quick key press gets its own move.
        if self.turn_queue:
            self.direction = self.turn_queue.pop(0)
        head_x, head_y = self.snake[0]
        dx, dy = self.direction
        new_head = (head_x + dx, head_y + dy)

        hit_wall = not (0 <= new_head[0] < GRID_WIDTH and 0 <= new_head[1] < GRID_HEIGHT)
        hit_self = new_head in self.snake
        if hit_wall or hit_self:
            if is_high_score(self.high_scores, self.score):
                self.state = State.ENTER_INITIALS
            else:
                self.state = State.GAME_OVER
            return

        self.snake.insert(0, new_head)
        if new_head == self.food:
            self.food = random_food_position(self.snake)
            self.rattle_shake_ms = EAT_BEEP_MS + RATTLE_MS
            self.play(self.eat_sound, then=self.rattle_sound)
        else:
            self.snake.pop()
        if self.move_count % PULSE_EVERY_MOVES == 0:
            self.play(self.pulse_sound)
        self.move_count += 1
        # Applied after the move so a speed-up takes effect from the next move, not mid-interval.
        self.moves_per_sec = min(BASE_FPS + (self.score // SCORE_STEP) * FPS_STEP, MAX_FPS)

    def board_items_overlap(self, layout, rect):
        return rect.collidelist([layout.cell_rect(pos) for pos in [*self.snake, self.food]]) != -1

    def draw_hud_label(self, screen, layout, text, rect):
        # Hide HUD text while the snake or rat is under it so the text doesn't hide them. Only the rat's own cell
        # counts, so its tail and whiskers can still slip under the text; hiding the score for those would
        # hide it whenever the rat is merely nearby.
        if not self.board_items_overlap(layout, rect):
            screen.blit(text, rect)

    def draw(self, screen, layout):
        font, small_font = layout.font, layout.small_font
        screen.fill(LETTERBOX)
        screen.fill(BLACK, layout.board)
        draw_rat(screen, layout, self.food)
        draw_snake(screen, layout, self.snake, self.direction, shaking=self.rattle_shake_ms > 0)

        margin = layout.px(10)
        score_text = font.render(f"Score: {self.score}", True, GREEN)
        self.draw_hud_label(screen, layout, score_text, score_text.get_rect(topleft=layout.board.move(margin, margin).topleft))
        if self.muted:
            mute_text = font.render("Muted (M)", True, GREEN)
            mute_rect = mute_text.get_rect(topright=(layout.board.right - margin, layout.board.y + margin))
            self.draw_hud_label(screen, layout, mute_text, mute_rect)

        if self.state == State.WAITING:
            draw_center_text(screen, layout, font, "Press SPACE to start")
        elif self.state == State.PAUSED:
            draw_center_text(screen, layout, font, "Paused - SPACE to resume")
        elif self.state == State.ENTER_INITIALS:
            shown = self.initials.ljust(3, "_")
            text = (
                f"NEW HIGH SCORE! Score: {self.score}\n\n"
                f"{shown}\n\n"
                "Type A-Z, BACKSPACE to edit,\nENTER to confirm"
            )
            draw_center_text(screen, layout, small_font, text)
        elif self.state == State.GAME_OVER:
            text = (
                "Game Over\n\n"
                "HIGH SCORES\n"
                f"{format_leaderboard(self.high_scores, self.new_entry)}\n\n"
                "SPACE to play again or ESC to quit"
            )
            draw_center_text(screen, layout, small_font, text)


def main():
    # Must come before pygame.init(). A small buffer keeps latency low so the beep lines up with eating.
    pygame.mixer.pre_init(SAMPLE_RATE, -16, 1, 512)
    enable_dpi_awareness()
    pygame.init()
    screen = pygame.display.set_mode(initial_window_size(), pygame.RESIZABLE)
    pygame.display.set_caption("Snake")
    clock = pygame.time.Clock()
    layout = Layout(screen.get_size())
    game = Game(load_sounds())

    dt = 0
    running = True
    while running:
        for event in pygame.event.get():
            # Quitting is handled here rather than in Game, since it ends the app, not just the game.
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False
            elif event.type == pygame.KEYDOWN:
                game.handle_key(event.key)

        game.update(dt)

        # After a resize, rebuild the layout so cells and fonts render at the new native size instead of
        # being stretched.
        screen = pygame.display.get_surface()
        if screen.get_size() != layout.window_size:
            layout = Layout(screen.get_size())
        game.draw(screen, layout)
        pygame.display.flip()

        dt = clock.tick(RENDER_FPS)

    pygame.quit()


if __name__ == "__main__":
    main()
