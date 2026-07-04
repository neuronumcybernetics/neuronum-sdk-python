VALID_ELEMENTS = {"confirm", "choice", "input", "form", "table", "card", "link", "file"}


def validate_element_payload(data: dict) -> dict:
    """Validate and normalise an element payload produced by the LLM.

    Raises ValueError for unknown element types or missing required fields.
    Returns the (possibly cleaned) data dict.
    """
    element = data.get("element")
    if not element:
        return data

    if element not in VALID_ELEMENTS:
        raise ValueError(f"Unknown element type: '{element}'")

    if element == "choice":
        if not data.get("choices") or not isinstance(data["choices"], list):
            raise ValueError("element='choice' requires a non-empty 'choices' list")

    elif element == "form":
        if not data.get("fields") or not isinstance(data["fields"], list):
            raise ValueError("element='form' requires a non-empty 'fields' list")

    elif element == "table":
        if not data.get("columns") or not isinstance(data["columns"], list):
            raise ValueError("element='table' requires a non-empty 'columns' list")
        if data.get("rows") is None or not isinstance(data["rows"], list):
            raise ValueError("element='table' requires a 'rows' list")
        # Coerce all cell values to strings
        data["rows"] = [[str(cell) for cell in row] for row in data["rows"]]

    elif element == "card":
        if not data.get("components") or not isinstance(data["components"], list):
            raise ValueError("element='card' requires a non-empty 'components' list")

    elif element == "link":
        if not data.get("link"):
            raise ValueError("element='link' requires a 'link' URL string")

    return data
