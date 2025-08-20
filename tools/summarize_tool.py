def summarize(items: list[dict]) -> str:
    # TODO: LLM ile toparlama (şimdilik basit join)
    return "\n".join([f"- {i.get('subject') or i.get('title')}" for i in items])