import json
import os
import random
from enum import Enum, auto

import pygame

CELL_SIZE = 10
GRID_WIDTH = 60
GRID_HEIGHT = 40
WINDOW_WIDTH = CELL_SIZE * GRID_WIDTH
WINDOW_HEIGHT = CELL_SIZE * GRID_HEIGHT
BASE_FPS = 5
MAX_FPS = 25
FPS_STEP = 1
SCORE_STEP = 5

MAX_HIGH_SCORES = 10
HIGH_SCORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "high_scores.json")

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (0, 200, 0)
RED = (200, 0, 0)

UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)
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


def random_food_position(snake):
    while True:
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
    return len(snake) - 3


def load_high_scores():
    try:
        with open(HIGH_SCORE_FILE) as f:
            scores = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    scores.sort(key=lambda entry: entry["score"], reverse=True)
    return scores[:MAX_HIGH_SCORES]


def save_high_scores(scores):
    with open(HIGH_SCORE_FILE, "w") as f:
        json.dump(scores, f, indent=2)


def is_high_score(scores, score):
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


def draw_center_text(screen, font, text, color=WHITE):
    lines = text.split("\n")
    surfaces = [font.render(line, True, color) for line in lines]

    line_height = font.get_linesize()
    total_height = line_height * len(lines)
    max_width = max(s.get_width() for s in surfaces)
    center_x, center_y = WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2
    top = center_y - total_height // 2

    backdrop = pygame.Surface((max_width + 20, total_height + 20), pygame.SRCALPHA)
    backdrop.fill((0, 0, 0, 180))
    screen.blit(backdrop, backdrop.get_rect(center=(center_x, center_y)))

    for i, surface in enumerate(surfaces):
        line_center_y = top + line_height * i + line_height // 2
        rect = surface.get_rect(center=(center_x, line_center_y))
        screen.blit(surface, rect)


def main():
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE | pygame.SCALED)
    pygame.init()
    pygame.display.set_caption("Snake")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 24)
    small_font = pygame.font.SysFont(None, 20)
    hud_font = pygame.font.SysFont(None, 24)

    snake, direction, food = new_game()
    state = State.WAITING
    current_fps = BASE_FPS
    high_scores = load_high_scores()
    initials = ""
    new_entry = None

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif state == State.WAITING:
                    if event.key == pygame.K_SPACE:
                        state = State.PLAYING
                elif state == State.PLAYING:
                    if event.key == pygame.K_SPACE:
                        state = State.PAUSED
                    elif event.key in DIRECTION_KEYS:
                        new_direction = DIRECTION_KEYS[event.key]
                        if new_direction != OPPOSITE[direction]:
                            direction = new_direction
                elif state == State.PAUSED:
                    if event.key == pygame.K_SPACE:
                        state = State.PLAYING
                elif state == State.ENTER_INITIALS:
                    if event.key == pygame.K_BACKSPACE:
                        initials = initials[:-1]
                    elif event.key == pygame.K_RETURN and len(initials) == 3:
                        new_entry = {"initials": initials, "score": get_score(snake)}
                        high_scores.append(new_entry)
                        high_scores.sort(key=lambda entry: entry["score"], reverse=True)
                        del high_scores[MAX_HIGH_SCORES:]
                        save_high_scores(high_scores)
                        state = State.GAME_OVER
                    elif pygame.K_a <= event.key <= pygame.K_z and len(initials) < 3:
                        initials += chr(event.key).upper()
                elif state == State.GAME_OVER:
                    if event.key == pygame.K_SPACE:
                        snake, direction, food = new_game()
                        current_fps = BASE_FPS
                        initials = ""
                        new_entry = None
                        state = State.PLAYING

        if state == State.PLAYING:
            head_x, head_y = snake[0]
            dx, dy = direction
            new_head = (head_x + dx, head_y + dy)

            hit_wall = not (0 <= new_head[0] < GRID_WIDTH and 0 <= new_head[1] < GRID_HEIGHT)
            hit_self = new_head in snake

            if hit_wall or hit_self:
                if is_high_score(high_scores, get_score(snake)):
                    state = State.ENTER_INITIALS
                else:
                    state = State.GAME_OVER
            else:
                snake.insert(0, new_head)
                if new_head == food:
                    food = random_food_position(snake)
                else:
                    snake.pop()
                current_fps = min(BASE_FPS + (get_score(snake) // SCORE_STEP) * FPS_STEP, MAX_FPS)

        screen.fill(BLACK)
        for segment in snake:
            rect = pygame.Rect(segment[0] * CELL_SIZE, segment[1] * CELL_SIZE, CELL_SIZE, CELL_SIZE)
            pygame.draw.rect(screen, GREEN, rect)
        food_rect = pygame.Rect(food[0] * CELL_SIZE, food[1] * CELL_SIZE, CELL_SIZE, CELL_SIZE)
        pygame.draw.rect(screen, RED, food_rect)

        score_text = hud_font.render(f"Score: {get_score(snake)}", True, GREEN)
        screen.blit(score_text, (10, 10))

        if state == State.WAITING:
            draw_center_text(screen, font, "Press SPACE to start")
        elif state == State.PAUSED:
            draw_center_text(screen, font, "Paused - SPACE to resume")
        elif state == State.ENTER_INITIALS:
            shown = initials.ljust(3, "_")
            text = (
                f"NEW HIGH SCORE! Score: {get_score(snake)}\n\n"
                f"{shown}\n\n"
                "Type A-Z, BACKSPACE to edit,\nENTER to confirm"
            )
            draw_center_text(screen, small_font, text)
        elif state == State.GAME_OVER:
            text = (
                "Game Over\n\n"
                "HIGH SCORES\n"
                f"{format_leaderboard(high_scores, new_entry)}\n\n"
                "SPACE to play again or ESC to quit"
            )
            draw_center_text(screen, small_font, text)

        pygame.display.flip()

        clock.tick(current_fps)

    pygame.quit()


if __name__ == "__main__":
    main()
