import builtins
import json
import os
import threading
import time
import zipfile
import random
import traceback
import shutil

NO_OUTPUT = False
VERBOSITY = 0

DEFAULT_BOOK = {
    "xiangqi": "3mvs_140-200_150560",
    "jieqi": "1mvs",
    "chess": "UHO_XXL_+0.90_+1.19",
    "gomoku_freestyle20": "f20-100M-40k",
    "gomoku_freestyle15": "f15-base-8k",
    "gomoku_standard15": "s15-100M-40k",
    "gomoku_renju15": "r15-100M-40k",
}

SIDE_NAME = {
    "xiangqi": ["Red", "Black"],
    "jieqi": ["Red", "Black"],
    "chess": ["White", "Black"],
    "gomoku_freestyle20": ["Black", "White"],
    "gomoku_freestyle15": ["Black", "White"],
    "gomoku_standard15": ["Black", "White"],
    "gomoku_renju15": ["Black", "White"],
}


def print(*args, **kwargs):
    if not NO_OUTPUT:
        builtins.print(*args, **kwargs)


class Tester:
    def __init__(self):
        self.win = 0
        self.lose = 0
        self.draw = 0
        self.first_stats = [0, 0, 0]
        self.ptnml = [0, 0, 0, 0, 0]
        self.working_workers = 0
        self.need_exit = False
        self.started = False
        self.dead_threads = []
        self.task_queue = []
        self.task_results = {}
        self.lock = threading.Lock()
        self.thread_list = []
        self.enable = True
        self.abandon_list = []
        self.books_set = {
            "xiangqi": self.load_books("./books/xiangqi", extensions=[".txt", ".epd"]),
            "jieqi": self.load_books("./books/jieqi", extensions=[".txt", ".epd"]),
            "chess": self.load_books("./books/chess", extensions=[".txt", ".epd"]),
            "gomoku_freestyle20": self.load_books("./books/gomoku/f20", extensions=[".txt"]),
            "gomoku_freestyle15": self.load_books("./books/gomoku/f15", extensions=[".txt"]),
            "gomoku_standard15": self.load_books("./books/gomoku/s15", extensions=[".txt"]),
            "gomoku_renju15": self.load_books("./books/gomoku/r15", extensions=[".txt"]),
        }

    def load_books(self, book_dir, extensions=[".txt"]) -> dict:
        books = {}
        for file in os.listdir(book_dir):
            book_path = os.path.join(book_dir, file)
            fn_noext = os.path.splitext(file)[0]
            if any([file.endswith(ext) for ext in extensions]):
                with open(book_path, "r") as f:
                    text = f.read()
                    books[fn_noext] = [s for s in text.splitlines() if s]
            elif file.endswith(".zip"):
                with zipfile.ZipFile(book_path, "r") as f:
                    lines = []
                    for text_filename in f.namelist():
                        text = f.read(text_filename).decode("utf-8")
                        lines += [s for s in text.splitlines() if s]
                    books[fn_noext] = lines
        return books

    def add_task(self,
                 task_id,
                 weight,
                 engine,
                 baseline_weight,
                 baseline_engine,
                 depth=None,
                 nodes=None,
                 game_time=10000,
                 inc_time=100,
                 move_time=None,
                 nodestime=0,
                 hash=256,
                 thread_count=2,
                 uci_ops=None,
                 baseline_uci_ops=None,
                 draw_move_limit=-1,
                 draw_score_limit=-1,
                 win_move_limit=-1,
                 win_score_limit=-1,
                 draw_as_black_win=False,
                 mate1_judge=False,
                 count=6,
                 book=None,
                 variant="xiangqi"):
        book = book if book in self.books_set[variant] else DEFAULT_BOOK[variant]
        if not book:
            fens = ["" for _ in range(count // 2)]
        else:
            if len(self.books_set[variant][book]) >= count // 2:
                fens = random.sample(self.books_set[variant][book], count // 2)
            else:
                book_extend = self.books_set[variant][book] * (count // 2)
                fens = random.sample(book_extend, count // 2)
        if variant == "jieqi":
            from jieqi.game import JieQi
            fens = [json.dumps(JieQi.generate_random_board_info_from_fen(fen)) for fen in fens]
        if task_id not in self.task_results:
            self.task_results[task_id] = {}
        for fen in fens:
            if fen in self.task_results[task_id]:
                continue
            for order in range(2):
                self.task_queue.append({
                    "task_id": task_id,
                    "variant": variant,
                    "fen": fen,
                    "order": order,
                    "options": {
                        "engine": engine,
                        "weight": weight,
                        "baseline_engine": baseline_engine,
                        "baseline_weight": baseline_weight,
                        "depth": depth,
                        "nodes": nodes,
                        "game_time": game_time,
                        "inc_time": inc_time,
                        "move_time": move_time,
                        "nodestime": nodestime,
                        "hash": hash,
                        "thread_count": thread_count,
                        "uci_ops": uci_ops,
                        "baseline_uci_ops": baseline_uci_ops,
                        "draw_move_limit": draw_move_limit,
                        "draw_score_limit": draw_score_limit,
                        "win_move_limit": win_move_limit,
                        "win_score_limit": win_score_limit,
                        "draw_as_black_win": draw_as_black_win,
                        "mate1_judge": mate1_judge,
                    },
                    "error_count": 0
                })
            self.task_results[task_id][fen] = {0: "", 1: ""}

    def remove_tasks(self, task_ids):
        if not task_ids:
            return
        for task in list(self.task_queue):
            if task["task_id"] in task_ids:
                self.task_queue.remove(task)
        for task_id in task_ids:
            if task_id in self.task_results:
                del self.task_results[task_id]

    def get_task_ids_in_queue(self):
        task_ids = []
        for task in self.task_queue:
            if task["task_id"] not in task_ids:
                task_ids.append(task["task_id"])
        return task_ids

    def process_match(self, variant, order, fen, engine, baseline_engine, weight, baseline_weight, ops):
        depth = ops["depth"]
        nodes = ops["nodes"]
        game_time = ops["game_time"]
        inc_time = ops["inc_time"]
        move_time = ops["move_time"]
        if depth is not None and depth <= 0: depth = None
        if nodes is not None and nodes <= 0: nodes = None
        if move_time is not None and move_time <= 0: move_time = None
        hash = ops["hash"]
        draw_move_limit = ops["draw_move_limit"]
        draw_score_limit = ops["draw_score_limit"]
        win_move_limit = ops["win_move_limit"]
        win_score_limit = ops["win_score_limit"]
        options = ops["uci_ops"] or {}
        baseline_options = ops["baseline_uci_ops"] or {}
        draw_as_black_win = ops["draw_as_black_win"]
        mate1_judge = ops["mate1_judge"]
        nodestime = ops["nodestime"]
        thread_count = 1

        if variant == "xiangqi":
            from match.xiangqi_match import XiangQiEngineMatch
            uci_options = {"Hash": hash, "Threads": thread_count,
                           "EvalFile": weight, "Variant": "xiangqi",
                           "nodestime": nodestime}
            uci_options.update(options)
            baseline_uci_options = {"Hash": hash, "Threads": thread_count,
                                    "EvalFile": baseline_weight, "Variant": "xiangqi",
                                    "nodestime": nodestime}
            baseline_uci_options.update(baseline_options)
            match = XiangQiEngineMatch(engine,
                                       baseline_engine,
                                       uci_options,
                                       baseline_uci_options,
                                       time=game_time,
                                       inctime=inc_time,
                                       depth=depth,
                                       nodes=nodes,
                                       movetime=move_time,
                                       nodestime=nodestime,
                                       draw_move_limit=draw_move_limit,
                                       draw_score_limit=draw_score_limit,
                                       win_move_limit=win_move_limit,
                                       win_score_limit=win_score_limit,
                                       draw_as_black_win=draw_as_black_win,
                                       mate1_judge=mate1_judge,
                                       verbosity=VERBOSITY)
        elif variant == "jieqi":
            from match.jieqi_match import JieQiEngineMatch
            uci_options = {"Hash": hash, "Threads": thread_count,
                           "EvalFile": weight, "nodestime": nodestime}
            uci_options.update(options)
            baseline_uci_options = {"Hash": hash, "Threads": thread_count,
                                    "EvalFile": baseline_weight, "nodestime": nodestime}
            baseline_uci_options.update(baseline_options)
            match = JieQiEngineMatch(engine,
                                     baseline_engine,
                                     uci_options,
                                     baseline_uci_options,
                                     time=game_time,
                                     inctime=inc_time,
                                     depth=depth,
                                     nodes=nodes,
                                     movetime=move_time,
                                     nodestime=nodestime,
                                     draw_move_limit=draw_move_limit,
                                     draw_score_limit=draw_score_limit,
                                     win_move_limit=win_move_limit,
                                     win_score_limit=win_score_limit,
                                     verbosity=VERBOSITY)
        elif variant == "chess":
            from match.chess_match import ChessEngineMatch
            uci_options = {"Hash": hash, "Threads": thread_count,
                           "nodestime": nodestime}
            if weight:
                uci_options.update({
                    "EvalFile": weight
                })
            uci_options.update(options)
            baseline_uci_options = {"Hash": hash, "Threads": thread_count,
                                    "nodestime": nodestime}
            if baseline_weight:
                baseline_uci_options.update({
                    "EvalFile": baseline_weight
                })
            baseline_uci_options.update(baseline_options)
            match = ChessEngineMatch(engine,
                                     baseline_engine,
                                     uci_options,
                                     baseline_uci_options,
                                     time=game_time,
                                     inctime=inc_time,
                                     depth=depth,
                                     nodes=nodes,
                                     movetime=move_time,
                                     nodestime=nodestime,
                                     draw_move_limit=draw_move_limit,
                                     draw_score_limit=draw_score_limit,
                                     win_move_limit=win_move_limit,
                                     win_score_limit=win_score_limit,
                                     draw_as_black_win=draw_as_black_win,
                                     mate1_judge=mate1_judge,
                                     verbosity=VERBOSITY)
        elif variant.startswith("gomoku"):
            from match.gomoku_match import GomokuEngineMatch
            postfix = variant.split("_")[1]
            rule, board_size = postfix[:-2], int(postfix[-2:])

            def prepare_directory_if_not_ready(engine, weight):
                engine_name = os.path.basename(engine)
                dir = os.path.splitext(weight)[0] + '-' + os.path.splitext(engine_name)[0]
                engine_path = os.path.join(dir, engine_name)
                ready_path = os.path.join(dir, "ready")
                if not os.path.isdir(dir) or not os.path.isfile(ready_path):
                    try:
                        os.makedirs(dir, exist_ok=False)
                        # weight is considered as a zipped file of multiple weights and config
                        with zipfile.ZipFile(weight, "r") as f:
                            f.extractall(dir)
                        shutil.copyfile(engine, engine_path)
                        open(ready_path, 'a').close()  # mark this dir as ready to use
                    except FileExistsError:
                        # Wait for other threads to complete extracting and copying
                        while not os.path.isfile(ready_path):
                            time.sleep(1.0)
                return engine_path

            engine = prepare_directory_if_not_ready(engine, weight)
            baseline_engine = prepare_directory_if_not_ready(baseline_engine, baseline_weight)
            hash_bytes = hash * 1024 * 1024  # MB to Bytes
            pisk_options = {"max_memory": hash_bytes, "thread_num": thread_count}
            baseline_pisk_options = {"max_memory": hash_bytes, "thread_num": thread_count}
            pisk_options.update(options)
            baseline_pisk_options.update(baseline_options)
            match = GomokuEngineMatch(rule,
                                      board_size,
                                      engine,
                                      baseline_engine,
                                      pisk_options,
                                      baseline_pisk_options,
                                      time=game_time,
                                      inctime=inc_time,
                                      depth=depth,
                                      nodes=nodes,
                                      movetime=move_time,
                                      nodestime=nodestime,
                                      draw_move_limit=draw_move_limit,
                                      draw_score_limit=draw_score_limit,
                                      win_move_limit=win_move_limit,
                                      win_score_limit=win_score_limit,
                                      draw_after=int(board_size * board_size * 0.85),
                                      verbosity=VERBOSITY)
        else:
            assert 0, f"unknown variant {variant}"

        match.init_engines()
        time.sleep(0.2)
        if not match.check_engines_ok():
            raise Exception("Engine died")
        results = match.run_game(order, 1 - order, fen)
        match.destroy_engines()
        return results

    def process_task(self, worker_id, task):
        task_id = task["task_id"]
        variant = task["variant"]
        fen = task["fen"]
        order = task["order"]
        ops = task["options"]
        engine = ops["engine"]
        weight = ops["weight"]
        baseline_engine = ops["baseline_engine"]
        baseline_weight = ops["baseline_weight"]
        print(f"线程 {worker_id} 正在测试 {fen} {SIDE_NAME[variant][order]}\n"
              f"Time:{ops['game_time'] / 1000}+{ops['inc_time'] / 1000} "
              f"Depth:{ops['depth']} "
              f"Nodes:{ops['nodes']} "
              f"MoveTime:{ops['move_time']}")
        try:
            if not engine and not weight and not baseline_engine and not baseline_weight:
                raise Exception("No engine or weight specified")
            if not baseline_engine:
                raise Exception("No baseline engine specified")
            if not engine:
                engine = baseline_engine
            if not weight:
                weight = baseline_weight
            if not os.path.isfile(engine):
                raise Exception("Engine File Not Exist")
            if not os.path.isfile(baseline_engine):
                raise Exception("Baseline Engine File Not Exist")
            if os.path.exists(engine + "_upx"):
                engine += "_upx"
            if os.path.exists(baseline_engine + "_upx"):
                baseline_engine += "_upx"
            if os.name != 'nt':
                os.system(f"chmod +x {engine}")
                os.system(f"chmod +x {baseline_engine}")

            start_time = time.time()
            res, game_record = self.process_match(variant, order, fen, engine, baseline_engine,
                                                  weight, baseline_weight, ops)
            end_time = time.time()

            with self.lock:
                if task_id in self.task_results and fen in self.task_results[task_id]:
                    self.task_results[task_id][fen][order] = (res, game_record)

            print(f"Worker {worker_id}|Time: {round(end_time - start_time, 1)}s|"
                  f" {weight}@{engine} vs {baseline_weight}@{baseline_engine} Finished"
                  f" {fen} {SIDE_NAME[variant][order]}: {res}")
            print(f"{len(self.task_queue)} tasks left")
        except Exception as e:
            traceback.print_exc()
            task["error_count"] += 1
            if task["error_count"] <= 1:
                with self.lock:
                    self.task_queue.insert(0, task)
                print(
                    f"Worker {worker_id}|{weight}@{engine} vs {baseline_weight}@{baseline_engine} Error: {repr(e)}"
                )
                print("Insert task to queue")
            else:
                with self.lock:
                    for t in self.task_queue.copy():
                        if t["task_id"] == task["task_id"] and t["fen"] == task["fen"]:
                            self.task_queue.remove(t)
                    self.abandon_list.append({
                        "task_id": task["task_id"],
                        "fen": task["fen"],
                    })
                print(
                    f"Worker {worker_id}|{weight}@{engine} vs {baseline_weight}@{baseline_engine} Failed: {repr(e)}"
                )
                print(f"{len(self.task_queue)} tasks left")

    def worker_thread(self, worker_id):
        print(f"Worker {worker_id} started.")
        self.working_workers += 1
        self.started = True
        while self.enable:
            output_cnt = 0
            while len(self.task_queue) == 0:
                output_cnt = (output_cnt + 1) % 5
                if output_cnt == 1:
                    print(f"线程 {worker_id} 等待任务...")
                time.sleep(1)
                if not self.enable:
                    return
            with self.lock:
                if len(self.task_queue) > 0:
                    task = self.task_queue.pop(0)
                else:
                    continue
            self.process_task(worker_id, task)
        self.working_workers -= 1
        print(f"Worker {worker_id} exited.")

    def start_worker(self, thread_count):
        self.thread_list = []
        for i in range(thread_count):
            thread = threading.Thread(target=self.worker_thread, args=(i,))
            thread.setDaemon(True)
            thread.start()
            self.thread_list.append(thread)


if __name__ == "__main__":
    tester = Tester()
    tester.start_worker(1)
    tester.add_task("test",
                    "",
                    "./files/stockfish15.1.exe",
                    "",
                    "./files/stockfish15.1.exe",
                    variant="chess",
                    depth=7,
                    count=1000)
    # tester.add_task("test2",
    #                 "./files/rapfi_weight.zip",
    #                 "./files/rapfi.exe",
    #                 "./files/rapfi_weight.zip",
    #                 "./files/rapfi.exe",
    #                 variant="gomoku_freestyle20",
    #                 game_time=10000,
    #                 inc_time=100,
    #                 count=2)
    while True:
        result_list = {}
        # print(tester.task_results)
        for task_id in list(tester.task_results):
            task_result = {
                "task_id": task_id,
                "wdl": [0, 0, 0],
                "ptnml": [0, 0, 0, 0, 0],
                "fwdl": [0, 0, 0],
            }
            done_fens = []
            results = tester.task_results[task_id]
            for fen in results:
                respair = results[fen]
                if not respair[0] or not respair[1]:
                    # print("Fen not completed:", fen, respair)
                    continue
                done_fens.append(fen)
                for i in range(2):
                    res = respair[i]
                    if res == "win":
                        task_result["wdl"][0] += 1
                    elif res == "lose":
                        task_result["wdl"][2] += 1
                    elif res == "draw":
                        task_result["wdl"][1] += 1
                    if i == 0:
                        if res == "win":
                            task_result["fwdl"][0] += 1
                        elif res == "lose":
                            task_result["fwdl"][2] += 1
                        elif res == "draw":
                            task_result["fwdl"][1] += 1
                res = respair[1][0]
                first_res = respair[0][0]
                if res == "lose" and first_res == "lose":
                    task_result["ptnml"][0] += 1
                elif res == "lose" and first_res == "draw" or \
                        res == "draw" and first_res == "lose":
                    task_result["ptnml"][1] += 1
                elif res == "draw" and first_res == "draw" or \
                        res == "win" and first_res == "lose" or \
                        res == "lose" and first_res == "win":
                    task_result["ptnml"][2] += 1
                elif res == "win" and first_res == "draw" or \
                        res == "draw" and first_res == "win":
                    task_result["ptnml"][3] += 1
                elif res == "win" and first_res == "win":
                    task_result["ptnml"][4] += 1
                else:
                    print(f"Err res:{res} first_res:{first_res}")
            if sum(task_result["wdl"]) > 0:
                print(task_result)
                if task_id not in result_list:
                    result_list[task_id] = task_result
                else:
                    for i in range(3):
                        result_list[task_id]["wdl"][i] += task_result["wdl"][i]
                        result_list[task_id]["fwdl"][i] += task_result["fwdl"][i]
                    for i in range(5):
                        result_list[task_id]["ptnml"][i] += task_result["ptnml"][i]
                with tester.lock:
                    for fen in done_fens:
                        tester.task_results[task_id].pop(fen)
        time.sleep(1)
