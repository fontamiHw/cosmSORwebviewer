#!/usr/bin/env python3
"""
Test script for the graph viewer functionality
"""

import json
import sys
import os
import tempfile

# Add parent directory to path to import modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from web.sor_graph_viewer import (create_graph_page_for_file,
                                  extract_measurement_data)


def test_graph_viewer_with_simulated_data():
    """Test graph viewer with simulated SOR data"""
    print("🔬 Testing graph viewer with simulated data...")

    # Create simulated SOR data structure with trace data
    simulated_data = {
        'sor_data': {
            'filename': 'test.sor',
            'GenParams': {
                'GeneralParameters': {
                    'LanguageCode': 'EN',
                    'UnitsOfDistance': 'kilometers'
                }
            },
            'FxdParams': {
                'FixedParameters': {
                    'ActualWavelength': 1310,
                    'AcquisitionRange_km': 10.0
                }
            }
        },
        'ml_events': [
            {'type': 'splice', 'distance_km': 2.5, 'loss_db': 0.1},
            {'type': 'connector', 'distance_km': 5.0, 'loss_db': 0.3}
        ],
        'tracedata': [
            {'km': 0.0, 'loss': 0.0},
            {'km': 1.0, 'loss': 0.2},
            {'km': 2.0, 'loss': 0.4},
            {'km': 3.0, 'loss': 0.6},
            {'km': 4.0, 'loss': 0.8},
            {'km': 5.0, 'loss': 1.0},
        ]
    }

    print(f"✅ Created simulated data with keys: {list(simulated_data.keys())}")

    # Test data extraction
    try:
        km_values, loss_values = extract_measurement_data(simulated_data)
        print(f"📊 Extracted {len(km_values)} km values and {len(loss_values)} loss values")

        if km_values and loss_values:
            print(f"📏 Distance range: {min(km_values):.6f} - {max(km_values):.6f} km")
            print(f"📉 Loss range: {min(loss_values):.3f} - {max(loss_values):.3f} dB")
            print("✅ Data extraction successful!")

            # Test graph page creation
            try:
                html_content = create_graph_page_for_file(
                    sor_data=simulated_data,
                    filename="test_file.sor",
                    file_id="test_123"
                )
                print(f"📊 Generated HTML content length: {len(html_content)} characters")

                # Verify HTML contains expected elements
                expected_elements = [
                    '<canvas id="sorChart"',
                    'Chart.js',
                    'test_file.sor',
                    'Distance (km)',
                    'Loss (dB)'
                ]

                missing_elements = []
                for element in expected_elements:
                    if element not in html_content:
                        missing_elements.append(element)

                if not missing_elements:
                    print("✅ HTML content contains all expected elements")
                else:
                    print(f"❌ Missing HTML elements: {missing_elements}")

                # Save for inspection
                with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                    f.write(html_content)
                    temp_file = f.name

                print(f"✅ Graph page creation successful! Saved to {temp_file}")

            except Exception as e:
                print(f"❌ Graph page creation failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("❌ No data extracted")

    except Exception as e:
        print(f"❌ Data extraction failed: {e}")
        import traceback
        traceback.print_exc()


def test_empty_data_handling():
    """Test graph viewer with empty data"""
    print("\n🔬 Testing graph viewer with empty data...")

    empty_data = {
        'sor_data': {
            'filename': 'empty_test.sor',
            'GenParams': {}
        },
        'ml_events': [],
        'tracedata': []
    }

    try:
        km_values, loss_values = extract_measurement_data(empty_data)
        
        if not km_values and not loss_values:
            print("✅ Empty data handled correctly - no values extracted")
        else:
            print(f"❌ Empty data failed - extracted {len(km_values)} km, {len(loss_values)} loss values")

        # Test graph creation with empty data
        try:
            html_content = create_graph_page_for_file(
                sor_data=empty_data,
                filename="empty_test.sor",
                file_id="empty_123"
            )
            
            if 'empty_test.sor' in html_content and len(html_content) > 1000:
                print("✅ Graph page created successfully even with empty data")
            else:
                print("❌ Graph page creation with empty data seems incomplete")

        except Exception as e:
            print(f"❌ Graph page creation with empty data failed: {e}")

    except Exception as e:
        print(f"❌ Empty data test failed: {e}")


def test_import_functionality():
    """Test if we can import the required modules"""
    print("\n� Testing import functionality...")

    try:
        from web.sor_graph_viewer import create_graph_page_for_file, extract_measurement_data
        print("✅ Successfully imported graph viewer functions")
        
        # Test function signatures
        import inspect
        
        # Check create_graph_page_for_file signature
        sig = inspect.signature(create_graph_page_for_file)
        params = list(sig.parameters.keys())
        expected_params = ['sor_data', 'filename', 'file_id']
        
        if all(param in params for param in expected_params):
            print("✅ create_graph_page_for_file has correct signature")
        else:
            print(f"❌ create_graph_page_for_file signature issue. Expected {expected_params}, got {params}")
        
        # Check extract_measurement_data signature
        sig2 = inspect.signature(extract_measurement_data)
        params2 = list(sig2.parameters.keys())
        
        if 'sor_data' in params2:
            print("✅ extract_measurement_data has correct signature")
        else:
            print(f"❌ extract_measurement_data signature issue. Got {params2}")

    except ImportError as e:
        print(f"❌ Import failed: {e}")
        print("   Make sure web/sor_graph_viewer.py exists and is accessible")
    except Exception as e:
        print(f"❌ Import test failed: {e}")


if __name__ == "__main__":
    print("🚀 Testing graph viewer functionality...\n")
    try:
        test_import_functionality()
        test_graph_viewer_with_simulated_data()
        test_empty_data_handling()
        print("\n🎉 All tests completed!")
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
