"""Market-data brokers. Each hands data over in Kite's shapes (instrument rows, ticks, candles)."""


def make_broker(cfg):
    """The broker DATA_PROVIDER names, built from its credentials."""
    if cfg.provider == "kite":
        from options.brokers.kite import KiteBroker
        return KiteBroker(cfg.KITE_API_KEY, cfg.KITE_API_SECRET)
    from options.brokers.angel import AngelBroker
    return AngelBroker(cfg.ANGEL_API_KEY, cfg.ANGEL_CLIENT_CODE, cfg.ANGEL_PIN, cfg.ANGEL_TOTP_SECRET,
                       historical_api_key=cfg.ANGEL_HISTORICAL_API_KEY)
