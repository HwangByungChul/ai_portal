def render_extracts(quotes: tuple[str, ...]) -> str:
    if type(quotes) is not tuple or len(quotes)>5 or any(type(x) is not str or not x.strip() for x in quotes):raise ValueError('SUMMARY_OUTPUT_INVALID')
    return '\n'.join(f'{n}. {quote}' for n,quote in enumerate(quotes,1))
