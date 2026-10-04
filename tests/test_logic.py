import random
import unittest

from neonblocks.logic import (
    COLS, HIDDEN_ROWS, LINE_SCORES, LOCK_DELAY_MS, PIECE_NAMES, ROWS,
    BagRandomizer, Game, gravity_interval_ms,
)


def fill_row(game, row, holes=()):
    for x in range(COLS):
        game.board[row][x] = None if x in holes else "Z"


class BagTests(unittest.TestCase):
    def test_each_bag_contains_all_seven(self):
        bag = BagRandomizer(random.Random(1))
        for _ in range(5):
            self.assertEqual(sorted(bag.next() for _ in range(7)), sorted(PIECE_NAMES))


class LineClearTests(unittest.TestCase):
    def setUp(self):
        self.g = Game(random.Random(0))

    def test_multi_clear_with_ragged_row_above_does_not_crash(self):
        # Regression: the original code raised KeyError here.
        fill_row(self.g, ROWS - 1)
        fill_row(self.g, ROWS - 2)
        self.g.board[ROWS - 3][0] = "T"
        self.assertEqual(self.g._clear_lines(), 2)
        self.assertEqual(self.g.board[ROWS - 1][0], "T")
        self.assertTrue(all(c is None for c in self.g.board[ROWS - 2]))

    def test_non_adjacent_rows_clear(self):
        fill_row(self.g, ROWS - 1)
        fill_row(self.g, ROWS - 2, holes={3})
        fill_row(self.g, ROWS - 3)
        self.assertEqual(self.g._clear_lines(), 2)
        self.assertIsNone(self.g.board[ROWS - 1][3])
        self.assertEqual(self.g.board[ROWS - 1][0], "Z")

    def test_line_completed_by_piece_clears_immediately(self):
        # Regression: original code only cleared on the *next* lock.
        g = Game(random.Random(0))
        g.current.kind = "I"
        g.current.rotation = 0
        g.current.x = 0
        for x in range(4, COLS):
            g.board[ROWS - 1][x] = "Z"
        g.hard_drop()
        self.assertEqual(g.lines, 1)
        self.assertTrue(all(c is None for c in g.board[ROWS - 1]))

    def test_tetris_score_uses_level(self):
        g = Game(random.Random(0))
        g.level = 3
        for r in range(ROWS - 4, ROWS):
            fill_row(g, r, holes={0})
        g.current.kind, g.current.rotation = "I", 1  # vertical, column 2 of 4x4
        g.current.x = -2
        g.current.y = HIDDEN_ROWS
        g.score = 0
        dropped = g.hard_drop()
        self.assertEqual(g.lines, 4)
        self.assertEqual(g.score, dropped * 2 + LINE_SCORES[4] * 3)


class MovementTests(unittest.TestCase):
    def test_walls_block_movement(self):
        g = Game(random.Random(0))
        for _ in range(20):
            g.move(-1)
        self.assertEqual(min(x for x, _ in g.current.cells()), 0)
        for _ in range(20):
            g.move(1)
        self.assertEqual(max(x for x, _ in g.current.cells()), COLS - 1)

    def test_rotation_kicks_off_wall(self):
        g = Game(random.Random(0))
        g.current.kind, g.current.rotation = "I", 1
        g.current.y = 10
        while g.move(1):
            pass
        self.assertTrue(g.rotate(1))
        self.assertTrue(all(0 <= x < COLS for x, _ in g.current.cells()))

    def test_lock_delay(self):
        g = Game(random.Random(0))
        g.current.y = g.ghost_y()
        first = g.current.kind
        g.update(LOCK_DELAY_MS - 1)
        self.assertEqual(g.current.kind, first)
        self.assertEqual(g.pop_events(), [])
        g.update(2)
        self.assertEqual(g.pop_events(), ["lock"])


class LevelAndGameOverTests(unittest.TestCase):
    def test_level_up_every_ten_lines(self):
        g = Game(random.Random(0))
        g.lines = 9
        fill_row(g, ROWS - 1, holes=set(range(4)))
        g.current.kind, g.current.rotation, g.current.x = "I", 0, 0
        g.hard_drop()
        self.assertEqual(g.lines, 10)
        self.assertEqual(g.level, 2)

    def test_gravity_gets_faster(self):
        self.assertGreater(gravity_interval_ms(1), gravity_interval_ms(5))
        self.assertGreaterEqual(gravity_interval_ms(99), 1000 / 60)

    def test_block_out_ends_game(self):
        g = Game(random.Random(0))
        for r in range(HIDDEN_ROWS, ROWS):
            fill_row(g, r, holes={r % COLS})
        for _ in range(3):
            if g.game_over:
                break
            g.hard_drop()
        self.assertTrue(g.game_over)
        self.assertFalse(g.move(1))
        self.assertEqual(g.hard_drop(), 0)


if __name__ == "__main__":
    unittest.main()
