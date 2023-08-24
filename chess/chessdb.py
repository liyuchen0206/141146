import requests

API = "http://www.chessdb.cn/chessdb.php?action=querypv&board="


def get_pv(fen):
    req = requests.get(API + fen)
    if "score" not in req.text:
        return None
    args = req.text.split(",")
    kvs = {}
    for arg in args:
        k, v = arg.split(":")
        if k == "pv":
            kvs[k] = v.split("|")
        else:
            kvs[k] = int(v)
    return kvs