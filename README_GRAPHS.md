# SOR File Analysis Suite with Advanced Comparison & Visualization

## Overview

This comprehensive suite provides both command-line and web-based interfaces for parsing, analyzing, and comparing SOR (Standard Optical Reflectometer) files with advanced visualization and comparison capabilities.

## Features

### Core Functionality
- **Dual Interface**: Command-line tool (`dumpSOR.py`) and web application (`sor_web_app.py`)
- **Template-Based Architecture**: Clean separation of HTML templates from Python code for better maintainability
- **File Upload**: Web interface with drag-and-drop or browse selection
- **Complete SOR Parsing**: Full parsing of SOR file structure and metadata using `ciscotdrpy`
- **Chapter Organization**: Organized view of all SOR sections (DataPts, FxdParams, KeyEvents, etc.)
- **Export Options**: JSON export of individual chapters or complete datasets

### Advanced Comparison System (NEW)
- **Dual File Processing**: Compare two SOR files using `--otherSor` flag
- **Deep Structure Analysis**: Recursive comparison of all SOR data structures
- **Intelligent Diff Detection**: Identifies changes in values, types, and nested structures
- **Formatted Output**: Human-readable comparison reports with precise difference tracking

### Interactive Graph Visualization (ENHANCED)
- **Same-Page Display**: Graphs display inline within the main interface using iframe technology
- **Real Trace Data**: Distance (km) vs Loss (dB) plotting with actual SOR trace information
- **Interactive Controls**: Mouse wheel zoom and click-drag pan functionality
- **Data Export**: Export graphs as PNG images or raw data as CSV
- **Measurement Analysis**: Automatic calculation of fiber length, total loss, and attenuation rate

## Usage

### Command Line Interface

1. **Basic SOR File Analysis**
   ```bash
   cd /home/ubuntu/svo/Development/actualDev/tools/otdr
   python dumpSOR.py path/to/file.sor
   ```

2. **Extract Trace Data**
   ```bash
   python dumpSOR.py path/to/file.sor --trace
   ```

3. **Compare Two SOR Files**
   ```bash
   python dumpSOR.py primary_file.sor --otherSor secondary_file.sor --compare
   ```

### Web Interface

1. **Install Dependencies** (if needed)
   ```bash
   pip install jinja2 uvicorn fastapi python-multipart
   ```

2. **Start the Application**
   ```bash
   ./start_web_app.sh
   # OR
   python3 sor_web_app.py
   ```

3. **Access Web Interface**
   - Open browser to `http://localhost:8000`
   - Upload SOR file via drag-drop or file browser

3. **Enable Graph Generation**
   - ✅ Check "Generate Graph Plots" checkbox before uploading
   - This enables the interactive graph functionality

### SOR File Comparison

1. **Basic Comparison**
   ```bash
   python dumpSOR.py file1.sor --otherSor file2.sor --compare
   ```

2. **Comparison Output**
   - Shows detailed differences between two SOR files
   - Identifies changed values, added/removed fields
   - Recursive analysis of nested data structures
   - Type-aware comparison (numbers vs strings)

### Graph Visualization

1. **Command Line Graph Data**
   ```bash
   python dumpSOR.py file.sor --trace
   ```

2. **Web Interface Graphs** (ENHANCED)
   - Ensure the "Enable Interactive Graphs" checkbox is checked before uploading
   - Upload your SOR file
   - Look for the "Graphs Enabled (Click to View)" button in the results panel
   - Click the button to display the interactive graph within the same page (no new windows)

3. **Graph Features**
   - **Real Trace Data**: Uses actual SOR measurement data
   - **Zoom**: Mouse wheel or pinch to zoom in/out
   - **Pan**: Click and drag to pan around the graph
   - **Reset**: Click "🔍 Reset Zoom" to return to full view
   - **Grid Toggle**: Show/hide measurement grid
   - **Export PNG**: Save graph as PNG image
   - **Export CSV**: Download measurement data as spreadsheet

## Project Structure (REFACTORED)

```
tools/otdr/
├── dumpSOR.py                    # Main CLI tool with comparison features
├── sor_web_app.py               # Clean FastAPI web application (Python only)
├── sor_web_app_backup.py        # Backup of original mixed HTML/Python file
├── start_web_app.sh             # Web server startup script
├── README_GRAPHS.md             # This documentation
├── REFACTORING_SUMMARY.md       # Details of template separation refactoring
├── unitTest/                    # Test files directory
│   ├── test_data_extraction.py
│   ├── test_graph_viewer.py
│   └── test_parse_data.py
├── web/                         # Web-related modules
│   ├── html/                    # HTML template directory (NEW)
│   │   ├── main_interface.html  # Main page template with Jinja2 support
│   │   └── graph_viewer.html    # Graph viewer template
│   ├── sor_graph_viewer.py      # Graph visualization module (updated)
│   └── README_WEB.md            # Web interface documentation  
└── utility/                     # Shared utility modules
    └── sor_comparator.py        # SOR file comparison engine
```

## Recent Improvements (Template Refactoring)

### Architecture Enhancements
- **Clean Code Separation**: HTML templates now separated from Python business logic
- **Template System**: Jinja2 templating with fallback mechanisms for better maintainability
- **Same-Page Graphs**: Enhanced user experience with inline graph display instead of popup windows
- **Improved Structure**: Organized `web/html/` directory for all template files

### User Experience Improvements
- **No More Popups**: Graphs display within the main interface using iframe technology
- **Seamless Navigation**: Stay on the same page when viewing graphs and returning to main interface
- **Responsive Design**: Better mobile and desktop compatibility maintained
- **Backward Compatibility**: All existing functionality preserved during refactoring

