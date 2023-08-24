import random
import time
import multiprocessing as mp
import requests
import base64

magic = "aCp0KnRwOi8vdGVzdC5waWthZmlzaC5vcmcvYSpwKmk="
magic = base64.b64decode(magic).decode().replace("*", "")
sess = requests.Session()


def heartbeat(client_id, processing_task_ids):
    try:
        rep = sess.post(magic + "/heartbeat", json={
            "client_id": client_id,
            "core_count": mp.cpu_count(),
            "task_ids": processing_task_ids
        })
        if rep.status_code == 200:
            return rep.json()
        else:
            return None
    except Exception as e:
        print("发送心跳失败:", repr(e))
        return None


def get_tasks(client_id):
    try:
        rep = sess.get(magic + "/get_tasks?password=ftclient!&client_id=" + client_id + "&core_count=" + str(mp.cpu_count()))
        if rep.status_code == 200:
            return rep.json()
        else:
            return None
    except Exception as e:
        print("获取任务失败:", repr(e))
        return None


def register_task(client_id, task_id):
    try:
        rep = sess.post(magic + f"/register_task", json={
            "task_id": task_id,
            "client_id": client_id,
            "core_count": mp.cpu_count()
        })
        if rep.status_code == 200:
            return rep.json()
        else:
            return None
    except Exception as e:
        print("注册任务失败:", repr(e))
        return None


def upload_result(client_id, task_id, program_version, wdl, fwdl, ptnml, game_records,
                  task_type="normal", current_iter=None, vars1=None, vars2=None):
    try:
        rep = sess.post(magic + "/upload_result", json={"client_id": client_id, "task_id": task_id, "type": task_type,
                                                            "program_version": program_version,
                                                            "wdl": wdl, "fwdl": fwdl, "ptnml": ptnml,
                                                            "game_records": game_records, "iter": current_iter,
                                                            "vars1": vars1, "vars2": vars2})
        info = rep.text
        return info
    except Exception as e:
        print("上传结果失败:", repr(e))
        return None


def download_file(url, save_path):
    try:
        req = sess.get(url)
        data = req.content
        if len(data) < 1024 * 10:
            text = data.decode(encoding="utf-8", errors="ignore")
            if "download-form" in text:
                confirm_url = text.split('download-form" action="')[1].split('"')[0].replace("&amp;", "&")
                return download_file_with_post(confirm_url, save_path)
        with open(save_path, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        print("下载文件失败:", repr(e))
        return False


def download_file_with_post(url, save_path):
    try:
        req = sess.post(url)
        data = req.content
        with open(save_path, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        print("下载文件失败:", repr(e))
        return False


def download_file_with_trail(url, save_path, webdrives, retry_count=3):
    drive_index = random.randint(0, len(webdrives) - 1)
    for i in range(retry_count):
        drive = webdrives[drive_index]
        if download_file(drive + url, save_path):
            return True
        print("下载失败，重试中")
        drive_index = (drive_index + 1) % len(webdrives)
        time.sleep(1)
    return False


if __name__ == "__main__":
    download_file("http://od.stockfishxq.com/gd/XiangQi/fishtest/engine_uob7yg", "weight_8wi6br_test")
