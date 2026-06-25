"""Slack token validation helpers."""


def validate_slack_tokens(bot_token: str, app_token: str) -> None:
    """
    Validate Slack bot and app token shapes before Socket Mode connects.

    Args:
        bot_token: Bot user OAuth token from ``SLACK_BOT_TOKEN``.
        app_token: App-level token from ``SLACK_APP_TOKEN``.

    Raises:
        ValueError: If either token has the wrong prefix or they are identical.
    """
    bot = bot_token.strip()
    app = app_token.strip()

    if not bot.startswith("xoxb-"):
        raise ValueError(
            "SLACK_BOT_TOKEN must start with 'xoxb-'. "
            "Install the app to your workspace and copy the Bot User OAuth Token."
        )

    if not app.startswith("xapp-"):
        raise ValueError(
            "SLACK_APP_TOKEN must start with 'xapp-' (App-Level Token). "
            f"Got prefix '{app[:5]}...' — you likely pasted the bot token into both variables. "
            "In api.slack.com → Your App → Basic Information → App-Level Tokens, "
            "create a token with the connections:write scope."
        )

    if bot == app:
        raise ValueError(
            "SLACK_BOT_TOKEN and SLACK_APP_TOKEN must be different. "
            "Use xoxb- for the bot token and xapp- for Socket Mode."
        )
