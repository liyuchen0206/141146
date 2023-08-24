import sys
import os
import logging
import time
from abc import abstractmethod

RESULTS = [WIN, LOSS, DRAW] = range(3)
SCORES = [1, 0, 0.5]


class EngineMatch:
    """The base class to run an engine match."""
    def __init__(self,
                 variant,
                 engine1,
                 engine2,
                 e1_options,
                 e2_options,
                 time=10000,
                 inctime=100,
                 depth=None,
                 nodes=None,
                 movetime=None,
                 nodestime=0,
                 draw_after=400,
                 draw_move_limit=-1,
                 draw_score_limit=-1,
                 win_move_limit=-1,
                 win_score_limit=-1,
                 verbosity=0):
        self.variant = variant
        self.engine1 = engine1
        self.engine2 = engine2
        self.e1_options = e1_options
        self.e2_options = e2_options
        self.time = time
        self.inc = inctime
        self.depth = depth
        self.nodes = nodes
        self.movetime = movetime
        self.nodestime = nodestime
        self.verbosity = verbosity
        self.engine_paths = [os.path.abspath(self.engine1), os.path.abspath(self.engine2)]
        self.engine_options = [dict(self.e1_options), dict(self.e2_options)]
        self.out = sys.stdout
        self.book = True
        self.draw_after = draw_after
        self.draw_move_limit = draw_move_limit
        self.draw_score_limit = draw_score_limit
        self.win_move_limit = win_move_limit
        self.win_score_limit = win_score_limit

        self.engines = []
        self.time_losses = []
        self.scores = [0, 0, 0]
        self.r = []

        # check if it's not on Windows
        if os.name != 'nt':
            os.system("chmod +x " + self.engine1)
            os.system("chmod +x " + self.engine2)

        if self.verbosity > 2:
            logging.basicConfig(level=logging.DEBUG if self.verbosity > 3 else logging.INFO)

    def init_engines(self):
        """Setup engines and info handlers."""
        for path, options in zip(self.engine_paths, self.engine_options):
            if not os.path.exists(path) or not os.path.isfile(path):
                raise Exception(f"Engine not found: {path}")
            engine = self.do_init_engine(path, options)
            assert engine is not None
            self.engines.append(engine)
            self.time_losses.append(0)

    def check_engines_ok(self):
        """Check if all engines are ok."""
        for engine in self.engines:
            if not self.do_check_engine(engine):
                return False
        return True

    def destroy_engines(self):
        """Destroy all engines."""
        for engine in self.engines:
            self.do_destroy_engine(engine)

    def _play_one_game(self, white, black, pos):
        """Play a game and return the game result from white's point of view."""
        limits = {
            'wtime': self.time,
            'btime': self.time,
            'winc': self.inc,
            'binc': self.inc,
            'depth': self.depth,
            'nodes': self.nodes,
            'movetime': self.movetime
        }
        for index, engine in enumerate(self.engines):
            if self.verbosity > 1:
                self.out.write(f'Engine {index} init: pos="{pos}" limits={limits}\n')
            self.do_init_game(engine, pos, limits)
        opening_offset = self.get_offset_from_pos(pos)
        win_move_count = 0
        loss_move_count = 0
        draw_move_count = 0
        bestmoves = []
        game_record = {'fen': pos, 'moves': [], 'result': None, 'bestmoves': bestmoves}
        while True:
            index = white if (opening_offset + len(bestmoves)) % 2 == 0 else black
            engine = self.engines[index]

            start_time = time.time()
            results = self.do_play_game(engine, pos, bestmoves, limits)
            time_used = int((time.time() - start_time) * 1000)

            if results == 'timeout':
                self.time_losses[index] += 1
                game_record['result'] = -2 if index == white else 2
                game_record['comment'] = 'Lose by deadline timeout'
                return LOSS, game_record

            # record engine's move
            score = results.get('score', None)
            game_record['moves'].append((results['bestmove'], score, time_used))
            bestmoves.append(results['bestmove'])

            if self.verbosity > 1:
                self.out.write(f"Engine {index} ({time_used} ms): {results}\n")

            # check for mate (only recognize the mate admitted by the losing side)
            if results.get('mate', 0) < 0:
                if index == white:
                    game_record['result'] = -1
                    return LOSS, game_record
                else:
                    game_record['result'] = 1
                    return WIN, game_record
            elif score is not None:
                white_score = score if index == white else -score
                # check for end of game draw conditions
                if white_score == 0 and 'pv' in results and len(results['pv']) == 0:
                    game_record['result'] = 0
                    return DRAW, game_record
                # check for draw adjudication
                elif self.draw_move_limit > 0 and abs(white_score) <= self.draw_score_limit:
                    draw_move_count += 1
                    if draw_move_count >= self.draw_move_limit:
                        game_record['result'] = 0
                        return DRAW, game_record
                # check for win adjudication for white perspective
                elif self.win_move_limit > 0 and white_score >= self.win_score_limit:
                    win_move_count += 1
                    if win_move_count >= self.win_move_limit:
                        return (WIN if index == white else LOSS), game_record
                # check for loss adjudication for white perspective
                elif self.win_move_limit > 0 and white_score <= -self.win_score_limit:
                    loss_move_count += 1
                    if loss_move_count >= self.win_move_limit:
                        return (LOSS if index == white else WIN), game_record
                # refresh move counters
                else:
                    win_move_count = 0
                    loss_move_count = 0
                    draw_move_count = 0

            # adjust time remaining on clock and check time loss
            if limits['wtime'] is not None and limits['btime'] is not None:
                if index == white:
                    limits['wtime'] += self.inc - results.get('time', time_used)
                    if limits['wtime'] < 0:
                        self.time_losses[index] += 1
                        game_record['result'] = -2
                        game_record['comment'] = 'Lose by timeout'
                        return LOSS, game_record
                else:
                    limits['btime'] += self.inc - results.get('time', time_used)
                    if limits['btime'] < 0:
                        self.time_losses[index] += 1
                        game_record['result'] = 2
                        game_record['comment'] = 'Lose by timeout'
                        return WIN, game_record

            # check for draw by total move count
            if self.draw_after >= 0 and len(bestmoves) >= self.draw_after:
                game_record['result'] = 0
                game_record['comment'] = f'Draw by move count >= {self.draw_after}'
                return DRAW, game_record

    def run_game(self, white, black, pos):
        """Run a game, record and return the result."""
        res, game_record = self._play_one_game(white, black, pos)
        if self.verbosity > 0:
            self.out.write(f"Game {sum(self.scores) + 1} ({self.variant}):\nPos: {pos}\n"
                           f"Bestmoves: {' '.join(game_record['bestmoves'])}\n")

        self.r.append(SCORES[res] if white == 0 else 1 - SCORES[res])
        if white == 0 or res == DRAW:
            self.scores[res] += 1
        else:
            self.scores[1 - res] += 1
        if res == DRAW:
            return "draw", game_record
        elif res == WIN and white == 0 or res == LOSS and white == 1:
            return "win", game_record
        else:
            return "lose", game_record

    @abstractmethod
    def do_init_engine(self, engine_path, engine_options):
        """Overwrite: Initialize an engine from path and returns the engine object."""
        pass

    @abstractmethod
    def do_check_engine(self, engine) -> bool:
        """Overwrite: Check whether the engine status is ok."""
        return True

    @abstractmethod
    def do_destroy_engine(self, engine):
        """Overwrite: Destroy the engine."""
        pass

    @abstractmethod
    def do_init_game(self, engine, pos, limits):
        """
        Overwrite: Prepare engines for next game.
        :param engine: engine object
        :param pos: starting position
        :param limits: various time limits
        """
        pass

    @abstractmethod
    def get_offset_from_pos(self, pos):
        """
        Overwrite: Return offset (game ply) from opening position.
        This is used to determine the first mover (white or black) in a game.
        """
        pass

    @abstractmethod
    def do_play_game(self, engine, pos, bestmoves, limits):
        """
        Overwrite: Play a game and return a dict of all results.
        :param engine: Engine object
        :param pos: Opening position string
        :param bestmoves: List of previous played best moves
        :param limits: Dict of limits, including depth, nodes, movetime, wtime, btime, winc, binc
            At least one of depth, nodes, movetime, wtime/btime must be set.
        :return: a dict of all results including
            bestmove: an object representing the best move (can be string or a chess.Move)
            score: the score of the best move, None if there is no score
            mate: moves to mate, positive/negative for win/lose, or 0 if there is no mate
            pv: a list of moves in the principal variation, pv[0] should be the best move
            time: time used for this move in milliseconds
        """
        pass


if __name__ == "__main__":
    pass
