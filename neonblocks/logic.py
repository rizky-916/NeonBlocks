"""Core game rules for NeonBlocks.

This module is intentionally free of any pygame code so the rules can be
unit-tested without opening a window.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

COLS = 10
VISIBLE_ROWS = 20
HIDDEN_ROWS = 2  # spawn area above the visible playfield
ROWS = VISIBLE_ROWS + HIDDEN_ROWS

# Piece order also defines each piece's colour index in the UI.
PIECE_NAMES = ("I", "J", "L", "O", "S", "T", "Z")

_SPAWN_SHAPES = {
    "I": ((0, 0, 0, 0),
          (1, 1, 1, 1),
          (0, 0, 0, 0),
          (0, 0, 0, 0)),
    "J": ((1, 0, 0),
          (1, 1, 1),
          (0, 0, 0)),
    "L": ((0, 0, 1),
          (1, 1, 1),
          (0, 0, 0)),
    "O": ((1, 1),
          (1, 1)),
    "S": ((0, 1, 1),
          (1, 1, 0),
          (0, 0, 0)),
    "T": ((0, 1, 0),
          (1, 1, 1),
          (0, 0, 0)),
    "Z": ((1, 1, 0),
          (0, 1, 1),
          (0, 0, 0)),
}

Shape = Tuple[Tuple[int, ...], ...]


def rotate_cw(shape: Shape) -> Shape:
    """Rotate a square matrix 90 degrees clockwise."""
    return tuple(tuple(row) for row in zip(*shape[::-1]))


def _build_rotations(shape: Shape) -> Tuple[Shape, ...]:
    states = [shape]
    for _ in range(3):
        states.append(rotate_cw(states[-1]))
    return tuple(states)


ROTATIONS = {name: _build_rotations(s) for name, s in _SPAWN_SHAPES.items()}

# Simplified wall kicks: (dx, dy) offsets tried in order when a rotation
# collides. Negative dy moves the piece up.
KICKS = ((0, 0), (-1, 0), (1, 0), (0, -1), (-2, 0), (2, 0))

LINE_SCORES = (0, 100, 300, 500, 800)  # multiplied by the current level
SOFT_DROP_POINTS = 1   # per cell
HARD_DROP_POINTS = 2   # per cell
LINES_PER_LEVEL = 10
LOCK_DELAY_MS = 500
MAX_LOCK_RESETS = 15
MAX_LEVEL = 99


def gravity_interval_ms(level: int) -> float:
    """Milliseconds between automatic one-row drops for a level."""
    level = max(1, min(level, MAX_LEVEL))
    seconds = (0.8 - (level - 1) * 0.007) ** (level - 1)
    return max(1000 / 60, seconds * 1000)


class BagRandomizer:
    """'7-bag' generator: every piece appears once per bag of seven,
    which avoids long droughts of the same piece."""

    def __init__(self, rng: Optional[random.Random] = None) -> None:
        # Gameplay randomness only, not security-sensitive.
        self._rng = rng or random.Random()  # nosec B311
        self._bag: List[str] = []

    def next(self) -> str:
        if not self._bag:
            self._bag = list(PIECE_NAMES)
            self._rng.shuffle(self._bag)
        return self._bag.pop()


@dataclass
class Piece:
    kind: str
    rotation: int
    x: int
    y: int

    @property
    def shape(self) -> Shape:
        return ROTATIONS[self.kind][self.rotation]

    def cells(self, x: Optional[int] = None, y: Optional[int] = None,
              rotation: Optional[int] = None) -> List[Tuple[int, int]]:
        """Board coordinates (col, row) occupied by this piece."""
        x = self.x if x is None else x
        y = self.y if y is None else y
        rot = self.rotation if rotation is None else rotation
        shape = ROTATIONS[self.kind][rot]
        return [(x + c, y + r)
                for r, row in enumerate(shape)
                for c, filled in enumerate(row) if filled]


def spawn_piece(kind: str) -> Piece:
    size = len(ROTATIONS[kind][0])
    x = (COLS - size) // 2
    y = HIDDEN_ROWS - 1
    return Piece(kind, 0, x, y)


class Game:
    """Complete state of one game session."""

    def __init__(self, rng: Optional[random.Random] = None) -> None:
        self._rng = rng
        self.reset()

    # ------------------------------------------------------------------ setup
    def reset(self) -> None:
        # board[row][col] holds a piece name, or None when empty.
        self.board: List[List[Optional[str]]] = [
            [None] * COLS for _ in range(ROWS)
        ]
        self.bag = BagRandomizer(self._rng)
        self.score = 0
        self.lines = 0
        self.level = 1
        self.game_over = False
        self._events: List[str] = []
        self._gravity_timer = 0.0
        self._lock_timer = 0.0
        self._lock_resets = 0
        self.next_kind = self.bag.next()
        self.current: Piece = spawn_piece(self.bag.next())
        if self._collides(self.current.cells()):
            self.game_over = True

    def pop_events(self) -> List[str]:
        """Return and forget events ("lock", "clear") since the last call.
        Used by the UI to play sounds."""
        events, self._events = self._events, []
        return events

    # --------------------------------------------------------------- queries
    def _collides(self, cells: Sequence[Tuple[int, int]]) -> bool:
        for x, y in cells:
            if x < 0 or x >= COLS or y < 0 or y >= ROWS:
                return True
            if self.board[y][x] is not None:
                return True
        return False

    def is_grounded(self) -> bool:
        return self._collides(self.current.cells(y=self.current.y + 1))

    def ghost_y(self) -> int:
        """Row where the current piece would land after a hard drop."""
        y = self.current.y
        while not self._collides(self.current.cells(y=y + 1)):
            y += 1
        return y

    # --------------------------------------------------------------- actions
    def _after_successful_move(self) -> None:
        # Moving or rotating on the ground buys a little more time, but only
        # a limited number of times so a piece cannot stall forever.
        if self.is_grounded() and self._lock_resets < MAX_LOCK_RESETS:
            self._lock_timer = 0.0
            self._lock_resets += 1

    def move(self, dx: int) -> bool:
        if self.game_over:
            return False
        if self._collides(self.current.cells(x=self.current.x + dx)):
            return False
        self.current.x += dx
        self._after_successful_move()
        return True

    def rotate(self, direction: int = 1) -> bool:
        """Rotate clockwise (direction=1) or counter-clockwise (-1)."""
        if self.game_over or self.current.kind == "O":
            return False
        new_rot = (self.current.rotation + direction) % 4
        for dx, dy in KICKS:
            nx, ny = self.current.x + dx, self.current.y + dy
            if not self._collides(self.current.cells(nx, ny, new_rot)):
                self.current.x, self.current.y = nx, ny
                self.current.rotation = new_rot
                self._after_successful_move()
                return True
        return False

    def soft_drop(self) -> bool:
        if self.game_over:
            return False
        if self._collides(self.current.cells(y=self.current.y + 1)):
            return False
        self.current.y += 1
        self.score += SOFT_DROP_POINTS
        self._gravity_timer = 0.0
        return True

    def hard_drop(self) -> int:
        if self.game_over:
            return 0
        target = self.ghost_y()
        distance = target - self.current.y
        self.current.y = target
        self.score += distance * HARD_DROP_POINTS
        self._lock_piece()
        return distance

    # ----------------------------------------------------------------- tick
    def update(self, dt_ms: float) -> None:
        """Advance gravity and lock delay by dt_ms milliseconds."""
        if self.game_over:
            return
        if self.is_grounded():
            self._lock_timer += dt_ms
            if self._lock_timer >= LOCK_DELAY_MS:
                self._lock_piece()
            return

        self._lock_timer = 0.0
        self._gravity_timer += dt_ms
        interval = gravity_interval_ms(self.level)
        while self._gravity_timer >= interval and not self.is_grounded():
            self._gravity_timer -= interval
            self.current.y += 1
        if self.is_grounded():
            self._gravity_timer = 0.0

    # ------------------------------------------------------------- internals
    def _lock_piece(self) -> None:
        cells = self.current.cells()
        for x, y in cells:
            self.board[y][x] = self.current.kind

        # "Lock out": the whole piece came to rest above the visible area.
        if all(y < HIDDEN_ROWS for _, y in cells):
            self.game_over = True
            return

        self._events.append("lock")
        cleared = self._clear_lines()
        if cleared:
            self._events.append("clear")
            self.lines += cleared
            self.score += LINE_SCORES[cleared] * self.level
            self.level = min(MAX_LEVEL, 1 + self.lines // LINES_PER_LEVEL)

        self._spawn_next()

    def _clear_lines(self) -> int:
        remaining = [row for row in self.board
                     if any(cell is None for cell in row)]
        cleared = ROWS - len(remaining)
        if cleared:
            self.board = [[None] * COLS for _ in range(cleared)] + remaining
        return cleared

    def _spawn_next(self) -> None:
        self.current = spawn_piece(self.next_kind)
        self.next_kind = self.bag.next()
        self._gravity_timer = 0.0
        self._lock_timer = 0.0
        self._lock_resets = 0
        # "Block out": no room for the new piece.
        if self._collides(self.current.cells()):
            self.game_over = True
