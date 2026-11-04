def safe_cell(value):
    """Keep numeric cells numeric and neutralize formula-like text, including whitespace."""
    if isinstance(value, str) and value.strip() != '-' and value.lstrip().startswith(('=', '+', '-', '@')):
        return "'" + value
    return value

sanitize_spreadsheet_value = safe_cell
