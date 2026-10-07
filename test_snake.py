import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

import snake
from snake import DOWN, LEFT, RIGHT, UP, Game, Layout, State


def setUpModule():
    pygame.init()


def tearDownModule():
    pygame.quit()


class GameTestCase(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        score_file = os.path.join(temp_dir.name, "high_scores.json")
        patcher = mock.patch.object(snake, "HIGH_SCORE_FILE", score_file)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.game = Game((None, None, None))
        self.game.handle_key(pygame.K_SPACE)

    def move(self, times=1):
        for _ in range(times):
            self.game.update(1000 / self.game.moves_per_sec)


class TestStartAndPause(unittest.TestCase):
    def test_starts_waiting_until_space(self):
        game = Game((None, None, None))
        self.assertEqual(game.state, State.WAITING)
        game.update(5000)
        self.assertEqual(game.snake[0], (snake.GRID_WIDTH // 2, snake.GRID_HEIGHT // 2))
        game.handle_key(pygame.K_SPACE)
        self.assertEqual(game.state, State.PLAYING)


class TestMovement(GameTestCase):
    def test_moves_once_per_interval(self):
        head_x, head_y = self.game.snake[0]
        self.game.update(1000 / self.game.moves_per_sec - 1)
        self.assertEqual(self.game.snake[0], (head_x, head_y))
        self.game.update(1)
        self.assertEqual(self.game.snake[0], (head_x + 1, head_y))

    def test_stall_causes_at_most_two_moves_in_a_row(self):
        head_x, head_y = self.game.snake[0]
        self.game.update(10_000)
        self.game.update(0)
        self.game.update(0)
        self.assertEqual(self.game.snake[0], (head_x + 2, head_y))

    def test_pause_stops_movement(self):
        self.game.handle_key(pygame.K_SPACE)
        head = self.game.snake[0]
        self.game.update(5000)
        self.assertEqual(self.game.state, State.PAUSED)
        self.assertEqual(self.game.snake[0], head)
        self.game.handle_key(pygame.K_SPACE)
        self.assertEqual(self.game.state, State.PLAYING)


class TestTurning(GameTestCase):
    def test_reverse_is_ignored(self):
        self.game.handle_key(pygame.K_LEFT)
        self.assertEqual(self.game.turn_queue, [])

    def test_fast_turns_are_applied_one_per_move(self):
        head_x, head_y = self.game.snake[0]
        self.game.handle_key(pygame.K_UP)
        self.game.handle_key(pygame.K_LEFT)
        self.assertEqual(self.game.turn_queue, [UP, LEFT])
        self.move()
        self.assertEqual(self.game.snake[0], (head_x, head_y - 1))
        self.move()
        self.assertEqual(self.game.snake[0], (head_x - 1, head_y - 1))
        self.assertEqual(self.game.state, State.PLAYING)

    def test_queued_turn_cannot_reverse_previous_queued_turn(self):
        self.game.handle_key(pygame.K_UP)
        self.game.handle_key(pygame.K_DOWN)
        self.assertEqual(self.game.turn_queue, [UP])

    def test_queue_is_capped(self):
        for key in (pygame.K_UP, pygame.K_LEFT, pygame.K_DOWN, pygame.K_RIGHT, pygame.K_UP):
            self.game.handle_key(key)
        self.assertEqual(self.game.turn_queue, [UP, LEFT, DOWN])


class TestEatingAndCollisions(GameTestCase):
    def test_eating_grows_snake_and_starts_rattle(self):
        head_x, head_y = self.game.snake[0]
        self.game.food = (head_x + 1, head_y)
        length = len(self.game.snake)
        self.move()
        self.assertEqual(len(self.game.snake), length + 1)
        self.assertEqual(self.game.score, 1)
        self.assertNotIn(self.game.food, self.game.snake)
        self.assertGreater(self.game.rattle_shake_ms, 0)
        self.game.update(snake.EAT_BEEP_MS + snake.RATTLE_MS)
        self.assertEqual(self.game.rattle_shake_ms, 0)

    def test_speed_increases_with_score(self):
        self.game.snake.extend([(0, 0)] * snake.SCORE_STEP)
        head_x, head_y = self.game.snake[0]
        self.game.food = (head_x + 1, head_y)
        self.move()
        self.assertEqual(self.game.moves_per_sec, snake.BASE_FPS + snake.FPS_STEP)

    def test_hitting_wall_with_zero_score_ends_game(self):
        self.game.food = (0, 0)
        self.move(snake.GRID_WIDTH)
        self.assertEqual(self.game.state, State.GAME_OVER)

    def test_hitting_self_ends_game(self):
        self.game.high_scores = [{"initials": "AAA", "score": 99}] * snake.MAX_HIGH_SCORES
        x, y = self.game.snake[0]
        self.game.snake = [(x, y), (x - 1, y), (x - 1, y - 1), (x, y - 1), (x + 1, y - 1), (x + 1, y)]
        self.game.handle_key(pygame.K_UP)
        self.move()
        self.assertEqual(self.game.state, State.GAME_OVER)


class TestHighScores(GameTestCase):
    def reach_initials_entry(self):
        head_x, head_y = self.game.snake[0]
        self.game.food = (head_x + 1, head_y)
        while self.game.state == State.PLAYING:
            self.move()
        self.assertEqual(self.game.state, State.ENTER_INITIALS)

    def test_entering_initials_saves_score(self):
        self.reach_initials_entry()
        for key in (pygame.K_a, pygame.K_b, pygame.K_x, pygame.K_BACKSPACE, pygame.K_c, pygame.K_d):
            self.game.handle_key(key)
        self.assertEqual(self.game.initials, "ABC")
        self.game.handle_key(pygame.K_RETURN)
        self.assertEqual(self.game.state, State.GAME_OVER)
        self.assertEqual(snake.load_high_scores(), [{"initials": "ABC", "score": 1}])

    def test_enter_requires_three_letters(self):
        self.reach_initials_entry()
        self.game.handle_key(pygame.K_a)
        self.game.handle_key(pygame.K_RETURN)
        self.assertEqual(self.game.state, State.ENTER_INITIALS)

    def test_m_types_initial_instead_of_muting(self):
        self.reach_initials_entry()
        self.game.handle_key(pygame.K_m)
        self.assertEqual(self.game.initials, "M")
        self.assertFalse(self.game.muted)

    def test_is_high_score(self):
        full = [{"initials": "AAA", "score": 10}] * snake.MAX_HIGH_SCORES
        self.assertFalse(snake.is_high_score([], 0))
        self.assertTrue(snake.is_high_score([], 1))
        self.assertFalse(snake.is_high_score(full, 10))
        self.assertTrue(snake.is_high_score(full, 11))


class TestMuteAndRestart(GameTestCase):
    def test_m_toggles_mute(self):
        self.game.handle_key(pygame.K_m)
        self.assertTrue(self.game.muted)
        self.game.handle_key(pygame.K_m)
        self.assertFalse(self.game.muted)

    def test_restart_resets_game_but_keeps_mute_and_scores(self):
        self.game.handle_key(pygame.K_m)
        self.game.high_scores = [{"initials": "ABC", "score": 5}]
        self.game.handle_key(pygame.K_UP)
        self.game.state = State.GAME_OVER
        self.game.handle_key(pygame.K_SPACE)
        self.assertEqual(self.game.state, State.PLAYING)
        self.assertEqual(self.game.score, 0)
        self.assertEqual(self.game.direction, RIGHT)
        self.assertEqual(self.game.turn_queue, [])
        self.assertTrue(self.game.muted)
        self.assertEqual(self.game.high_scores, [{"initials": "ABC", "score": 5}])


class TestDrawing(GameTestCase):
    def test_every_state_draws_at_several_sizes(self):
        for size in [(600, 400), (900, 700), (2580, 1720)]:
            surface = pygame.Surface(size)
            layout = Layout(size)
            for state in State:
                with self.subTest(size=size, state=state):
                    self.game.state = state
                    self.game.draw(surface, layout)

    def test_score_hidden_while_snake_or_rat_under_it(self):
        layout = Layout((600, 400))
        surface = pygame.Surface((600, 400))
        self.game.food = (40, 30)
        score_area = pygame.Rect(layout.px(10), layout.px(10), layout.px(60), layout.px(15))

        def score_visible():
            # The snake body shares the score's green, so only look at pixels outside the snake.
            surface.fill((0, 0, 0))
            self.game.draw(surface, layout)
            snake_cells = [layout.cell_rect(segment) for segment in self.game.snake]
            pixels = pygame.PixelArray(surface)
            try:
                return any(
                    surface.unmap_rgb(pixels[x, y]) == snake.GREEN
                    and not any(cell.collidepoint(x, y) for cell in snake_cells)
                    for x in range(score_area.left, score_area.right)
                    for y in range(score_area.top, score_area.bottom)
                )
            finally:
                pixels.close()

        self.assertTrue(score_visible())
        self.game.snake = [(2, 1), (3, 1), (4, 1)]
        self.assertFalse(score_visible())
        self.game.snake = [(30, 20), (29, 20), (28, 20)]
        self.assertTrue(score_visible())
        self.game.food = (3, 1)
        self.assertFalse(score_visible())
        self.game.food = (40, 30)
        self.assertTrue(score_visible())

    def test_layout_keeps_board_inside_window(self):
        layout = Layout((900, 700))
        self.assertTrue(pygame.Rect(0, 0, 900, 700).contains(layout.board))
        self.assertEqual(layout.board.width, layout.cell * snake.GRID_WIDTH)


if __name__ == "__main__":
    unittest.main()
