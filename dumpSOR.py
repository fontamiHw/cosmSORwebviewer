#!/usr/bin/env python3

import argparse
import json
import sys

# from ciscotdrpy.read import sorparse
from ciscotdrpy.detector import OtdrEventDetector
from ciscotdrpy.read import sorparse
from utility.sor_comparator import SORComparator


def main():
    parser = argparse.ArgumentParser(
        description='Parse SOR file and output JSON results')
    parser.add_argument('path', help='Path to the SOR file to parse')
    parser.add_argument('--trace', action='store_true',
                        help='dump also the trace data')
    parser.add_argument(
        '--otherSor', help='Path to a second SOR file to parse')
    parser.add_argument('--compare', nargs='?', const='all',
                        help='Compare two SOR files. Options: "all" (default), "sor_data", "ml", "trace". Requires --otherSor')

    args = parser.parse_args()

    # Validation: --compare requires --otherSor
    if args.compare and not args.otherSor:
        print("Error: --compare option requires --otherSor to specify the second file", file=sys.stderr)
        sys.exit(1)

    def process_sor_file(file_path, include_trace=False):
        """Process a single SOR file and return the results"""
        try:
            if include_trace:
                eva = OtdrEventDetector()
                sor_data, ml_events, tracedata = eva.predict_from_file(
                    file_path)
                return sor_data, ml_events, tracedata
            else:
                _, std_res, _ = sorparse(file_path)
                return std_res, None, None
        except (FileNotFoundError, IOError, ValueError) as e:
            raise Exception(f"Error parsing file '{file_path}': {e}")

    # Process main SOR file
    try:
        sor_data, ml_events, tracedata = process_sor_file(
            args.path, args.trace)

        # Create structured data for first file
        main_data = {
            'sor_data': sor_data,
            'ml_events': ml_events if ml_events is not None else [],
            'tracedata': tracedata if tracedata is not None else []
        }

        # If comparison mode is not enabled, output normally
        if not args.compare:
            # Output main file results
            print(json.dumps(sor_data, indent=2))
            if args.trace:
                print(json.dumps(ml_events, indent=2))
                print(json.dumps(tracedata, indent=2))

    except Exception as e:
        print(f"Error processing main SOR file: {e}", file=sys.stderr)
        sys.exit(1)

    # Process second SOR file if provided
    if args.otherSor:
        try:
            other_sor_data, other_ml_events, other_tracedata = process_sor_file(
                args.otherSor, args.trace)

            # Create structured data for second file
            other_data = {
                'sor_data': other_sor_data,
                'ml_events': other_ml_events if other_ml_events is not None else [],
                'tracedata': other_tracedata if other_tracedata is not None else []
            }

            # Handle comparison mode
            if args.compare:
                comparator = SORComparator()
                comparator.compare_structures(
                    main_data, other_data, args.compare)
            else:
                # Output second file results normally
                print(json.dumps(other_sor_data, indent=2))
                if args.trace:
                    print(json.dumps(other_ml_events, indent=2))
                    print(json.dumps(other_tracedata, indent=2))

        except Exception as e:
            print(f"Error processing second SOR file: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
