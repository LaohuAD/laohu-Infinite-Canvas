#!/bin/bash
cd "$(dirname "$0")" || exit 1
/bin/bash "$PWD/mac-启动服务.sh" "$@"
code=$?
if [ "$code" -ne 0 ] && [ -t 0 ]; then
  read -r -p "启动失败，请查看上方提示。按 Enter 退出..."
fi
exit "$code"
