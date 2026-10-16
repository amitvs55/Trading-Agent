"""Third-party connectors and trading settings managed from the UI.

Values saved on the Connectors page live in the database (secrets encrypted) and override
environment variables. Both the API and the recorder read them, so nothing needs editing
in .env or on Railway after the first deploy. DATABASE_URL (and optionally SECRET_KEY) is
the only configuration that has to stay in the environment.
"""

from dataclasses import dataclass, field
from types import SimpleNamespace

from pydantic import TypeAdapter

from options.admin import validation
from options.admin.repo import AdminRepo
from options.config import OptionsSettings
from options.setups import SETUP_LABELS


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    secret: bool = False
    required: bool = True
    help: str = ""
    placeholder: str = ""


@dataclass(frozen=True)
class ConnectorSpec:
    id: str
    name: str
    role: str
    description: str
    fields: tuple[FieldSpec, ...]
    docs_url: str = ""
    extra: dict = field(default_factory=dict)


CONNECTORS: dict[str, ConnectorSpec] = {c.id: c for c in [
    ConnectorSpec(
        "angel", "Angel One SmartAPI", "Market data", "Free live data. Logs in by itself every morning with your MPIN "
        "and a TOTP code.",
        (FieldSpec("ANGEL_API_KEY", "API key", secret=True, help="SmartAPI app → API key"),
         FieldSpec("ANGEL_CLIENT_CODE", "Client code", placeholder="A123456"),
         FieldSpec("ANGEL_PIN", "MPIN", secret=True, help="Your 4-digit Angel One MPIN"),
         FieldSpec("ANGEL_TOTP_SECRET", "TOTP secret", secret=True,
                   help="The secret shown as text when you enable TOTP (not the 6-digit code)"),
         FieldSpec("ANGEL_HISTORICAL_API_KEY", "Historical data API key", secret=True, required=False,
                   help="Only if SmartAPI gave historical data a separate key")),
        docs_url="https://smartapi.angelbroking.com/"),
    ConnectorSpec(
        "kite", "Zerodha Kite Connect", "Market data", "Paid data plan (₹500/month). Needs a one-tap login each "
        "morning from Telegram.",
        (FieldSpec("KITE_API_KEY", "API key", secret=True),
         FieldSpec("KITE_API_SECRET", "API secret", secret=True),
         FieldSpec("KITE_USER_ID", "Zerodha client ID", required=False, placeholder="AB1234",
                   help="Logins from any other account are rejected")),
        docs_url="https://developers.kite.trade/"),
    ConnectorSpec(
        "telegram", "Telegram", "Alerts", "Signal cards, follow-ups, the morning brief and the end-of-day report.",
        (FieldSpec("TELEGRAM_BOT_TOKEN", "Bot token", secret=True, help="From @BotFather"),
         FieldSpec("TELEGRAM_CHAT_ID", "Chat ID", placeholder="123456789",
                   help="Your own Telegram ID (a number): press Start on your bot, then send /start to @userinfobot")),
        docs_url="https://core.telegram.org/bots#how-do-i-create-a-bot"),
    ConnectorSpec(
        "openai", "OpenAI", "Research pipeline", "Powers the multi-agent research pages. Not used by the "
        "options signals.",
        (FieldSpec("OPENAI_API_KEY", "API key", secret=True),
         FieldSpec("MODEL_NAME", "Model", required=False, placeholder="gpt-4o-mini")),
        docs_url="https://platform.openai.com/api-keys"),
]}

FIELD_INDEX: dict[str, tuple[ConnectorSpec, FieldSpec]] = {f.key: (c, f) for c in CONNECTORS.values() for f in c.fields}
RESEARCH_KEYS = ("OPENAI_API_KEY", "MODEL_NAME")     # belong to config.settings, not OptionsSettings
PROVIDERS = {"angel": "Angel One", "kite": "Kite"}



class InvalidFields(ValueError):
    """One or more submitted values are malformed; nothing was saved."""

    def __init__(self, problems: dict[str, str]):
        self.problems = problems
        super().__init__(" ".join(problems.values()))


