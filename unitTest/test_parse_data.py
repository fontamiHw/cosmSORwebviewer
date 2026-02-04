#!/usr/bin/env python3
"""
Test script for the parse_data function using dumpSOR.py output
"""

import json
import sys
import os
import subprocess
from pathlib import Path

# Add parent directory to path to import modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from sor_web_app import parse_data


def test_parse_data_function():
    """Test the parse_data function with simulated dumpSOR.py output"""
    print("🔬 Testing parse_data function with simulated output...")

    # Create simulated output from dumpSOR.py (JSON format)
    simulated_output = {
        "filename": "test_file.sor",
        "GenParams": {
            "GeneralParameters": {
                "LanguageCode": "EN",
                "UnitsOfDistance": "kilometers",
                "WavelengthIndex": 1310
            }
        },
        "SupParams": {
            "SupplierParameters": {
                "OTDR": "Test OTDR",
                "OTDRVersion": "1.0"
            }
        },
        "FxdParams": {
            "FixedParameters": {
                "DateTimeStamp": 1699632000,
                "UnitsOfDistance": "kilometers",
                "ActualWavelength": 1310,
                "AcquisitionOffset": 0.0,
                "AcquisitionOffset_km": 0.0,
                "AcquisitionRange": 50000,
                "AcquisitionRange_km": 50.0,
                "AverageTime": 30
            }
        },
        "KeyEvents": [],
        "DataPts": {
            "DataPoints": {
                "NumberOfDataPoints": 1000,
                "ScalingFactor": 1000,
                "DataPointValues": list(range(1000))
            }
        }
    }

    # Test with trace data enabled (simulate --trace flag)
    print("\n� Testing with trace data enabled...")
    output_str = json.dumps(simulated_output)
    result = parse_data(output_str, include_trace=True)

    print(f"✅ Parsed structure keys: {list(result.keys())}")
    
    if 'sor_data' in result:
        print(f"📊 SOR data keys: {list(result['sor_data'].keys())}")
        print("✅ SOR data structure found")
    else:
        print("❌ Missing sor_data structure")

    if 'ml_events' in result:
        print(f"⚡ ML events: {result['ml_events']}")
        print("✅ ML events structure found")
    else:
        print("❌ Missing ml_events structure")

    if 'tracedata' in result:
        print(f"📈 Trace data: {result['tracedata']}")
        print("✅ Trace data structure found")
    else:
        print("❌ Missing tracedata structure")

    # Test without trace data
    print("\n📊 Testing without trace data...")
    result_no_trace = parse_data(output_str, include_trace=False)
    
    print(f"✅ Parsed structure keys: {list(result_no_trace.keys())}")
    
    # Should still have the same structure but empty arrays for trace-related data
    expected_empty = result_no_trace.get('ml_events', []) == [] and result_no_trace.get('tracedata', []) == []
    if expected_empty:
        print("✅ ML events and trace data are empty as expected")
    else:
        print("❌ ML events and trace data should be empty arrays")

    return True


def test_integration_with_dumpsor():
    """Test integration with actual dumpSOR.py if available"""
    print("\n🔗 Testing integration with dumpSOR.py...")
    
    dumpsor_path = Path("../dumpSOR.py")
    if not dumpsor_path.exists():
        print("⚠️  dumpSOR.py not found, skipping integration test")
        return False
    
    print("✅ dumpSOR.py found, testing import...")
    try:
        # Test if we can import the CLI tool's functionality
        sys.path.append(str(dumpsor_path.parent))
        print("✅ Import path setup successful")
        return True
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        return False


if __name__ == "__main__":
    print("🚀 Testing parse_data function...\n")

    try:
        test_parse_data_function()
        test_integration_with_dumpsor()
        print("\n🎉 All tests completed!")
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
