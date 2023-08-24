import builtins
import os.path
import os
import time
import threading
import random
import traceback
import argparse

import fishtest
import util.client_helper as client_helper
import multiprocessing as mp
from fishtest import Tester
from subprocess import Popen, PIPE


def rand_str(length=4):
    return ''.join(random.sample('abcdefghijklmnopqrstuvwxyz0123456789', length))


program_version = "3.1.9"
downloaded_file_list = []
client_id = rand_str(8)
user = ""
need_update = False
last_output_time = time.time()
task_queue = []
tester: Tester = Tester()
running = True
NO_OUTPUT = True
CPU_THREADS = mp.cpu_count()
FILE_PATH = "./files/"
gendata_process: Popen = None
data_generator = "./colab"
download_failed_count = 0
spsa_record = {}


def print(*args, **kwargs):
    if not NO_OUTPUT:
        builtins.print(*args, **kwargs)


def start_gendata_process():
    global gendata_process
    return
    if gendata_process is None or gendata_process.poll() is not None:
        if os.name != 'nt':
            os.system("chmod +x " + data_generator)
        gendata_process = Popen([data_generator, "-u", f"{user}", "-t", f"{CPU_THREADS}"], shell=False,
                                stdin=PIPE, stdout=PIPE, encoding="gb2312")


def stop_gendata_process():
    global gendata_process
    return
    if gendata_process is not None and gendata_process.poll() is not None:
        gendata_process.terminate()
        gendata_process = None


def merge_partial_file():
    merged_files = []
    for file in os.listdir(FILE_PATH):
        if file.endswith(".partial") and len(file.split(".")) >= 3:
            file_parts = []
            file_name = ".".join(file.split(".")[:-2])
            if file_name in merged_files:
                continue
            for i in range(1, 10):
                if os.path.exists(os.path.join(FILE_PATH, f"{file_name}.{i}.partial")):
                    file_parts.append(os.path.join(FILE_PATH, f"{file_name}.{i}.partial"))
                else:
                    break
            # merge the files into one
            with open(os.path.join(FILE_PATH, file_name), 'wb') as wfd:
                for f in file_parts:
                    with open(f, 'rb') as fd:
                        wfd.write(fd.read())
                    os.remove(f)
            merged_files.append(file_name)


def scan_existing_files():
    global downloaded_file_list
    downloaded_file_list = []
    for file in os.listdir(FILE_PATH):
        if file.startswith("engine") or file.endswith(".nnue"):
            if os.path.getsize(FILE_PATH + file) > 1024 * 100 and file not in downloaded_file_list:
                downloaded_file_list.append(file)
        if file.startswith("weight_"):
            os.rename(FILE_PATH + file, FILE_PATH + f"xiangqi-{file[7:]}.nnue")
            new_name = f"xiangqi-{file[7:]}.nnue"
            if os.path.getsize(FILE_PATH + new_name) > 1024 * 100 and new_name not in downloaded_file_list:
                downloaded_file_list.append(new_name)


