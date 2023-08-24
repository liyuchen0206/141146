import os
import time
import zipfile


def rename_all():
    files = os.listdir("./books")
    for file in files:
        if file.endswith(".txt"):
            file_name = file.replace(".txt", "")
            os.rename("./books/" + file, "./books/" + file_name.replace(".", "_") + ".txt")


def get_names(ext=".zip"):
    files = os.listdir("./books")
    names = []
    for file in files:
        if file.endswith(ext):
            file_name = file.replace(ext, "")
            names.append(file_name)
    return names


def read_zip_file():
    files = os.listdir("./books")
    for file in files:
        if file.endswith(".zip"):
            with zipfile.ZipFile("./books/" + file, "r") as f:
                text = f.read(file.replace(".zip", ".txt")).decode("utf-8")
                lines = text.splitlines(keepends=False)
                print(len(lines))


if __name__ == "__main__":
    print(get_names(".zip"))
    # st = time.time()
    # read_zip_file()
    # print(time.time() - st)

