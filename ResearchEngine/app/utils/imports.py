"""可选依赖加载。"""



def require_optional(module: str, hint: str):
    """惰性导入可选依赖；缺失时抛出带安装提示的 ImportError。"""
    try:
        return __import__(module)
    except ImportError as exc:  # pragma: no cover
        raise ImportError(f"{hint}（请执行 `pip install {module}`）") from exc