TRADING_LIMITS = {
    "OPTIONS_CAPITAL": (10_000, 100_000_000),
    "OPTIONS_RISK_PER_TRADE_PCT": (0.25, 10.0),
    "OPTIONS_DAILY_LOSS_STOP_PCT": (0.5, 50.0),
}


def effective_settings(repo: AdminRepo | None, base: OptionsSettings | None = None) -> OptionsSettings:
    """Environment settings with UI-saved values on top."""
    base = base or OptionsSettings()
    if repo is None:
        return base
    saved = repo.setting_values()
    update = {}
    for key, value in saved.items():
        f = OptionsSettings.model_fields.get(key)
        if f is not None:
            if isinstance(value, str):
                value = validation.normalize(key, value)
            update[key] = TypeAdapter(f.annotation).validate_python(value)
    return base.model_copy(update=update)


def apply_research_overrides(repo: AdminRepo) -> None:
    """Push UI-saved OpenAI settings into the research pipeline's settings object (same process)."""
    from config.settings import settings as research

    saved = repo.setting_values()
    for key in RESEARCH_KEYS:
        if key in saved and saved[key]:
            setattr(research, key, saved[key])


def _env_value(key: str, base: OptionsSettings) -> str:
    if key in RESEARCH_KEYS:
        from config.settings import Settings
        return str(getattr(Settings(), key) or "")
    return str(getattr(base, key, "") or "")


def mask(value: str) -> str:
    return "••••" + value[-4:] if len(value) >= 10 else "••••"


def connector_view(spec: ConnectorSpec, repo: AdminRepo, base: OptionsSettings, saved: dict, meta: dict,
                   health: dict) -> dict:
    fields_out, missing = [], []
    for f in spec.fields:
        if f.key in saved:
            value, source = str(saved[f.key] or ""), "app"
        else:
            value = _env_value(f.key, base)
            source = "env" if value else "unset"
        if f.required and not value:
            missing.append(f.label)
        fields_out.append({
            "key": f.key, "label": f.label, "secret": f.secret, "required": f.required, "help": f.help,
            "placeholder": f.placeholder, "source": source, "is_set": bool(value),
            "display": (mask(value) if f.secret else value) if value else "",
            "problem": validation.problem(f.key, value),
            "updated_at": meta[f.key]["updated_at"].isoformat() if f.key in meta and meta[f.key]["updated_at"] else None,
        })
    return {"id": spec.id, "name": spec.name, "role": spec.role, "description": spec.description,
            "docs_url": spec.docs_url, "fields": fields_out, "configured": not missing, "missing": missing,
            "health": health.get(spec.id)}


def connectors_payload(repo: AdminRepo, base: OptionsSettings | None = None) -> dict:
    base = base or OptionsSettings()
    saved, meta, health = repo.setting_values(), repo.setting_meta(), repo.health_results()
    cfg = effective_settings(repo, base)
    return {
        "connectors": [connector_view(c, repo, base, saved, meta, health) for c in CONNECTORS.values()],
        "data_provider": cfg.provider,
        "providers": PROVIDERS,
        "trading": trading_view(cfg),
    }


def clean_values(connector_id: str, values: dict[str, str | None]) -> dict[str, str | None]:
    """Tidy and check submitted edits: a non-empty string sets a field, None clears it, "" or absent
    keeps it. Raises InvalidFields (every problem, keyed by field) before anything is stored."""
    spec = CONNECTORS.get(connector_id)
    if spec is None:
        raise KeyError(connector_id)
    allowed = {f.key for f in spec.fields}
    out, problems = {}, {}
    for key, value in values.items():
        if key not in allowed:
            raise ValueError(f"{key} is not a {spec.name} setting")
        if value is None:
            out[key] = None
        elif str(value).strip():
            cleaned, problem = validation.clean(key, str(value))
            if problem:
                problems[key] = problem
            else:
                out[key] = cleaned
    if problems:
        raise InvalidFields(problems)
    return out


def missing_after(repo: AdminRepo, connector_id: str, clean: dict[str, str | None],
                  base: OptionsSettings | None = None) -> list[str]:
    """Required fields that would still be empty once `clean` is saved."""
    base = base or OptionsSettings()
    saved = repo.setting_values()
    missing = []
    for f in CONNECTORS[connector_id].fields:
        if not f.required:
            continue
        if f.key in clean:
            value = clean[f.key] if clean[f.key] is not None else _env_value(f.key, base)
        else:
            value = saved[f.key] if f.key in saved else _env_value(f.key, base)
        if not value:
            missing.append(f.label)
    return missing


