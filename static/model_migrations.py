"""模型 ID 单向迁移；位于旧更新器能够同步的目录内。"""


def normalize_laohu_model_id(model_id: str) -> str:
    """内部平台 ID 保持 ai-money，提交模型 ID 统一为 laohu。"""
    normalized = str(model_id or "").strip()
    for legacy_prefix, current_prefix in (
        ("laohuaimoney-", "laohu-"), ("laohuaimoney/", "laohu/"),
        ("zhenzhen-", "laohu-"), ("zhenzhen/", "laohu/"),
    ):
        if normalized.lower().startswith(legacy_prefix):
            return current_prefix + normalized[len(legacy_prefix):]
    return normalized
