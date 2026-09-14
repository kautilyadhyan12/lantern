"""Lantern: AI-orchestrated OSINT investigation platform."""


def __getattr__(name: str) -> str:
    if name == "__version__":
        raise NotImplementedError("S0.1: lantern.__version__ not implemented yet")
    raise AttributeError(name)
