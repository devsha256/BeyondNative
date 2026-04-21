import json
import re
import difflib
from typing import Any, List, Dict, Optional, Tuple
from urllib.parse import urlparse

class PostmanComparator:
    """Enterprise-grade JSON comparison engine with structural alignment."""

    def __init__(self, exempted_fields: List[str] = None):
        self.exempted_fields = exempted_fields or []
        self.stats = {
            "totalMatched": 0,
            "totalMismatches": 0,
            "totalExempted": 0,
            "totalOnlyA": 0,
            "totalOnlyB": 0
        }

    def _is_field_exempted(self, path: str) -> bool:
        if not path: return False
        for pattern in self.exempted_fields:
            # Mode 1: Full Regex (between / /)
            if pattern.startswith('/') and pattern.endswith('/') and len(pattern) > 2:
                try:
                    if re.search(pattern[1:-1], path): return True
                except: pass
            # Mode 2: Wildcard (contains *)
            elif '*' in pattern:
                regex_pattern = re.escape(pattern).replace('\\*', '.*')
                if re.fullmatch(regex_pattern, path.split('.')[-1]) or re.fullmatch(regex_pattern, path):
                    return True
            # Mode 3: Exact Match or Substring
            elif pattern in path:
                return True
        return False

    def _normalize(self, data: Any) -> Any:
        """Sorts keys and primitive arrays for stable comparison."""
        if isinstance(data, dict):
            return {k: self._normalize(data[k]) for k in sorted(data.keys())}
        elif isinstance(data, list):
            # If it's a list of primitives, sort it
            if all(isinstance(x, (str, int, float, bool, type(None))) for x in data):
                return sorted(data, key=lambda x: str(x))
            return [self._normalize(x) for x in data]
        return data

    def _get_json_lines(self, obj: Any, path: str = "", indent: int = 0) -> List[Dict]:
        lines = []
        if obj is None:
            lines.append({"text": "null", "indent": indent, "path": path, "type": "primitive"})
        elif isinstance(obj, bool):
            lines.append({"text": str(obj).lower(), "indent": indent, "path": path, "type": "primitive"})
        elif isinstance(obj, (int, float, str)):
            lines.append({"text": json.dumps(obj), "indent": indent, "path": path, "type": "primitive"})
        elif isinstance(obj, dict):
            lines.append({"text": "{", "indent": indent, "path": path, "type": "open-obj"})
            keys = sorted(obj.keys())
            for i, k in enumerate(keys):
                sub_path = f"{path}.{k}" if path else k
                comma = "," if i < len(keys) - 1 else ""
                lines.append({"text": f'"{k}": ', "indent": indent + 1, "path": sub_path, "type": "key"})
                val_lines = self._get_json_lines(obj[k], sub_path, indent + 1)
                # Combine key and first line of value if primitive
                if val_lines[0]["type"] == "primitive":
                    lines[-1]["text"] += val_lines[0]["text"] + comma
                else:
                    lines.extend(val_lines)
                    lines[-1]["text"] += comma
            lines.append({"text": "}", "indent": indent, "path": path, "type": "close-obj"})
        elif isinstance(obj, list):
            lines.append({"text": "[", "indent": indent, "path": path, "type": "open-arr"})
            for i, item in enumerate(obj):
                sub_path = f"{path}[{i}]"
                comma = "," if i < len(obj) - 1 else ""
                val_lines = self._get_json_lines(item, sub_path, indent + 1)
                for j, line in enumerate(val_lines):
                    if j == len(val_lines) - 1: line["text"] += comma
                    lines.append(line)
            lines.append({"text": "]", "indent": indent, "path": path, "type": "close-arr"})
        return lines

    def _align_lines(self, lines_a: List[Dict], lines_b: List[Dict]) -> List[Dict]:
        """Aligns lines side by side using a path-aware matching strategy."""
        aligned = []
        i, j = 0, 0
        
        while i < len(lines_a) or j < len(lines_b):
            line_a = lines_a[i] if i < len(lines_a) else None
            line_b = lines_b[j] if j < len(lines_b) else None
            
            if not line_a:
                aligned.append({"a": None, "b": line_b, "status": "only_b"})
                j += 1
            elif not line_b:
                aligned.append({"a": line_a, "b": None, "status": "only_a"})
                i += 1
            elif line_a["path"] == line_b["path"]:
                status = "match"
                if line_a["text"] != line_b["text"]:
                    status = "mismatch"
                
                # Check for exemption
                if self._is_field_exempted(line_a["path"]):
                    status = "exempted"
                
                aligned.append({"a": line_a, "b": line_b, "status": status})
                i += 1
                j += 1
            else:
                # Path mismatch - look ahead to find a resync point
                # Simple logic: if path_a exists in future of b, or vice-versa
                found_a_in_b = False
                for k in range(j + 1, min(j + 20, len(lines_b))):
                    if lines_b[k]["path"] == line_a["path"]:
                        found_a_in_b = True
                        break
                
                if found_a_in_b:
                    aligned.append({"a": None, "b": line_b, "status": "only_b"})
                    j += 1
                else:
                    aligned.append({"a": line_a, "b": None, "status": "only_a"})
                    i += 1
        
        return aligned

    def compare(self, data_a: Any, data_b: Any) -> Dict:
        norm_a = self._normalize(data_a)
        norm_b = self._normalize(data_b)
        
        lines_a = self._get_json_lines(norm_a)
        lines_b = self._get_json_lines(norm_b)
        
        aligned = self._align_lines(lines_a, lines_b)
        
        # Calculate Stats
        self.stats = {k: 0 for k in self.stats}
        for row in aligned:
            status = row["status"]
            if status == "match": self.stats["totalMatched"] += 1
            elif status == "mismatch": self.stats["totalMismatches"] += 1
            elif status == "exempted": self.stats["totalExempted"] += 1
            elif status == "only_a": self.stats["totalOnlyA"] += 1
            elif status == "only_b": self.stats["totalOnlyB"] += 1
            
        total_compared = self.stats["totalMatched"] + self.stats["totalMismatches"] + self.stats["totalExempted"]
        match_percent = round((self.stats["totalMatched"] / total_compared * 100), 2) if total_compared > 0 else 100
        
        # Return formatted rows for UI
        ui_rows = []
        for row in aligned:
            la = row["a"]
            lb = row["b"]
            ui_rows.append({
                "text_a": la["text"] if la else "",
                "indent_a": la["indent"] if la else (lb["indent"] if lb else 0),
                "text_b": lb["text"] if lb else "",
                "indent_b": lb["indent"] if lb else (la["indent"] if la else 0),
                "status": row["status"],
                "path": la["path"] if la else lb["path"]
            })
            
        return {
            "stats": self.stats,
            "match_percent": match_percent,
            "status": "PASSED" if self.stats["totalMismatches"] == 0 and self.stats["totalOnlyA"] == 0 else "FAILED",
            "diff": ui_rows
        }

def validate_urls(url_a: str, url_b: str) -> Tuple[bool, str]:
    """Ensures paths are identical, ignoring hosts."""
    try:
        p_a = urlparse(url_a)
        p_b = urlparse(url_b)
        
        if p_a.path != p_b.path:
            return False, f"URL Path mismatch: '{p_a.path}' vs '{p_b.path}'"
        if p_a.query != p_b.query:
            return False, f"URL Query mismatch: '{p_a.query}' vs '{p_b.query}'"
        return True, ""
    except Exception as e:
        return False, str(e)

def compare_responses(payload: dict) -> dict:
    """Helper function for backward compatibility and quick API calls."""
    resp_a = payload.get("response_a", {})
    resp_b = payload.get("response_b", {})
    exempted = payload.get("exempted_fields", [])
    comparator = PostmanComparator(exempted_fields=exempted)
    return comparator.compare(resp_a, resp_b)
