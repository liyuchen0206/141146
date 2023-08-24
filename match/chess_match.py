import logging
import time
import chess
from match.base_match import EngineMatch

RESULTS = [WIN, LOSS, DRAW] = range(3)
SCORES = [1, 0, 0.5]


class ChessEngineMatch(EngineMatch):
    """Compare two UCI engines by running an engine match."""
    def __init__(self,
                 engine1,
                 engine2,
                 e1_options,
                 e2_options,
                 time=10000,
                 inctime=100,
                 depth=None,
                 nodes=None,
                 movetime=-1,
                 nodestime=0,
                 draw_after=400,
                 draw_move_limit=-1,
                 draw_score_limit=-1,
                 win_move_limit=-1,
                 win_score_limit=-1,
                 draw_as_black_win=False,
                 mate1_judge=False,
                 verbosity=0):
        import chess.uci
        super().__init__("chess", engine1, engine2, e1_options, e2_options, time, inctime, depth,
                         nodes, movetime, nodestime, draw_after, draw_move_limit, draw_score_limit,
                         win_move_limit, win_score_limit, verbosity)
        if self.verbosity > 2:
            chess.uci.LOGGER.setLevel(logging.DEBUG)
        self.draw_as_black_win = draw_as_black_win
        self.mate1_judge = mate1_judge

    @staticmethod
    def get_oppo(side):
        return 'w' if side == 'b' else 'b'

    def _play_one_game(self, white, black, pos):
        """Play a game and return the game result from white's point of view."""
        limits = {
            'wtime': self.time if self.time > 0 else None,
            'btime': self.time if self.time > 0 else None,
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
        board = chess.Board(pos)
        game_record = {'order': white, 'fen': pos, 'moves': [], 'result': None, 'bestmoves': bestmoves, 'comment': ''}
        while True:
            index = white if (opening_offset + len(bestmoves)) % 2 == 0 else black
            engine = self.engines[index]

            start_time = time.time()
            results = self.do_play_game(engine, pos, bestmoves, limits)
            time_used = int((time.time() - start_time) * 1000)

            # record engine's move
            score = results.get('score', None)
            if results["bestmove"] != "(none)":
                game_record['moves'].append({
                    'move': results['bestmove'],
                    'score': score,
                    'time': results.get('time'),
                    'rtime': time_used,
                    'depth': results.get('depth'),
                    'seldepth': results.get('seldepth'),
                    'nodes': results.get('nodes'),
                    'nps': results.get('nps'),
                    'hashfull': results.get('hashfull'),
                })
            bestmoves.append(results['bestmove'])

            if self.verbosity > 1:
                self.out.write(f"Engine {index} ({time_used} ms): {results}\n")

            # check for mate (only recognize the mate admitted by the losing side)
            if results.get('mate', 0) == -1:
                if index == white:
                    game_record['result'] = -1
                    game_record['comment'] = 'Lose by mate'
                    return LOSS, game_record
                else:
                    game_record['result'] = 1
                    game_record['comment'] = 'Win by mate'
                    return WIN, game_record
            elif self.mate1_judge and results.get('mate', 0) == 1:
                if index == white:
                    game_record['result'] = 1
                    game_record['comment'] = 'Win by mate'
                    return WIN, game_record
                else:
                    game_record['result'] = -1
                    game_record['comment'] = 'Lose by mate'
                    return LOSS, game_record
            elif score is not None:
                white_score = score if index == white else -score
                # check for end of game draw conditions
                if white_score == 0 and 'pv' in results and len(results['pv']) == 0:
                    if self.draw_as_black_win:
                        game_record['result'] = -1
                        game_record['comment'] = 'Lose by draw (draw as black win)'
                        return LOSS, game_record
                    else:
                        game_record['result'] = 0
                        game_record['comment'] = 'Draw by end of game'
                        return DRAW, game_record
                # check for draw adjudication
                elif self.draw_move_limit > 0 and abs(white_score) <= self.draw_score_limit:
                    draw_move_count += 1
                    if draw_move_count >= self.draw_move_limit:
                        if self.draw_as_black_win:
                            game_record['result'] = -1
                            game_record['comment'] = 'Lose by draw (draw as black win)'
                            return LOSS, game_record
                        else:
                            game_record['result'] = 0
                            game_record['comment'] = f'Draw by score <= {self.draw_score_limit} for ' \
                                                     f'{self.draw_move_limit} moves'
                            return DRAW, game_record
                # check for win adjudication for white perspective
                elif self.win_move_limit > 0 and white_score >= self.win_score_limit:
                    win_move_count += 1
                    if win_move_count >= self.win_move_limit:
                        game_record['result'] = (1 if index == white else 0)
                        game_record['comment'] = f'Win by score >= {self.win_score_limit} for ' \
                                                 f'{self.win_move_limit} moves'
                        return (WIN if index == white else LOSS), game_record
                # check for loss adjudication for white perspective
                elif self.win_move_limit > 0 and white_score <= -self.win_score_limit:
                    loss_move_count += 1
                    if loss_move_count >= self.win_move_limit:
                        game_record['result'] = (0 if index == white else 1)
                        game_record['comment'] = f'Loss by score <= {-self.win_score_limit} for ' \
                                                 f'{self.win_move_limit} moves'
                        return (LOSS if index == white else WIN), game_record
                # refresh move counters
                else:
                    win_move_count = 0
                    loss_move_count = 0
                    draw_move_count = 0

            # update board and judge for rule60 and repetition
            if results['bestmove'] != "(none)":
                board.push(chess.Move.from_uci(results['bestmove']))

            # game judgement
            if board.can_claim_fifty_moves() or board.is_repetition(3) or \
                    board.is_insufficient_material():
                if self.draw_as_black_win:
                    game_record['result'] = -1
                    game_record['comment'] = 'Lose by draw (draw as black win)'
                    return LOSS, game_record
                else:
                    game_record['result'] = 0
                    game_record['comment'] = 'Draw'
                    return DRAW, game_record

            # adjust time remaining on clock and check time loss
            if limits['wtime'] is not None and limits['btime'] is not None:
                if index == white:
                    if self.nodestime > 0:
                        limits['wtime'] += self.inc - int(results.get("time") / self.nodestime)
                    else:
                        limits['wtime'] += self.inc - results.get("time", time_used)
                    if limits['wtime'] < 0:
                        self.time_losses[index] += 1
                        game_record['result'] = -2
                        game_record['comment'] = 'Lose by Time loss'
                        return LOSS, game_record
                else:
                    if self.nodestime > 0:
                        limits['btime'] += self.inc - int(results.get("time") / self.nodestime)
                    else:
                        limits['btime'] += self.inc - results.get("time", time_used)
                    if limits['btime'] < 0:
                        self.time_losses[index] += 1
                        game_record['result'] = 2
                        game_record['comment'] = 'Win by time loss'
                        return WIN, game_record

    def do_init_engine(self, engine_path, engine_options):
        import chess.uci
        engine = chess.uci.popen_engine(engine_path)
        engine.uci(async_callback=False)
        engine.setoption(engine_options, async_callback=False)
        engine.info_handlers.append(chess.uci.InfoHandler())
        return engine

    def do_check_engine(self, engine) -> bool:
        return engine.is_alive()

    def do_destroy_engine(self, engine):
        engine.quit(async_callback=False)

    def do_init_game(self, engine, pos, limits):
        engine.ucinewgame()

    def get_offset_from_pos(self, pos):
        parts = pos.split(' ')
        if len(parts) >= 2 and parts[1] == 'b':
            return 1
        return 0

    def do_play_game(self, engine, pos, bestmoves, limits):
        fen = pos if pos.startswith("fen ") else "fen " + pos
        engine.send_line("position " + fen + " moves " + " ".join(bestmoves))
        if engine.chess_db:
            engine.chess_db_pos = pos + " moves " + " ".join(bestmoves)

        bestmove, ponder = engine.go(depth=limits['depth'],
                                     nodes=limits['nodes'],
                                     movetime=limits['movetime'],
                                     wtime=limits['wtime'],
                                     btime=limits['btime'],
                                     winc=limits['winc'],
                                     binc=limits['binc'])

        with engine.info_handlers[0] as info:
            if 'string' in info:
                if 'classical' in info['string']:
                    raise Exception("Failed loading NNUE")

            if 1 in info["score"]:
                score = info["score"][1].cp
                mate = info["score"][1].mate if score is None else 0
                score = 30000 - mate if mate > 0 else -30000 - mate if mate < 0 else score
                return {
                    "bestmove": bestmove,
                    "score": score,
                    "mate": mate,
                    "pv": info["pv"],
                    "depth": info.get("depth", -1),
                    "seldepth": info.get("seldepth", -1),
                    "nodes": info.get("nodes", -1),
                    "nps": info.get("nps", -1),
                    "hashfull": info.get("hashfull", -1),
                    "time": info.get("time", -1)
                }
            else:
                raise Exception("Engine does not return a score.\nMoves: " + " ".join(bestmoves))