def preview_settings(repo: AdminRepo, clean: dict[str, str | None],
                     base: OptionsSettings | None = None) -> tuple[OptionsSettings, SimpleNamespace]:
    """The options and research settings as they would be after saving `clean`, without saving it,
    so a connector can be tested before its values are stored."""
    from config.settings import settings as research_now

    base = base or OptionsSettings()
    research = {k: getattr(research_now, k, "") for k in RESEARCH_KEYS}
    update = {}
    for key, value in clean.items():
        value = _env_value(key, base) if value is None else value
        if key in RESEARCH_KEYS:
            research[key] = value
        else:
            update[key] = TypeAdapter(OptionsSettings.model_fields[key].annotation).validate_python(value)
    return effective_settings(repo, base).model_copy(update=update), SimpleNamespace(**research)


def save_connector(repo: AdminRepo, connector_id: str, values: dict[str, str | None], by: str) -> list[str]:
    """Check, then store the edits (see clean_values). Returns the keys that changed."""
    clean = clean_values(connector_id, values)
    for key, value in clean.items():
        if value is None:
            repo.delete_setting(key)
        else:
            repo.set_setting(key, value, secret=FIELD_INDEX[key][1].secret, by=by)
    return list(clean)


def set_data_provider(repo: AdminRepo, provider: str, by: str) -> None:
    provider = provider.strip().lower()
    if provider not in PROVIDERS:
        raise ValueError(f"unknown data provider {provider!r}")
    repo.set_setting("DATA_PROVIDER", provider, secret=False, by=by)


def trading_view(cfg: OptionsSettings) -> dict:
    return {
        "capital": cfg.OPTIONS_CAPITAL,
        "risk_per_trade_pct": cfg.OPTIONS_RISK_PER_TRADE_PCT,
        "daily_loss_stop_pct": cfg.OPTIONS_DAILY_LOSS_STOP_PCT,
        "live_setups": list(cfg.OPTIONS_LIVE_SETUPS),
        "setups": SETUP_LABELS,
        "limits": TRADING_LIMITS,
    }


def save_trading(repo: AdminRepo, values: dict, by: str) -> None:
    mapping = {"capital": "OPTIONS_CAPITAL", "risk_per_trade_pct": "OPTIONS_RISK_PER_TRADE_PCT",
               "daily_loss_stop_pct": "OPTIONS_DAILY_LOSS_STOP_PCT"}
    numbers = {}
    for name, key in mapping.items():
        if name in values and values[name] is not None:
            v = float(values[name])
            lo, hi = TRADING_LIMITS[key]
            if not lo <= v <= hi:
                raise ValueError(f"{name.replace('_', ' ')} must be between {lo:g} and {hi:g}")
            numbers[key] = v
    risk = numbers.get("OPTIONS_RISK_PER_TRADE_PCT")
    stop = numbers.get("OPTIONS_DAILY_LOSS_STOP_PCT")
    if risk is not None and stop is not None and stop < risk:
        raise ValueError("the daily loss stop can't be smaller than the risk per trade")
    live = values.get("live_setups")
    if live is not None:
        unknown = [s for s in live if s not in SETUP_LABELS]
        if unknown:
            raise ValueError(f"unknown setup {', '.join(unknown)}")
    for key, v in numbers.items():
        repo.set_setting(key, v, secret=False, by=by)
    if live is not None:
        repo.set_setting("OPTIONS_LIVE_SETUPS", list(live), secret=False, by=by)


def load_effective_settings() -> OptionsSettings:
    """For processes outside the API (the recorder session): env + settings saved in the UI."""
    from options.storage import make_engine
    from utils.logger import setup_logger

    base = OptionsSettings()
    try:
        return effective_settings(AdminRepo(make_engine(base.DATABASE_URL)), base)
    except Exception:
        setup_logger("options.admin").exception("Couldn't read saved settings; using environment only")
        return base
