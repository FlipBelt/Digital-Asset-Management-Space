"""Reviewed public directory facts, dated 2026-10-10; no purchase or approval facts."""

REFERENCES = (
    dict(
        code="openai",
        name="OpenAI",
        aliases=(
            "OpenAI",
            "OpenAI ChatGPT",
            "ChatGPT",
            "ChatGPT Plus",
            "ChatGPT Team",
            "ChatGPT Pro",
        ),
        website="https://openai.com",
        source="https://chatgpt.com/pricing/",
        category="ai",
        services=(
            dict(
                code="chatgpt",
                name="ChatGPT",
                aliases={
                    "ChatGPT": None,
                    "OpenAI ChatGPT": None,
                    "ChatGPT Plus": "Plus",
                    "ChatGPT Team": "Team",
                    "ChatGPT Pro": "Pro",
                },
                plans=("Free", "Go", "Plus", "Pro", "Business", "Enterprise", "Team"),
                billing="subscription",
            ),
        ),
    ),
    dict(
        code="anthropic",
        name="Anthropic",
        aliases=("Anthropic", "Anthropic Claude", "Claude", "Claude Pro"),
        website="https://www.anthropic.com",
        source="https://claude.com/pricing",
        category="ai",
        services=(
            dict(
                code="claude",
                name="Claude",
                aliases={"Claude": None, "Anthropic Claude": None, "Claude Pro": "Pro"},
                plans=("Free", "Pro", "Max 5x", "Max 20x", "Team", "Enterprise"),
                billing="subscription",
            ),
        ),
    ),
    dict(
        code="google",
        name="Google",
        aliases=("Google", "Google Gemini", "Gemini"),
        website="https://gemini.google.com",
        source="https://one.google.com/about/google-ai-plans/",
        category="ai",
        services=(
            dict(
                code="gemini",
                name="Gemini",
                aliases={"Google Gemini": None, "Gemini": None},
                plans=("免费", "Google AI Plus", "Google AI Pro", "Google AI Ultra"),
                billing="subscription",
            ),
        ),
    ),
    dict(
        code="deepseek",
        name="DeepSeek",
        aliases=("DeepSeek", "Deepseek", "DeepSeek 开放平台", "DeepSeek API"),
        website="https://platform.deepseek.com",
        source="https://api-docs.deepseek.com/quick_start/pricing/",
        category="ai",
        services=(
            dict(
                code="deepseek-api",
                name="DeepSeek API",
                aliases={"DeepSeek API": None},
                plans=("按量计费",),
                billing="usage",
            ),
        ),
    ),
    dict(
        code="minimax",
        name="MiniMax",
        aliases=("MiniMax", "MiniMax API"),
        website="https://platform.minimax.io",
        source="https://www.minimax.io/m-plan",
        category="ai",
        services=(
            dict(
                code="minimax-api",
                name="MiniMax API",
                aliases={"MiniMax API": None},
                plans=("按量计费",),
                billing="usage",
            ),
            dict(
                code="minimax-m-plan",
                name="MiniMax M Plan",
                aliases={"MiniMax M Plan": None, "M Plan": None},
                plans=("Go", "Explore", "Build"),
                billing="subscription",
            ),
        ),
    ),
    dict(
        code="xai",
        name="xAI",
        aliases=("xAI", "xAI Grok", "Grok"),
        website="https://grok.com",
        source="https://grok.com/release-notes/sep-05-2026",
        extra_sources=("https://x.ai/grok",),
        category="ai",
        services=(
            dict(
                code="grok",
                name="Grok",
                aliases={"xAI Grok": None, "Grok": None},
                plans=("SuperGrok", "SuperGrok Heavy"),
                billing="subscription",
            ),
        ),
    ),
)


def known_plan_name(name: str) -> bool:
    if name.casefold() in {"plus", "team", "pro"}:
        return True
    if any(
        name.casefold() == f"{service['name']} {plan}".casefold()
        for entry in REFERENCES
        for service in entry["services"]
        for plan in service["plans"]
    ):
        return True
    return any(
        default
        for entry in REFERENCES
        for service in entry["services"]
        for alias, default in service["aliases"].items()
        if alias.casefold() == name.casefold()
    )
