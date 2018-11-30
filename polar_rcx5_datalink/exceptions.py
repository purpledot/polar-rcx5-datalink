from requests.exceptions import HTTPError


class PolarDataLinkError(Exception):
    pass


class TrainingSessionError(PolarDataLinkError):
    pass


class ParsingSamplesError(TrainingSessionError):
    pass


class ConverterError(PolarDataLinkError):
    pass


class TCXConverterError(ConverterError):
    pass


class StravaHTTPError(PolarDataLinkError, HTTPError):
    pass


class StravaUnauthorized(StravaHTTPError):
    pass


class StravaActivityUploadError(StravaHTTPError):
    pass
