import re
import gomoku.piskpipe as piskpipe
from match.base_match import EngineMatch

RESULTS = [WIN, LOSS, DRAW] = range(3)
SCORES = [1, 0, 0.5]


class GomokuEngineMatch(EngineMatch):
    """Compare two piskvork engines by running an engine match."""
    def __init__(self,
                 rule,
                 board_size,
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
                 verbosity=0):
        assert rule in ["freestyle", "standard", "renju"]
        super().__init__(f"{rule}{board_size}", engine1, engine2, e1_options, e2_options, time,
                         inctime, depth, nodes, movetime, nodestime, draw_after, draw_move_limit,
                         draw_score_limit, win_move_limit, win_score_limit, verbosity)
        self.rule = 0 if rule == "freestyle" else 1 if rule == "standard" else 4
        self.board_size = board_size

    def do_init_engine(self, engine_path, engine_options):
        engine = piskpipe.popen_engine(engine_path)
        options = {"rule": self.rule, "show_detail": 2, "max_memory": 350 * 1024 * 1024}
        options.update(engine_options)
        if self.verbosity > 1:
            self.out.write(f"Engine options: {options}\n")
        engine.info(options, async_callback=False)
        return engine

    def do_check_engine(self, engine) -> bool:
        return engine.is_alive()

    def do_destroy_engine(self, engine):
        if engine.is_alive():
            try:
                engine.end(async_callback=5.0)
            except piskpipe.TimeoutError:
                engine.kill()

    def do_init_game(self, engine, pos, limits):
        limit_options = {}
        if limits['depth']:
            limit_options['max_depth'] = limits['depth']
        if limits['nodes']:
            limit_options['max_node'] = limits['nodes']
        if limits['movetime']:
            limit_options['timeout_turn'] = limits['movetime']
            limit_options['timeout_match'] = 0
        elif limits['wtime']:
            limit_options['timeout_turn'] = limits['wtime']
            limit_options['timeout_match'] = limits['wtime']
            if limits['winc']:
                limit_options['time_increment'] = limits['winc']
        engine.info(limit_options, async_callback=False)

        try:
            engine.start(self.board_size, async_callback=5.0)
        except piskpipe.TimeoutError as e:
            engine.kill()
            raise RuntimeError("Engine timeouted at start command.")

    def get_offset_from_pos(self, pos):
        return len(re.findall(r"([a-z][1-9][0-9]?)", pos.lower()))

    def do_play_game(self, engine, pos, bestmoves, limits):
        engine.clear_messages()
        color = 'w' if (self.get_offset_from_pos(pos) + len(bestmoves)) % 2 == 0 else 'b'

        # Set the deadline to the time limit plus a tolerance.
        tolerance = 5.0
        if limits['movetime']:
            deadline_time = limits['movetime'] * 0.001 + tolerance
        elif limits[f'{color}time']:
            engine.info({'time_left': limits[f'{color}time']}, async_callback=False)
            deadline_time = (limits[f'{color}time'] + limits[f'{color}inc']) * 0.001 + tolerance
        else:
            deadline_time = None

        try:
            if len(bestmoves) < 2:
                bestmove = engine.board(pos + "".join(bestmoves),
                                        start_thinking=True,
                                        async_callback=deadline_time)
            else:
                bestmove = engine.turn(bestmoves[-1], async_callback=deadline_time)
        except piskpipe.TimeoutError as e:
            engine.kill()
            if self.verbosity > 0:
                self.out.write(f"Force killed timeout engine. Moves: " + " ".join(bestmoves) + '\n')
            return 'timeout'

        for pvinfo in reversed(engine.infos):
            if pvinfo["pvidx"] == 0:
                mate = pvinfo.get("mate", 0)
                score = 30000 - mate if mate > 0 else -30000 - mate if mate < 0 else pvinfo["eval"]
                return {
                    "bestmove": bestmove,
                    "score": score,
                    "mate": mate,
                    "pv": pvinfo["bestline"],
                    "time": pvinfo["totaltime"]
                }

        if pos and self.verbosity > 0:
            self.out.write(f"Engine did not return pv info. Moves: " + " ".join(bestmoves) + '\n')
        return {"bestmove": bestmove}  # no pv info
