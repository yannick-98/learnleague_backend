from rest_framework.throttling import AnonRateThrottle


class GameJoinRateThrottle(AnonRateThrottle):
    """Rate limit for public game join and session lookup endpoints."""
    scope = 'game_join'
