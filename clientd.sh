#!/bin/bash
echo Updating gcc...
sudo apt update > /dev/null 2>&1
sudo apt install -y libtbb2 > /dev/null 2>&1

# 检测当前python版本
python_version=$(python -c 'import sys; print(sys.version_info[0])')

# 如果版本不是3，则使用python3
if [ "$python_version" -ne "3" ]; then
  PYTHON="python3"
else
  PYTHON="python"
fi
echo "Using $PYTHON to execute the script"

cleanup() {
  echo "Exiting and killing client..."
  kill $PID
  sleep 2
  if ps -p $PID > /dev/null; then
    kill -9 $PID
  fi
  pkill -9 'engine_'
  echo "Client killed, exiting script."
  exit 0
}

# 捕获 Ctrl+C 并调用清理函数
trap 'cleanup' SIGINT SIGTERM

while true; do
  # 启动你的Python脚本
  echo Starting client...
  $PYTHON client.py &

  # 获取进程ID
  PID=$!

  # 每隔1分钟检查进程是否存在，共检查360次（6小时）
  for i in {1..360}; do
    if ! ps -p $PID > /dev/null; then
      echo "Python process not found, moving to the next step."
      break
    fi
    sleep 60
  done

  if ps -p $PID > /dev/null; then
    # 杀掉进程
    echo Killing client...
    kill $PID

    # 等待5秒检查是否结束
    for i in {1..5}; do
      if ! ps -p $PID > /dev/null; then
        break
      fi
      sleep 1
    done

    # 如果进程仍在运行，则强制结束
    if ps -p $PID > /dev/null; then
      echo "Client did not shut down gracefully, force killing..."
      kill -9 $PID
    fi
  fi

  # 强制结束所有以 "engine_" 开头的进程
  pkill -9 'engine_'
  echo Client killed, restarting...

  # 如有必要 更新Git仓库
  # 检查是否存在git命令
  if command -v git &> /dev/null; then
    # 检查是否在Git仓库中
    if git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
      # 获取当前分支名称
      current_branch=$(git rev-parse --abbrev-ref HEAD)
      # 获取远程仓库信息
      git fetch
      # 比较本地分支和远程分支
      if git diff --quiet $current_branch..origin/$current_branch; then
        echo "The local repo is up to date."
      else
        echo "Reseting to the latest remote repo..."
        git reset --hard origin/$current_branch
        echo "Reset complete."
      fi
    fi
  fi
done