### Developer Benefits
- **Maintainable Code**: Clear separation between presentation and business logic
- **Template Reusability**: HTML templates can be easily modified without touching Python code
- **Error Handling**: Robust fallback mechanisms for environments without Jinja2
- **Future-Ready**: Architecture supports easy addition of new features and UI improvements

## Graph Visualization Features

### Interactive Controls
- **Mouse Wheel**: Zoom in/out on both X and Y axes
- **Click & Drag**: Pan around the zoomed graph
- **Keyboard Shortcuts**:
  - `Ctrl+R`: Reset zoom to fit all data
  - `Ctrl+G`: Toggle grid lines on/off
  - `Ctrl+S`: Export graph as PNG image

### Measurement Analysis
The graph page automatically calculates:
- **Fiber Length**: Maximum distance measured
- **Total Attenuation**: End-to-end loss
- **Average Loss Rate**: Loss per kilometer (dB/km)
- **Data Point Count**: Number of measurement samples

### Technical Details

#### Data Extraction
The graph viewer extracts measurement data from SOR files using:
1. **ciscotdrpy Library**: Professional SOR parsing with ML event detection
2. **Real Trace Data**: Extracts actual OTDR measurement points from binary SOR format
3. **Multiple Wavelengths**: Supports different wavelength measurements
4. **Event Detection**: Automatic identification of splices, connectors, and fiber events
5. **Precise Measurements**: Distance vs. loss data points with high accuracy

#### Graph Technology
- **Chart.js**: Professional charting library with zoom/pan plugins
- **Responsive Design**: Adapts to different screen sizes
- **High Performance**: Optimized for large datasets (up to 5000 points)
- **Export Capabilities**: PNG image and CSV data export

## API Endpoints

### Existing Endpoints
- `GET /`: Main web interface
- `POST /upload`: Upload and parse SOR files
- `GET /file/{file_id}/chapters`: Get organized chapter data
- `GET /file/{file_id}/export/{chapter_name}`: Export specific chapter
- `GET /file/{file_id}/export-all`: Export all chapters as ZIP

### Graph Endpoints
- `GET /graph/{file_id}`: Interactive graph page with Chart.js visualization

## Example Usage

```javascript
// Upload with graphs enabled
const formData = new FormData();
formData.append('file', sorFile);
formData.append('enable_graphs', true);  // Enable graph generation

fetch('/upload', {
    method: 'POST', 
    body: formData
}).then(response => {
    // Graph will be available at /graph/{file_id}
});
```

## Browser Compatibility

- ✅ Chrome 80+
- ✅ Firefox 75+
- ✅ Safari 13+
- ✅ Edge 80+

## Dependencies

### Python Packages
- `fastapi`: Modern web framework for API development
- `uvicorn`: High-performance ASGI server
- `python-multipart`: File upload support for web interface
- `jinja2`: Template engine for HTML/Python separation (NEW)
- `ciscotdrpy`: Professional SOR parsing library with ML capabilities
- `argparse`: Command-line interface framework

### JavaScript Libraries
- `Chart.js 3.x`: Charting engine
- `chartjs-plugin-zoom`: Zoom/pan functionality

## Comparison System Features

### SORComparator Module
Located in `utility/sor_comparator.py`, this module provides:

- **Deep Structure Comparison**: Recursively compares nested dictionaries and lists
- **Type-Aware Analysis**: Distinguishes between different data types
- **Intelligent Value Formatting**: Smart formatting for numbers, strings, and complex objects  
- **Detailed Difference Reports**: Shows exact paths to changed values
- **Missing/Added Field Detection**: Identifies structural changes between files

### Example Comparison Output
```
Differences found in SOR files:
├── fixedParameters.pulseDuration: 10 ns → 20 ns
├── dataPoints.traceData[0].loss: 0.25 dB → 0.28 dB
└── keyEvents[2].eventType: "splice" → "connector"
```

## Future Enhancements

### Completed Features
- [x] Real trace data extraction from SOR binary format ✅
- [x] Multiple wavelength support ✅  
- [x] Event detection and annotation ✅
- [x] Comparative analysis (dual file comparison) ✅
- [x] Template-based architecture with HTML/Python separation ✅
- [x] Same-page graph display (no more popups) ✅
- [x] Jinja2 templating integration with fallback support ✅

### Planned Features
- [ ] Splice loss analysis with statistical reporting
- [ ] Return loss measurements and analysis
- [ ] PDF report generation with graphs
- [ ] Batch file processing capabilities

### Technical Improvements
- [x] Clean code architecture with separated concerns ✅
- [ ] WebSocket real-time updates
- [ ] Database persistence
- [ ] User authentication
- [ ] Batch file processing
- [ ] REST API documentation with OpenAPI

## Troubleshooting

### Common Issues

1. **"Graphs not enabled for this file"**
   - Ensure the checkbox was checked during upload
   - Re-upload the file with graphs enabled

2. **Import Error: utility.sor_comparator**
   - Make sure you're running from the main otdr directory
   - Check that `utility/sor_comparator.py` exists

3. **SOR File Format Issues**
   - Ensure files are valid SOR format (binary OTDR files)
   - Check that ciscotdrpy library is properly installed

4. **Comparison Shows No Differences**
   - Verify both files are different SOR files
   - Check file paths are correct
   - Ensure --compare flag is included

### Debug Mode
Enable verbose logging by setting environment variable:
```bash
export LOG_LEVEL=DEBUG
python sor_web_app.py
```

## License

This tool is part of the SVO development suite for optical network analysis and OTDR measurement visualization.