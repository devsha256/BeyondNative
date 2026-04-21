import json
import re
from typing import Any, List, Dict, Optional, Tuple, Set
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
        self.exempted_paths_found : Set[str] = set()

    def _clean_path(self, path: str) -> str:
        """Removes array indices like [0] from path for summary purposes."""
        return re.sub(r'\[\d+\]', '', path)

    def _is_field_exempted(self, path: str) -> bool:
        if not path: return False
        for pattern in self.exempted_fields:
            # Mode 1: Full Regex (between / /)
            if pattern.startswith('/') and pattern.endswith('/') and len(pattern) > 2:
                try:
                    if re.search(pattern[1:-1], path): 
                        self.exempted_paths_found.add(self._clean_path(path))
                        return True
                except: pass
            # Mode 2: Wildcard (contains *)
            elif '*' in pattern:
                regex_pattern = re.escape(pattern).replace('\\*', '.*')
                field_name = path.split('.')[-1]
                if re.fullmatch(regex_pattern, field_name) or re.fullmatch(regex_pattern, path):
                    self.exempted_paths_found.add(self._clean_path(path))
                    return True
            # Mode 3: Exact Match or Substring
            elif pattern in path:
                self.exempted_paths_found.add(self._clean_path(path))
                return True
        return False

    def _normalize(self, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: self._normalize(data[k]) for k in sorted(data.keys())}
        elif isinstance(data, list):
            if all(isinstance(x, (str, int, float, bool, type(None))) for x in data):
                try: return sorted(data, key=lambda x: str(x))
                except: return data
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
        aligned = []
        i, j = 0, 0
        while i < len(lines_a) or j < len(lines_b):
            la = lines_a[i] if i < len(lines_a) else None
            lb = lines_b[j] if j < len(lines_b) else None
            if not la: aligned.append({"a": None, "b": lb, "status": "only_b"}); j += 1
            elif not lb: aligned.append({"a": la, "b": None, "status": "only_a"}); i += 1
            elif la["path"] == lb["path"]:
                status = "match"
                if la["text"] != lb["text"]: status = "mismatch"
                if self._is_field_exempted(la["path"]): status = "exempted"
                aligned.append({"a": la, "b": lb, "status": status})
                i += 1; j += 1
            else:
                found_a_in_b = False
                for k in range(j + 1, min(j + 20, len(lines_b))):
                    if lines_b[k]["path"] == la["path"]: found_a_in_b = True; break
                if found_a_in_b: aligned.append({"a": None, "b": lb, "status": "only_b"}); j += 1
                else: aligned.append({"a": la, "b": None, "status": "only_a"}); i += 1
        return aligned

    def compare(self, data_a: Any, data_b: Any) -> Dict:
        self.stats = {k: 0 for k in self.stats}
        self.exempted_paths_found = set()
        
        norm_a = self._normalize(data_a)
        norm_b = self._normalize(data_b)
        lines_a = self._get_json_lines(norm_a)
        lines_b = self._get_json_lines(norm_b)
        aligned = self._align_lines(lines_a, lines_b)
        
        for row in aligned:
            st = row["status"]
            if st == "match": self.stats["totalMatched"] += 1
            elif st == "mismatch": self.stats["totalMismatches"] += 1
            elif st == "exempted": self.stats["totalExempted"] += 1
            elif st == "only_a": self.stats["totalOnlyA"] += 1
            elif st == "only_b": self.stats["totalOnlyB"] += 1
            
        total_comp = self.stats["totalMatched"] + self.stats["totalMismatches"] + self.stats["totalExempted"]
        pct = round((self.stats["totalMatched"] / total_comp * 100), 2) if total_comp > 0 else 100
        
        ui_rows = []
        for row in aligned:
            la, lb = row["a"], row["b"]
            ui_rows.append({
                "text_a": la["text"] if la else "", "indent_a": la["indent"] if la else (lb["indent"] if lb else 0),
                "text_b": lb["text"] if lb else "", "indent_b": lb["indent"] if lb else (la["indent"] if la else 0),
                "status": row["status"], "path": la["path"] if la else lb["path"]
            })
            
        return {
            "stats": self.stats,
            "match_percent": pct,
            "exempted_fields_found": sorted(list(self.exempted_paths_found)),
            "status": "PASSED" if self.stats["totalMismatches"] == 0 and self.stats["totalOnlyA"] == 0 else "FAILED",
            "diff": ui_rows
        }

def validate_urls(url_a: str, url_b: str) -> Tuple[bool, str]:
    try:
        p_a, p_b = urlparse(url_a), urlparse(url_b)
        if p_a.path != p_b.path: return False, f"URL Path mismatch: '{p_a.path}' vs '{p_b.path}'"
        if p_a.query != p_b.query: return False, f"URL Query mismatch: '{p_a.query}' vs '{p_b.query}'"
        return True, ""
    except Exception as e: return False, str(e)

def compare_responses(payload: dict) -> dict:
    resp_a = payload.get("response_a", {})
    resp_b = payload.get("response_b", {})
    exempted = payload.get("exempted_fields", [])
    comparator = PostmanComparator(exempted_fields=exempted)
    return comparator.compare(resp_a, resp_b)
