"""Pygame front-end for NeonBlocks: rendering, input and the main loop."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict

import pygame

from . import __version__
from .logic import COLS, HIDDEN_ROWS, ROWS, VISIBLE_ROWS, ROTATIONS, Game
from .storage import HighScoreStore

# ----------------------------------------------------------------- layout
CELL = 30
MARGIN = 24
BOARD_W = COLS * CELL
BOARD_H = VISIBLE_ROWS * CELL
BOARD_X = MARGIN
BOARD_Y = MARGIN
PANEL_X = BOARD_X + BOARD_W + MARGIN
PANEL_W = 220
WIN_W = PANEL_X + PANEL_W + MARGIN
WIN_H = BOARD_H + MARGIN * 2
FPS = 60

# ----------------------------------------------------------------- colours
BG = (10, 10, 18)
BOARD_BG = (16, 16, 28)
GRID = (32, 32, 50)
PANEL_BG = (20, 20, 34)
BORDER = (0, 200, 230)
TEXT = (230, 232, 245)
MUTED = (140, 145, 170)
ACCENT = (0, 240, 255)
WARN = (255, 80, 110)
GOLD = (255, 215, 80)

PIECE_COLORS = {
    "I": (0, 240, 255),
    "J": (50, 120, 255),
    "L": (255, 150, 30),
    "O": (255, 225, 40),
    "S": (50, 240, 100),
    "T": (190, 80, 255),
    "Z": (255, 60, 85),
}

# ----------------------------------------------------------------- input
DAS_MS = 170        # delay before a held key starts repeating
ARR_MS = 50         # repeat rate for left/right
SOFT_DROP_MS = 35   # repeat rate for soft drop

LEFT_KEYS = (pygame.K_LEFT, pygame.K_a)
RIGHT_KEYS = (pygame.K_RIGHT, pygame.K_d)
DOWN_KEYS = (pygame.K_DOWN, pygame.K_s)
ROT_CW_KEYS = (pygame.K_UP, pygame.K_x, pygame.K_w)
ROT_CCW_KEYS = (pygame.K_z, pygame.K_LCTRL, pygame.K_RCTRL)
HARD_DROP_KEYS = (pygame.K_SPACE,)
PAUSE_KEYS = (pygame.K_p, pygame.K_ESCAPE)

CONTROLS_HELP = (
    ("Left/Right, A/D", "Move"),
    ("Down, S", "Soft drop"),
    ("Space", "Hard drop"),
    ("Up, X, W", "Rotate right"),
    ("Z, Ctrl", "Rotate left"),
    ("P, Esc", "Pause"),
    ("M", "Mute sound"),
)

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


def _scale(color, factor):
    return tuple(max(0, min(255, int(c * factor))) for c in color)


class Sound:
    """Optional sound effects. Missing files or audio devices are fine."""

    def __init__(self) -> None:
        self.enabled = False
        self.muted = False
        self.effects: Dict[str, pygame.mixer.Sound] = {}
        self.has_music = False
        try:
            pygame.mixer.init()
        except pygame.error:
            return
        self.enabled = True
        for name in ("clear", "drop"):
            for ext in ("wav", "ogg", "mp3"):
                path = ASSETS_DIR / f"{name}.{ext}"
                if path.is_file():
                    try:
                        sound = pygame.mixer.Sound(str(path))
                        sound.set_volume(0.6)
                        self.effects[name] = sound
                        break
                    except pygame.error:
                        pass
        for name in ("music.ogg", "music.mp3"):
            path = ASSETS_DIR / name
            if path.is_file():
                try:
                    pygame.mixer.music.load(str(path))
                    pygame.mixer.music.set_volume(0.3)
                    pygame.mixer.music.play(-1)
                    self.has_music = True
                    break
                except pygame.error:
                    pass

    @property
    def available(self) -> bool:
        return self.enabled and (bool(self.effects) or self.has_music)

    def play(self, name: str) -> None:
        if self.enabled and not self.muted and name in self.effects:
            self.effects[name].play()

    def toggle_mute(self) -> None:
        if not self.enabled:
            return
        self.muted = not self.muted
        if self.has_music:
            if self.muted:
                pygame.mixer.music.pause()
            else:
                pygame.mixer.music.unpause()


class Renderer:
    def __init__(self, surface: pygame.Surface) -> None:
        self.surface = surface
        # Fonts are created once (not every frame). Font(None) is the font
        # bundled with pygame, so the game looks the same on every OS.
        self.f_title = pygame.font.Font(None, 44)
        self.f_label = pygame.font.Font(None, 22)
        self.f_value = pygame.font.Font(None, 38)
        self.f_small = pygame.font.Font(None, 20)
        self.f_big = pygame.font.Font(None, 64)
        self.f_mid = pygame.font.Font(None, 30)
        self.overlay = pygame.Surface((BOARD_W, BOARD_H), pygame.SRCALPHA)
        self.overlay.fill((5, 5, 12, 200))

    # ------------------------------------------------------------ primitives
    def _text(self, font, text, color, pos, anchor="topleft"):
        img = font.render(text, True, color)
        rect = img.get_rect(**{anchor: pos})
        self.surface.blit(img, rect)
        return rect

    def _glow_text(self, font, text, color, pos, anchor="center"):
        glow = _scale(color, 0.35)
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            self._text(font, text, glow, (pos[0] + dx, pos[1] + dy), anchor)
        return self._text(font, text, color, pos, anchor)

    def _block(self, x, y, color, size=CELL):
        rect = pygame.Rect(x + 1, y + 1, size - 2, size - 2)
        pygame.draw.rect(self.surface, _scale(color, 0.45), rect, border_radius=4)
        inner = rect.inflate(-size * 0.4, -size * 0.4)
        pygame.draw.rect(self.surface, _scale(color, 0.75), inner, border_radius=3)
        pygame.draw.rect(self.surface, color, rect, width=2, border_radius=4)

    def _ghost(self, x, y, color):
        rect = pygame.Rect(x + 3, y + 3, CELL - 6, CELL - 6)
        pygame.draw.rect(self.surface, _scale(color, 0.55), rect, width=2, border_radius=4)

    def _box(self, rect, title=None):
        pygame.draw.rect(self.surface, PANEL_BG, rect, border_radius=8)
        pygame.draw.rect(self.surface, _scale(BORDER, 0.45), rect, width=1, border_radius=8)
        if title:
            self._text(self.f_label, title, MUTED, (rect.x + 12, rect.y + 10))

    # ------------------------------------------------------------ sections
    def draw_board(self, game: Game, show_piece: bool) -> None:
        board_rect = pygame.Rect(BOARD_X, BOARD_Y, BOARD_W, BOARD_H)
        pygame.draw.rect(self.surface, BOARD_BG, board_rect)
        for c in range(1, COLS):
            x = BOARD_X + c * CELL
            pygame.draw.line(self.surface, GRID, (x, BOARD_Y), (x, BOARD_Y + BOARD_H))
        for r in range(1, VISIBLE_ROWS):
            y = BOARD_Y + r * CELL
            pygame.draw.line(self.surface, GRID, (BOARD_X, y), (BOARD_X + BOARD_W, y))

        for row in range(HIDDEN_ROWS, ROWS):
            for col in range(COLS):
                kind = game.board[row][col]
                if kind:
                    self._block(BOARD_X + col * CELL,
                                BOARD_Y + (row - HIDDEN_ROWS) * CELL,
                                PIECE_COLORS[kind])

        if show_piece and not game.game_over:
            piece = game.current
            color = PIECE_COLORS[piece.kind]
            for col, row in piece.cells(y=game.ghost_y()):
                if row >= HIDDEN_ROWS:
                    self._ghost(BOARD_X + col * CELL,
                                BOARD_Y + (row - HIDDEN_ROWS) * CELL, color)
            for col, row in piece.cells():
                if row >= HIDDEN_ROWS:
                    self._block(BOARD_X + col * CELL,
                                BOARD_Y + (row - HIDDEN_ROWS) * CELL, color)

        # neon frame
        pygame.draw.rect(self.surface, _scale(BORDER, 0.3), board_rect.inflate(8, 8),
                         width=3, border_radius=6)
        pygame.draw.rect(self.surface, BORDER, board_rect.inflate(2, 2), width=2)

    def draw_panel(self, game: Game, best: int, sound: Sound) -> None:
        x = PANEL_X
        self._glow_text(self.f_title, "NEONBLOCKS", ACCENT, (x + PANEL_W // 2, BOARD_Y + 18))

        y = BOARD_Y + 46
        box = pygame.Rect(x, y, PANEL_W, 64)
        self._box(box, "SCORE")
        self._text(self.f_value, f"{game.score:,}", TEXT, (box.right - 12, box.y + 30), "topright")

        y += 72
        box = pygame.Rect(x, y, PANEL_W, 64)
        self._box(box, "BEST")
        self._text(self.f_value, f"{max(best, game.score):,}", GOLD,
                   (box.right - 12, box.y + 30), "topright")

        y += 72
        half = (PANEL_W - 8) // 2
        for i, (label, value) in enumerate((("LEVEL", game.level), ("LINES", game.lines))):
            box = pygame.Rect(x + i * (half + 8), y, half, 64)
            self._box(box, label)
            self._text(self.f_value, str(value), TEXT, (box.right - 12, box.y + 30), "topright")

        y += 72
        box = pygame.Rect(x, y, PANEL_W, 112)
        self._box(box, "NEXT")
        self._draw_preview(game.next_kind, box)

        y += 120
        rows = [r for r in CONTROLS_HELP if r[0] != "M" or sound.available]
        box = pygame.Rect(x, y, PANEL_W, 34 + len(rows) * 21)
        self._box(box, "CONTROLS")
        cy = box.y + 32
        for key, action in rows:
            self._text(self.f_small, key, ACCENT, (box.x + 12, cy))
            self._text(self.f_small, action, TEXT, (box.right - 12, cy), "topright")
            cy += 21

        self._text(self.f_small, f"v{__version__}", _scale(MUTED, 0.7),
                   (x + PANEL_W, WIN_H - MARGIN + 4), "bottomright")

    def _draw_preview(self, kind: str, box: pygame.Rect) -> None:
        shape = ROTATIONS[kind][0]
        cells = [(c, r) for r, row in enumerate(shape) for c, v in enumerate(row) if v]
        size = 24
        min_c = min(c for c, _ in cells)
        max_c = max(c for c, _ in cells)
        min_r = min(r for _, r in cells)
        max_r = max(r for _, r in cells)
        w = (max_c - min_c + 1) * size
        h = (max_r - min_r + 1) * size
        ox = box.centerx - w // 2
        oy = box.y + 30 + (box.height - 30 - h) // 2
        for c, r in cells:
            self._block(ox + (c - min_c) * size, oy + (r - min_r) * size,
                        PIECE_COLORS[kind], size)

    def draw_overlay(self, title, lines, title_color=ACCENT, extra=None):
        self.surface.blit(self.overlay, (BOARD_X, BOARD_Y))
        cx = BOARD_X + BOARD_W // 2
        cy = BOARD_Y + BOARD_H // 2 - 60
        self._glow_text(self.f_big, title, title_color, (cx, cy))
        cy += 52
        if extra:
            text, color = extra
            self._text(self.f_mid, text, color, (cx, cy), "center")
            cy += 36
        for line in lines:
            self._text(self.f_small, line, TEXT, (cx, cy), "center")
            cy += 24


class App:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("NeonBlocks")
        pygame.display.set_icon(self._make_icon())
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        self.clock = pygame.time.Clock()
        self.renderer = Renderer(self.screen)
        self.sound = Sound()
        self.store = HighScoreStore()
        self.best = self.store.load()
        self.game = Game()
        self.state = "ready"          # ready | playing | paused | over
        self.new_best = False
        self.score_saved = False
        self._held_dir = 0            # -1 left, +1 right, 0 none
        self._held_timer = 0.0
        self._down_held = False
        self._down_timer = 0.0

    @staticmethod
    def _make_icon() -> pygame.Surface:
        icon = pygame.Surface((32, 32), pygame.SRCALPHA)
        for i, (c, r) in enumerate(((0, 1), (1, 1), (2, 1), (1, 0))):
            rect = pygame.Rect(2 + c * 9, 6 + r * 9, 9, 9)
            pygame.draw.rect(icon, PIECE_COLORS["T"], rect, border_radius=2)
        return icon

    # ------------------------------------------------------------- helpers
    def _release_keys(self) -> None:
        self._held_dir = 0
        self._down_held = False

    def _new_game(self) -> None:
        self._save_best_if_needed()
        self.game.reset()
        self.state = "playing"
        self.new_best = False
        self.score_saved = False
        self._release_keys()

    def _save_best_if_needed(self) -> None:
        if not self.score_saved and self.game.score > self.best:
            self.best = self.game.score
            self.new_best = True
            self.store.save(self.best)
        self.score_saved = True

    # --------------------------------------------------------------- input
    def _handle_keydown(self, key: int) -> bool:
        """Returns False when the app should quit."""
        if self.state == "ready":
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.state = "playing"
            elif key == pygame.K_ESCAPE:
                return False
            return True

        if self.state == "over":
            if key in (pygame.K_r, pygame.K_RETURN, pygame.K_KP_ENTER):
                self._new_game()
            elif key in (pygame.K_ESCAPE, pygame.K_q):
                return False
            return True

        if self.state == "paused":
            if key in PAUSE_KEYS:
                self.state = "playing"
            elif key == pygame.K_r:
                self._new_game()
            elif key == pygame.K_q:
                return False
            elif key == pygame.K_m:
                self.sound.toggle_mute()
            return True

        # playing
        g = self.game
        if key in PAUSE_KEYS:
            self.state = "paused"
            self._release_keys()
        elif key in LEFT_KEYS:
            g.move(-1)
            self._held_dir, self._held_timer = -1, 0.0
        elif key in RIGHT_KEYS:
            g.move(1)
            self._held_dir, self._held_timer = 1, 0.0
        elif key in DOWN_KEYS:
            g.soft_drop()
            self._down_held, self._down_timer = True, 0.0
        elif key in ROT_CW_KEYS:
            g.rotate(1)
        elif key in ROT_CCW_KEYS:
            g.rotate(-1)
        elif key in HARD_DROP_KEYS:
            g.hard_drop()
        elif key == pygame.K_m:
            self.sound.toggle_mute()
        return True

    def _handle_keyup(self, key: int) -> None:
        if key in LEFT_KEYS and self._held_dir == -1:
            self._held_dir = 0
            # fall back to the other direction if it is still pressed
            if any(pygame.key.get_pressed()[k] for k in RIGHT_KEYS):
                self._held_dir, self._held_timer = 1, 0.0
        elif key in RIGHT_KEYS and self._held_dir == 1:
            self._held_dir = 0
            if any(pygame.key.get_pressed()[k] for k in LEFT_KEYS):
                self._held_dir, self._held_timer = -1, 0.0
        elif key in DOWN_KEYS:
            self._down_held = False

    def _auto_repeat(self, dt: float) -> None:
        if self._held_dir:
            self._held_timer += dt
            # First repeat after DAS_MS, then one move every ARR_MS.
            while self._held_timer >= DAS_MS:
                self._held_timer -= ARR_MS
                if not self.game.move(self._held_dir):
                    self._held_timer = DAS_MS - ARR_MS
                    break
        if self._down_held:
            self._down_timer += dt
            while self._down_timer >= SOFT_DROP_MS:
                self._down_timer -= SOFT_DROP_MS
                if not self.game.soft_drop():
                    self._down_timer = 0.0
                    break

    # ---------------------------------------------------------------- loop
    def step(self, dt: float) -> bool:
        """Process one frame. Returns False when the app should quit."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.WINDOWFOCUSLOST and self.state == "playing":
                self.state = "paused"
                self._release_keys()
            elif event.type == pygame.KEYDOWN:
                if not self._handle_keydown(event.key):
                    return False
            elif event.type == pygame.KEYUP:
                self._handle_keyup(event.key)

        if self.state == "playing":
            self._auto_repeat(dt)
            self.game.update(dt)
            for ev in self.game.pop_events():
                self.sound.play("clear" if ev == "clear" else "drop")
            if self.game.game_over:
                self.state = "over"
                self._release_keys()
                self._save_best_if_needed()

        self.draw()
        return True

    def draw(self) -> None:
        r = self.renderer
        self.screen.fill(BG)
        r.draw_board(self.game, show_piece=self.state != "ready")
        r.draw_panel(self.game, self.best, self.sound)
        if self.state == "ready":
            r.draw_overlay("READY?", ["Press Enter or Space to start",
                                      "Esc to quit"])
        elif self.state == "paused":
            r.draw_overlay("PAUSED", ["P / Esc  resume", "R  restart", "Q  quit"])
        elif self.state == "over":
            score = f"{self.game.score:,}"
            extra = ((f"NEW BEST!  {score}", GOLD) if self.new_best
                     else (f"Score  {score}", TEXT))
            r.draw_overlay("GAME OVER", ["R / Enter  play again", "Esc / Q  quit"],
                           title_color=WARN, extra=extra)
        pygame.display.flip()

    def run(self) -> None:
        try:
            running = True
            while running:
                dt = self.clock.tick(FPS)
                # Avoid a huge jump after the window was dragged or stalled.
                running = self.step(min(dt, 100))
        finally:
            if self.state in ("playing", "paused"):
                self._save_best_if_needed()
            pygame.quit()


def main() -> int:
    try:
        App().run()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
