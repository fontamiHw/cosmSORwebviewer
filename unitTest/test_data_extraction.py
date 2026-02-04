#!/usr/bin/env python3
"""
Test for data extraction functionality
"""

import json
import os
import sys
from typing import Dict, List, Tuple

# Add parent directory to path to import modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))


def extract_measurement_data(sor_data: Dict) -> Tuple[List[float], List[float]]:
    """Extract measurement data from the JSON structure"""
    km_values = []
    loss_values = []

    if isinstance(sor_data, dict):
        # First, try to extract actual trace data if available
        if 'tracedata' in sor_data and sor_data['tracedata']:
            trace_data = sor_data['tracedata']

            # The trace data should contain distance and loss measurements
            if isinstance(trace_data, list):
                for point in trace_data:
                    if isinstance(point, dict):
                        # Look for km and loss fields
                        km = None
                        loss = None

                        if 'km' in point:
                            km = float(point['km'])
                        if 'loss' in point:
                            loss = float(point['loss'])

                        if km is not None and loss is not None:
                            km_values.append(km)
                            loss_values.append(loss)

    return km_values, loss_values


def test_data_extraction_with_simulated_data():
    """Test data extraction with simulated trace data"""
    print("🔬 Testing data extraction with simulated data...")

    # Create simulated SOR data structure
    simulated_data = {
        'sor_data': {
            'filename': 'test.sor',
            'GenParams': {}
        },
        'ml_events': [],
        'tracedata': [
            {'km': 0.0, 'loss': 0.0},
            {'km': 0.1, 'loss': 0.2},
            {'km': 0.2, 'loss': 0.4},
            {'km': 0.3, 'loss': 0.6},
            {'km': 0.4, 'loss': 0.8},
        ]
    }

    print(f"✅ Created simulated data with keys: {list(simulated_data.keys())}")

    # Test data extraction
    try:
        km_values, loss_values = extract_measurement_data(simulated_data)
        print(
            f"📊 Extracted {len(km_values)} km values and {len(loss_values)} loss values")

        if km_values and loss_values:
            print(
                f"📏 Distance range: {min(km_values):.6f} - {max(km_values):.6f} km")
            print(
                f"📉 Loss range: {min(loss_values):.3f} - {max(loss_values):.3f} dB")
            print("✅ Data extraction successful!")

            # Verify the extracted data
            expected_km = [0.0, 0.1, 0.2, 0.3, 0.4]
            expected_loss = [0.0, 0.2, 0.4, 0.6, 0.8]

            if km_values == expected_km and loss_values == expected_loss:
                print("✅ Extracted data matches expected values")
            else:
                print("❌ Extracted data doesn't match expected values")
                print(f"Expected km: {expected_km}")
                print(f"Actual km: {km_values}")
                print(f"Expected loss: {expected_loss}")
                print(f"Actual loss: {loss_values}")

            # Test statistics calculation
            try:
                stats = {
                    'max_distance': max(km_values) if km_values else 0,
                    'total_loss': abs(max(loss_values) - min(loss_values)) if loss_values else 0,
                    'total_points': len(km_values)
                }
                print(f"📈 Statistics: {stats}")
                print("✅ Statistics calculation successful!")

            except Exception as e:
                print(f"❌ Statistics calculation failed: {e}")
        else:
            print("❌ No data extracted")

    except Exception as e:
        print(f"❌ Data extraction failed: {e}")
        import traceback
        traceback.print_exc()


def test_empty_data_handling():
    """Test handling of empty or invalid data"""
    print("\n🔬 Testing empty data handling...")

    empty_cases = [
        {'sor_data': {}, 'ml_events': [], 'tracedata': []},
        {'sor_data': {}, 'ml_events': [], 'tracedata': None},
        {},
        None
    ]

    for i, case in enumerate(empty_cases):
        print(
            f"\n📝 Testing case {i+1}: {type(case)} with {len(case) if case else 0} keys")

        try:
            km_values, loss_values = extract_measurement_data(case)
            if not km_values and not loss_values:
                print("✅ Empty case handled correctly - returned empty lists")
            else:
                print(
                    f"❌ Empty case failed - returned {len(km_values)} km, {len(loss_values)} loss values")
        except Exception as e:
            print(f"❌ Empty case failed with error: {e}")


if __name__ == "__main__":
    print("🚀 Testing data extraction functionality...\n")
    try:
        test_data_extraction_with_simulated_data()
        test_empty_data_handling()
        print("\n🎉 All tests completed!")
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