def download_needed_file(task_id, task, webdrives):
    if task['engine_url']:
        file_id = task['engine_url'].split("/")[-1].split(".")[0].split("_")[-1].strip("_")
        engine = "engine_" + file_id
        if engine not in downloaded_file_list:
            print(f"下载引擎: {task['engine_url']}")
            result = client_helper.download_file_with_trail(task['engine_url'], FILE_PATH + engine, webdrives)
            print(f"下载结果: {result}")
            if not result:
                return False
            if os.path.getsize(FILE_PATH + engine) < 1024 * 100:
                print("引擎文件错误")
                print("可能是网盘超限，等待")
                return False
            if engine not in downloaded_file_list:
                downloaded_file_list.append(engine)
        if not os.path.exists(FILE_PATH + engine + "_upx") and os.path.exists(FILE_PATH + engine) and os.name != 'nt':
            print(f"UPX 压缩: {FILE_PATH + engine}")
            os.system("chmod +x ./upx")
            os.system(f"chmod +x {FILE_PATH + engine}")
            os.system(f"./upx -{random.choice([str(i) for i in range(1, 10)])} -o {FILE_PATH + engine + '_upx'} {FILE_PATH + engine}")

    if task['weight_url']:
        file_id = task['weight_url'].split("/")[-1].split(".")[0].split("_")[-1].strip("_")
        weight = "xiangqi-" + file_id + ".nnue"
        if weight not in downloaded_file_list:
            print(f"下载权重: {task['weight_url']}")
            result = client_helper.download_file_with_trail(task['weight_url'], FILE_PATH + weight, webdrives)
            print(f"下载结果: {result}")
            if not result:
                return False
            if os.path.getsize(FILE_PATH + weight) < 1024 * 100:
                print("权重文件错误")
                print("可能是网盘超限，等待")
                return False
            if weight not in downloaded_file_list:
                downloaded_file_list.append(weight)

    if task['baseline_engine_url']:
        file_id = task['baseline_engine_url'].split("/")[-1].split(".")[0].split("_")[-1].strip("_")
        baseline_engine = "engine_" + file_id
        if baseline_engine not in downloaded_file_list:
            print(f"下载基准引擎: {task['baseline_engine_url']}")
            result = client_helper.download_file_with_trail(task['baseline_engine_url'], FILE_PATH + baseline_engine, webdrives)
            print(f"下载结果: {result}")
            if not result:
                return False
            if os.path.getsize(FILE_PATH + baseline_engine) < 1024 * 100:
                print("基准引擎文件错误")
                print("可能是网盘超限，等待")
                return False
            if baseline_engine not in downloaded_file_list:
                downloaded_file_list.append(baseline_engine)
            if not os.path.exists(FILE_PATH + baseline_engine + "_upx") and os.path.exists(FILE_PATH + baseline_engine) and os.name != 'nt':
                print(f"UPX 压缩: {FILE_PATH + baseline_engine}")
                os.system("chmod +x ./upx")
                os.system(f"chmod +x {FILE_PATH + baseline_engine}")
                os.system(
                    f"./upx -{random.choice([str(i) for i in range(1, 10)])} -o {FILE_PATH + baseline_engine + '_upx'} {FILE_PATH + baseline_engine}")

    if task['baseline_weight_url']:
        file_id = task['baseline_weight_url'].split("/")[-1].split(".")[0].split("_")[-1].strip("_")
        baseline_weight = "xiangqi-" + file_id + ".nnue"
        if baseline_weight not in downloaded_file_list:
            print(f"下载基准权重: {task['baseline_weight_url']}")
            result = client_helper.download_file_with_trail(task['baseline_weight_url'], FILE_PATH + baseline_weight, webdrives)
            print(f"下载结果: {result}")
            if not result:
                return False
            if os.path.getsize(FILE_PATH + baseline_weight) < 1024 * 100:
                print("基准权重文件错误")
                print("可能是网盘超限，等待")
                return False
            if baseline_weight not in downloaded_file_list:
                downloaded_file_list.append(baseline_weight)
    return True


def heartbeat_loop():
    global running
    initial_sleep_time = 30
    sleep_time = 30
    while running:
        time.sleep(sleep_time)
        sleep_time = initial_sleep_time
        data = client_helper.heartbeat(client_id, tester.get_task_ids_in_queue())
        if data is None:
            sleep_time = 5
            continue
        if "program_version" in data and data["program_version"] != program_version:
            print("版本不一致，请更新版本")
            running = False
            exit(0)
        if "invalid_task_ids" in data:
            try:
                tester.remove_tasks(data["invalid_task_ids"])
            except Exception as e:
                print(repr(e))


def get_name(url):
    return url.split("/")[-1]


def select_task(task_list):
    downloaded_tasks = []
    if len(task_list) == 0:
        return None
    task = task_list[0]
    if task["type"] == "spsa":
        return task
    else:
        for item in task_list:
            task = item["task"]
            if (task["engine_url"] == "" or get_name(task["engine_url"]) in downloaded_file_list) and \
                    (task["weight_url"] == "" or get_name(task["weight_url"]) in downloaded_file_list) and \
                    get_name(task["baseline_engine_url"]) in downloaded_file_list and \
                    get_name(task["baseline_weight_url"]) in downloaded_file_list:
                downloaded_tasks.append(item)
        if len(downloaded_tasks) > 0:
            return random.choice(downloaded_tasks)
        else:
            return random.choice(task_list)


