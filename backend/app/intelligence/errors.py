class IntelligenceError(Exception):
    """Base class for safe intelligence-layer failures."""


class IntelligenceProviderFailure(IntelligenceError):
    pass


class IntelligenceTimeout(IntelligenceProviderFailure):
    pass


class IntelligenceContextError(IntelligenceError):
    pass


class InvalidInterpretation(IntelligenceError):
    pass
