"""更新包校验兼容入口，真实实现与单文件升级器共用。"""
from canvas_update import (PUBLIC_ROOT, LATEST_URL, MAX_PACKAGE_BYTES, MAX_EXPANDED_BYTES,
                           package_url, allowed_file, validate_package)