def add_to_task(task_id, task):
    if task['engine_url']:
        file_id = task['engine_url'].split("/")[-1].split(".")[0].split("_")[-1].strip("_")
        engine = FILE_PATH + "engine_" + file_id
    else:
        engine = ""
    if task["weight_url"]:
        file_id = task['weight_url'].split("/")[-1].split(".")[0].split("_")[-1].strip("_")
        weight = FILE_PATH + "xiangqi-" + file_id + ".nnue"
    else:
        weight = ""
    if task["baseline_engine_url"]:
        file_id = task['baseline_engine_url'].split("/")[-1].split(".")[0].split("_")[-1].strip("_")
        baseline_engine = FILE_PATH + "engine_" + file_id
    else:
        baseline_engine = ""
    if task["baseline_weight_url"]:
        file_id = task['baseline_weight_url'].split("/")[-1].split(".")[0].split("_")[-1].strip("_")
        baseline_weight = FILE_PATH + "xiangqi-" + file_id + ".nnue"
    else:
        baseline_weight = ""

    num_games = 6
    depth = int(task['time_control'][2])
    game_time = task['time_control'][0]
    nodes = task['nodes']
    if game_time >= 60:
        num_games = CPU_THREADS
    elif game_time >= 30:
        num_games = 2 * CPU_THREADS
    elif game_time >= 10:
        num_games = 3 * CPU_THREADS
    elif game_time >= 5:
        num_games = 6 * CPU_THREADS
    elif game_time >= 2.5:
        num_games = 12 * CPU_THREADS
    elif game_time >= 1.25:
        num_games = 24 * CPU_THREADS
    if 0 < depth <= 10 or 0 < nodes <= 50000:
        num_games = 6 * CPU_THREADS
    if task["type"] == "spsa":
        num_games = task["num_games"]
    if num_games % 2 != 0:
        num_games += 1

    tester.add_task(task_id, weight, engine, baseline_weight, baseline_engine,
                    depth=int(task['time_control'][2]),
                    nodes=int(task['nodes']),
                    game_time=int(task['time_control'][0] * 1000) if task['time_control'][0] != -1 else -1,
                    inc_time=int(task['time_control'][1] * 1000) if task['time_control'][1] != -1 else -1,
                    move_time=int(task['move_time'] * 1000) if task['move_time'] != -1 else -1,
                    nodestime=int(task['nodestime']),
                    count=num_games,
                    uci_ops=task['uci_options'], baseline_uci_ops=task['baseline_uci_options'],
                    draw_move_limit=task['draw_move_limit'], draw_score_limit=task['draw_score_limit'],
                    win_move_limit=task['win_move_limit'], win_score_limit=task['win_score_limit'],
                    draw_as_black_win=task['draw_as_black_win'], mate1_judge=task['mate1_judge'],
                    book=task['book'],
                    variant=task['variant'])
    print(f"添加 来自 {task_id} 的 {num_games} 个 {task['type']} 测试局面到队列成功")


def task_manage_loop():
    global running, tester, download_failed_count
    while running:
        if len(tester.task_queue) >= min(CPU_THREADS, 32):
            time.sleep(0.2)
            continue
        print("队列中任务不足，开始获取任务")
        data = client_helper.get_tasks(client_id)
        if data is None:
            print("获取任务失败")
            time.sleep(10)
            continue
        if "program_version" in data and data["program_version"] != program_version:
            print("版本不一致，请更新版本")
            running = False
            exit(0)
        task_data = select_task(data["tasks"])
        if task_data is None:
            print("没有可用任务")
            start_gendata_process()
            time.sleep(20)
            continue
        stop_gendata_process()
        task_id = task_data["task_id"]
        task = task_data["task"]
        task_type = task_data["type"]
        webdrives = data["webdrives"]
        if task_type == "spsa":
            spsa_record[task_id] = task_data
        result = download_needed_file(task_id, task, webdrives)
        if result:
            download_failed_count = 0
            add_to_task(task_id, task)
        else:
            print(f"下载失败，等待 {download_failed_count * 30}s")
            download_failed_count += 1
            time.sleep(download_failed_count * 30)


def check_is_all_done(results):
    for fen in results:
        result = results[fen]
        if not result[0] or not result[1]:
            return False
    return True



