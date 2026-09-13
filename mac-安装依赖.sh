#!/bin/bash
cd "$(dirname "$0")" || exit 1
/bin/bash "$PWD/mac-启动服务.sh" --install
code=$?
if [ -t 0 ]; then
  read -r -p "按 Enter 退出..."
fi
exit "$code"
