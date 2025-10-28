class CleansingError(Exception):
    """Catch-all for anticipated errors cleansing"""



class VisuallyDifferentError(CleansingError):
    """A document does not look the same before and after cleansing"""