def result_waiting_loop():
    global running
    while running:
        try:
            result_list = {}
            
            with tester.lock:
                if len(tester.abandon_list) > 0:
                    for item in tester.abandon_list.copy():
                        if item["task_id"] in tester.task_results and \
                            item["fen"] in tester.task_results[item["task_id"]]:
                            del tester.task_results[item["task_id"]][item["fen"]]
                            if len(tester.task_results[item["task_id"]]) == 0:
                                del tester.task_results[item["task_id"]]
                    tester.abandon_list = []

            for task_id in list(tester.task_results):
                task_result = {
                    "task_id": task_id,
                    "wdl": [0, 0, 0],
                    "ptnml": [0, 0, 0, 0, 0],
                    "fwdl": [0, 0, 0],
                    "game_records": []
                }
                done_fens = []
                results = tester.task_results[task_id]
                if ":" in task_id and not check_is_all_done(results):  # spsa任务需要全部完成再返回
                    continue
                for fen in results:
                    result = results[fen]
                    if not result[0] or not result[1]:
                        continue
                    done_fens.append(fen)
                    for i in range(2):
                        res, game_record = result[i]
                        task_result["game_records"].append(game_record)
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
                    res, game_record = result[1]
                    first_result, first_record = result[0]
                    if res == "lose" and first_result == "lose":
                        task_result["ptnml"][0] += 1
                    elif res == "lose" and first_result == "draw" or \
                            res == "draw" and first_result == "lose":
                        task_result["ptnml"][1] += 1
                    elif res == "draw" and first_result == "draw" or \
                            res == "win" and first_result == "lose" or \
                            res == "lose" and first_result == "win":
                        task_result["ptnml"][2] += 1
                    elif res == "win" and first_result == "draw" or \
                            res == "draw" and first_result == "win":
                        task_result["ptnml"][3] += 1
                    elif res == "win" and first_result == "win":
                        task_result["ptnml"][4] += 1
                    else:
                        print(f"Err res:{res} first_result:{first_result}")

                if sum(task_result["wdl"]) > 0:
                    if task_id not in result_list:
                        result_list[task_id] = task_result
                    else:
                        for i in range(3):
                            result_list[task_id]["wdl"][i] += task_result["wdl"][i]
                            result_list[task_id]["fwdl"][i] += task_result["fwdl"][i]
                        for i in range(5):
                            result_list[task_id]["ptnml"][i] += task_result["ptnml"][i]
                        result_list[task_id]["game_records"].extend(task_result["game_records"])

                    with tester.lock:
                        for fen in done_fens:
                            tester.task_results[task_id].pop(fen)

            if len(result_list) > 0:
                for task_id in list(result_list):
                    current_iter = None
                    vars1 = None
                    vars2 = None
                    task_type = "normal"
                    if task_id in spsa_record:
                        task_type = "spsa"
                        info = spsa_record[task_id]
                        del spsa_record[task_id]
                        current_iter = info["iter"]
                        vars1 = info["task"]["uci_options"]
                        vars2 = info["task"]["baseline_uci_options"]
                    result = result_list[task_id]
                    result = client_helper.upload_result(client_id, task_id, program_version,
                                                         result["wdl"], result["fwdl"],
                                                         result["ptnml"], result["game_records"], task_type=task_type,
                                                         current_iter=current_iter, vars1=vars1, vars2=vars2)
                    if result == "ver":
                        print(f"版本不一致，请更新版本")
                        running = False
                    else:
                        print(f"上传 {task_id} 结果:", result)
                    time.sleep(1)
        except Exception as e:
            print("Error in result_waiting_loop:", repr(e))
            traceback.print_exc()
        time.sleep(10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", type=str, default="VinXiangQi")
    parser.add_argument("--output", action="store_true", default=False)
    args = parser.parse_args()
    user = args.user
    NO_OUTPUT = not args.output
    fishtest.NO_OUTPUT = NO_OUTPUT
    client_id = user + "/" + client_id

    os.makedirs(FILE_PATH, exist_ok=True)

    scan_existing_files()
    start_time = time.time()
    test_count = 0
    no_waiting = False
    tester.start_worker(CPU_THREADS)
    thread_result_waiting = threading.Thread(target=result_waiting_loop)
    thread_result_waiting.daemon = True
    thread_result_waiting.start()
    thread_heartbeat = threading.Thread(target=heartbeat_loop)
    thread_heartbeat.daemon = True
    thread_heartbeat.start()
    try:
        task_manage_loop()
    except KeyboardInterrupt as e:
        stop_gendata_process()
