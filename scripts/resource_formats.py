"""Shared format membership for the catalog, renderer, and validation."""

VALID_FORMATS = ("Paper", "Tool", "Benchmark", "Dataset", "Standard", "Collection")


def resource_formats(resource):
    primary = resource.get("format") or "Collection"
    return list(dict.fromkeys([primary, *resource.get("formats", [])]))


def formats_error(resource):
    if "formats" not in resource:
        return None
    values = resource["formats"]
    if (not isinstance(values, list) or not values
            or any(not isinstance(value, str) or value not in VALID_FORMATS for value in values)):
        return "formats must be a non-empty list of supported format names"
    if len(set(values)) != len(values):
        return "formats must not contain duplicates"
    if (resource.get("format") or "Collection") not in values:
        return "formats must include the primary format"
    return None
