#!/usr/bin/env python3
"""
SOR File Comparator Module

This module provides functionality to compare two SOR (Start Of Record) files
and identify differences in their structure, metadata, ML events, and trace data.
"""

from typing import Any, Dict, List


class SORComparator:
    """Class to handle comparison between two SOR files."""

    def __init__(self):
        self.differences = []

    def compare_structures(self, data1: Dict, data2: Dict, compare_type: str = "all") -> None:
        """Compare two SOR data structures and print differences."""

        if compare_type == "all":
            # Compare all three components
            self._compare_component(
                data1.get('sor_data', {}), data2.get('sor_data', {}), "sor_data")
            self._compare_component(
                data1.get('ml_events', []), data2.get('ml_events', []), "ml_events")
            self._compare_component(
                data1.get('tracedata', []), data2.get('tracedata', []), "tracedata")
        elif compare_type == "sor_data":
            self._compare_component(
                data1.get('sor_data', {}), data2.get('sor_data', {}), "sor_data")
        elif compare_type == "ml":
            self._compare_component(
                data1.get('ml_events', []), data2.get('ml_events', []), "ml_events")
        elif compare_type == "trace":
            self._compare_component(
                data1.get('tracedata', []), data2.get('tracedata', []), "tracedata")

    def _print_header(self, component_name: str) -> None:
        """Print comparison header for a component."""
        print("++++++++++++++")
        print(f"      {component_name}")
        print("++++++++++++++")

    def _compare_component(self, obj1: Any, obj2: Any, component_name: str) -> None:
        """Compare two components and print differences."""
        differences = []

        # Get differences
        self._find_differences(obj1, obj2, "", differences)

        # Print header and differences
        if differences:
            self._print_header(component_name)
            for diff in differences:
                print(diff)
            print()  # Empty line after each component

    def _find_differences(self, obj1: Any, obj2: Any, path: str, differences: List[str]) -> None:
        """Recursively find differences between two objects."""

        # Handle None values
        if obj1 is None and obj2 is None:
            return
        if obj1 is None:
            differences.append(
                f"  {path}: MISSING in first file, present in second: {self._format_value(obj2)}")
            return
        if obj2 is None:
            differences.append(
                f"  {path}: present in first file, MISSING in second: {self._format_value(obj1)}")
            return

        # Handle different types
        if type(obj1) != type(obj2):
            differences.append(
                f"  {path}: TYPE MISMATCH - first: {type(obj1).__name__}({self._format_value(obj1)}), second: {type(obj2).__name__}({self._format_value(obj2)})")
            return

        # Handle dictionaries
        if isinstance(obj1, dict):
            all_keys = set(obj1.keys()) | set(obj2.keys())
            for key in sorted(all_keys):
                new_path = f"{path}.{key}" if path else key
                if key not in obj1:
                    differences.append(
                        f"  {new_path}: MISSING in first file, present in second: {self._format_value(obj2[key])}")
                elif key not in obj2:
                    differences.append(
                        f"  {new_path}: present in first file, MISSING in second: {self._format_value(obj1[key])}")
                else:
                    self._find_differences(
                        obj1[key], obj2[key], new_path, differences)

        # Handle lists
        elif isinstance(obj1, list):
            len1, len2 = len(obj1), len(obj2)
            if len1 != len2:
                differences.append(
                    f"  {path}: LIST LENGTH MISMATCH - first: {len1} items, second: {len2} items")

            # Compare common indices
            for i in range(min(len1, len2)):
                new_path = f"{path}[{i}]"
                self._find_differences(obj1[i], obj2[i], new_path, differences)

            # Handle extra items
            if len1 > len2:
                for i in range(len2, len1):
                    differences.append(
                        f"  {path}[{i}]: EXTRA item in first file: {self._format_value(obj1[i])}")
            elif len2 > len1:
                for i in range(len1, len2):
                    differences.append(
                        f"  {path}[{i}]: EXTRA item in second file: {self._format_value(obj2[i])}")

        # Handle primitive values
        else:
            if obj1 != obj2:
                differences.append(
                    f"  {path}: VALUE MISMATCH - first: {self._format_value(obj1)}, second: {self._format_value(obj2)}")

    def _format_value(self, value: Any) -> str:
        """Format a value for display in differences."""
        if isinstance(value, (dict, list)):
            if len(str(value)) > 100:
                return f"<{type(value).__name__} with {len(value)} items>"
            return str(value)
        elif isinstance(value, str):
            if len(value) > 50:
                return f'"{value[:47]}..."'
            return f'"{value}"'
        else:
            return str(value)
