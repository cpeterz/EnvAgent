def __getattr__(name: str):
    if name == "AppSettings":
        from .config import AppSettings
        return AppSettings
    if name == "EnvNewsCollector":
        from .collector import EnvNewsCollector
        return EnvNewsCollector
    raise AttributeError(name)
