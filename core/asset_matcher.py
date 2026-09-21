import re
from typing import List, Dict, Any, Tuple, Optional


def normalize_version_tag(tag: str) -> str:
    """Strips leading 'v' or 'V' from a version tag."""
    if tag and tag.lower().startswith("v"):
        return tag[1:]
    return tag


def mask_version_in_filename(filename: str) -> str:
    """
    Replaces version strings (like v1.2.3, 1.0.0, -v4.1, _4.2.1-rc1)
    with a regex wildcard pattern.
    """
    # Regex matching:
    # Optional delimiter (-, _, .)
    # Optional 'v' or 'V'
    # Digits separated by dots (e.g. 1.2, 1.2.3, 4.1)
    # Optional trailing pre-release/build (e.g. -alpha, -rc1)
    version_regex = r'([-_.]?)v?\d+(?:\.\d+)+(?:[-_.][a-zA-Z0-9]+)?'
    
    # Replace version segments with a wildcard group
    pattern = re.sub(version_regex, r'\1v?.*?', filename, flags=re.IGNORECASE)
    return f"^{pattern}$"


def match_release_assets(
    selected_asset_names: List[str],
    available_assets: List[Dict[str, Any]],
    old_tag: str = "",
    new_tag: str = ""
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Matches previously selected asset names against the assets available in a new release.

    Parameters:
        selected_asset_names: List of asset file names selected previously (e.g. ['scrcpy-win64-v4.1.zip'])
        available_assets: List of dicts representing new release assets, each with at least 'name' and 'download_url'
        old_tag: The release tag associated with previous version (e.g. 'v4.1' or '4.1')
        new_tag: The release tag of the new release (e.g. 'v4.2' or '4.2')

    Returns:
        (matched_assets, unresolved_selected_names)
        - matched_assets: List of dicts from available_assets that matched
        - unresolved_selected_names: Subset of selected_asset_names that could not be matched
    """
    if not selected_asset_names:
        # If user previously chose whole release or no specific filter, return all available assets
        return available_assets, []

    matched_assets: List[Dict[str, Any]] = []
    matched_asset_names = set()
    unresolved: List[str] = []

    available_map = {a["name"].lower(): a for a in available_assets}

    for target in selected_asset_names:
        found: Optional[Dict[str, Any]] = None

        # -------------------------------------------------------------
        # Tier 1: Exact Name Match
        # -------------------------------------------------------------
        if target.lower() in available_map:
            found = available_map[target.lower()]

        # -------------------------------------------------------------
        # Tier 2: Direct Tag / Version Substitution
        # -------------------------------------------------------------
        if not found and old_tag and new_tag:
            # Try raw replacement
            candidate_name = target.replace(old_tag, new_tag)
            if candidate_name.lower() in available_map:
                found = available_map[candidate_name.lower()]

            # Try normalized version replacement (without leading 'v')
            if not found:
                norm_old = normalize_version_tag(old_tag)
                norm_new = normalize_version_tag(new_tag)
                if norm_old and norm_new:
                    candidate_name_2 = target.replace(norm_old, norm_new)
                    if candidate_name_2.lower() in available_map:
                        found = available_map[candidate_name_2.lower()]

        # -------------------------------------------------------------
        # Tier 3: Regex Version Pattern Masking
        # -------------------------------------------------------------
        if not found:
            pattern_str = mask_version_in_filename(target)
            try:
                rx = re.compile(pattern_str, re.IGNORECASE)
                candidates = [
                    a for a in available_assets
                    if rx.match(a["name"]) and a["name"] not in matched_asset_names
                ]
                if len(candidates) == 1:
                    found = candidates[0]
                elif len(candidates) > 1:
                    # If multiple match, prioritize same extension & closest length
                    target_ext = os_ext(target)
                    same_ext_candidates = [c for c in candidates if os_ext(c["name"]) == target_ext]
                    if len(same_ext_candidates) == 1:
                        found = same_ext_candidates[0]
                    elif same_ext_candidates:
                        found = min(same_ext_candidates, key=lambda c: abs(len(c["name"]) - len(target)))
                    else:
                        found = min(candidates, key=lambda c: abs(len(c["name"]) - len(target)))
            except Exception:
                pass

        # -------------------------------------------------------------
        # Outcome
        # -------------------------------------------------------------
        if found:
            if found["name"] not in matched_asset_names:
                matched_assets.append(found)
                matched_asset_names.add(found["name"])
        else:
            unresolved.append(target)

    return matched_assets, unresolved


def os_ext(filename: str) -> str:
    """Helper to extract file extension (e.g. .tar.gz or .zip)."""
    fl = filename.lower()
    if fl.endswith(".tar.gz"):
        return ".tar.gz"
    if fl.endswith(".tar.xz"):
        return ".tar.xz"
    if fl.endswith(".tar.bz2"):
        return ".tar.bz2"
    dot = fl.rfind(".")
    return fl[dot:] if dot != -1 else ""
