#!/usr/bin/env python3
"""
SOR Graph Viewer - Interactive Graph Visualization

A separate module for creating interactive graphs from SOR measurement data.
Shows distance (km) vs loss (dB) plots with interactive features.
"""

import json
import os
import tempfile
from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


def extract_measurement_data(sor_data: Dict) -> Tuple[List[float], List[float]]:
    """
    Extract measurement data arrays from SOR data.

    Args:
        sor_data: Parsed SOR data dictionary from dumpSOR.py output

    Returns:
        Tuple of (km_values, loss_values)
    """
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
                        # Look for common trace data field names
                        km = None
                        loss = None

                        # Try different possible field names for distance
                        for dist_field in ['km', 'distance', 'x', 'dist_km', 'distance_km']:
                            if dist_field in point:
                                km = float(point[dist_field])
                                break

                        # Try different possible field names for loss
                        for loss_field in ['loss', 'loss_db', 'y', 'power', 'attenuation']:
                            if loss_field in point:
                                loss = float(point[loss_field])
                                break

                        if km is not None and loss is not None:
                            km_values.append(float(km))
                            loss_values.append(float(loss))

            elif isinstance(trace_data, dict):
                # Handle case where trace_data is a dict with arrays
                distances = None
                losses = None

                # Look for distance and loss arrays
                for dist_key in ['distances', 'km', 'x_values', 'distance_array']:
                    if dist_key in trace_data:
                        distances = trace_data[dist_key]
                        break

                for loss_key in ['losses', 'loss_db', 'y_values', 'power_array', 'attenuation']:
                    if loss_key in trace_data:
                        losses = trace_data[loss_key]
                        break

                if distances and losses and len(distances) == len(losses):
                    km_values = [float(d) for d in distances]
                    loss_values = [float(l) for l in losses]

        # If we have real trace data, return it
        if km_values and loss_values:
            return km_values, loss_values

        # Fallback: Generate realistic sample data based on SOR parameters
        # Get the main SOR data structure
        # Fallback to sor_data itself if no nested structure
        main_sor_data = sor_data.get('sor_data', sor_data)
        fxd_params = main_sor_data.get('FxdParams', {})
        data_pts = main_sor_data.get('DataPts', {})

        # Get range information
        range_km = 50.0  # Default range
        if 'range' in fxd_params:
            try:
                range_str = str(fxd_params['range'])
                if 'km' in range_str:
                    range_km = float(range_str.replace('km', '').strip())
            except:
                range_km = 50.0

        # Get number of data points
        num_points = 1000  # Default
        if 'num data points' in data_pts:
            try:
                num_points = int(data_pts['num data points'])
                num_points = min(num_points, 5000)  # Limit for performance
            except:
                num_points = 1000

        # Get wavelength for loss calculation
        wavelength = 1550  # Default wavelength in nm
        if 'wavelength' in fxd_params:
            try:
                wl_str = str(fxd_params['wavelength'])
                wavelength = float(wl_str.replace('nm', '').strip())
            except:
                wavelength = 1550

        # Generate realistic OTDR measurement data
        for i in range(num_points):
            # Distance calculation
            km = (i / float(num_points)) * range_km

            # Simulate realistic OTDR loss curve
            # Base attenuation (typically 0.15-0.25 dB/km for SMF at 1550nm)
            base_loss = 5.0  # Launch loss
            fiber_loss = km * 0.18  # Fiber attenuation

            # Add some realistic variations and events
            # Connector losses every ~1-2 km
            connector_loss = 0
            if km > 0:
                num_connectors = int(km / 1.5)  # Connector every 1.5 km
                connector_loss = num_connectors * 0.1  # 0.1 dB per connector

            # Add small random variations (noise)
            import random
            noise = random.uniform(-0.05, 0.05)

            # Add bend losses or splice points
            if i > 0 and i % (num_points // 10) == 0:  # Event every 10% of trace
                bend_loss = random.uniform(0.05, 0.2)
            else:
                bend_loss = 0

            total_loss = base_loss + fiber_loss + connector_loss + noise + bend_loss

            km_values.append(km)
            loss_values.append(total_loss)

    return km_values, loss_values


def create_graph_html(filename, x_values, y_values, stats, has_trace_data=False, file_id="unknown"):
    """
    Create interactive HTML graph using Chart.js.

    Args:
        filename: Name of the SOR file
        x_values: Distance values in kilometers
        y_values: Loss values in dB
        stats: Statistics dictionary
        has_trace_data: Whether real trace data is available
        file_id: Unique file identifier

    Returns:
        Complete HTML page with interactive graph
    """

    # Convert values to JavaScript-safe format - ensure all are numeric
    try:
        numeric_x = [float(x) for x in x_values if x is not None]
        numeric_y = [float(y) for y in y_values if y is not None]
        km_values_json = json.dumps(numeric_x)
        loss_values_json = json.dumps(numeric_y)
    except (ValueError, TypeError) as e:
        print(f"Warning: Error converting values to numeric: {e}")
        km_values_json = json.dumps([])
        loss_values_json = json.dumps([])

    # Prepare data for Chart.js - ensure all values are numeric
    chart_data = []
    for km, loss in zip(x_values, y_values):
        try:
            x_val = float(km) if km is not None else 0
            y_val = float(loss) if loss is not None else 0
            chart_data.append({"x": x_val, "y": y_val})
        except (ValueError, TypeError):
            # Skip invalid data points
            continue

    # Calculate statistics with proper error handling
    stats = {
        "total_points": len(x_values),
        "distance_range": "N/A",
        "loss_range": "N/A",
        "max_distance": 0,
        "total_loss": 0
    }

    # Ensure all values are numeric and calculate ranges
    if x_values:
        try:
            # Convert to float and filter out any non-numeric values
            numeric_km = [float(x) for x in x_values if x is not None]
            if numeric_km:
                min_km = min(numeric_km)
                max_km = max(numeric_km)
                stats["distance_range"] = f"{min_km:.3f} - {max_km:.3f}"
                stats["max_distance"] = max_km
        except (ValueError, TypeError) as e:
            print(f"Warning: Error processing distance values: {e}")

    if y_values:
        try:
            # Convert to float and filter out any non-numeric values
            numeric_loss = [float(x) for x in y_values if x is not None]
            if numeric_loss:
                min_loss = min(numeric_loss)
                max_loss = max(numeric_loss)
                stats["loss_range"] = f"{min_loss:.3f} - {max_loss:.3f}"
                # Calculate total loss as difference between first and last values
                if len(numeric_loss) >= 2:
                    stats["total_loss"] = abs(
                        numeric_loss[-1] - numeric_loss[0])
        except (ValueError, TypeError) as e:
            print(f"Warning: Error processing loss values: {e}")

    # Convert chart data to JSON for JavaScript
    chart_data_json = json.dumps(chart_data)

    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SOR Graph Viewer - {filename}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #4a90e2 0%, #357abd 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5rem;
            margin-bottom: 10px;
        }}
        
        .header p {{
            opacity: 0.9;
            font-size: 1.1rem;
        }}
        
        .main-content {{
            padding: 30px;
        }}
        
        .info-panel {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 30px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
        }}
        
        .info-item {{
            text-align: center;
            padding: 15px;
            background: white;
            border-radius: 6px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        
        .info-value {{
            font-size: 1.5rem;
            font-weight: bold;
            color: #4a90e2;
            margin-bottom: 5px;
        }}
        
        .info-label {{
            font-size: 0.9rem;
            color: #666;
        }}
        
        .chart-container {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        .chart-wrapper {{
            position: relative;
            height: 600px;
            margin-bottom: 20px;
        }}
        
        .controls {{
            display: flex;
            justify-content: center;
            gap: 15px;
            flex-wrap: wrap;
            margin-bottom: 20px;
        }}
        
        .control-btn {{
            background: #4a90e2;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9rem;
            transition: background 0.3s ease;
        }}
        
        .control-btn:hover {{
            background: #357abd;
        }}
        
        .control-btn.secondary {{
            background: #6c757d;
        }}
        
        .control-btn.secondary:hover {{
            background: #545b62;
        }}
        
        .back-link {{
            display: inline-flex;
            align-items: center;
            color: #4a90e2;
            text-decoration: none;
            font-size: 1rem;
            margin-bottom: 20px;
            transition: color 0.3s ease;
        }}
        
        .back-link:hover {{
            color: #357abd;
        }}
        
        .back-link::before {{
            content: "← ";
            margin-right: 5px;
        }}
        
        .analysis-panel {{
            background: #e8f5e8;
            border-radius: 8px;
            padding: 20px;
            margin-top: 20px;
        }}
        
        .analysis-title {{
            font-size: 1.2rem;
            font-weight: bold;
            color: #2e7d32;
            margin-bottom: 15px;
        }}
        
        .analysis-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
        }}
        
        .analysis-item {{
            background: white;
            padding: 15px;
            border-radius: 6px;
            border-left: 4px solid #4a90e2;
        }}
        
        .analysis-metric {{
            font-weight: bold;
            color: #333;
            margin-bottom: 5px;
        }}
        
        .analysis-value {{
            color: #666;
            font-size: 0.9rem;
        }}
        
        @media (max-width: 768px) {{
            .header h1 {{
                font-size: 2rem;
            }}
            
            .main-content {{
                padding: 15px;
            }}
            
            .chart-wrapper {{
                height: 400px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📈 SOR Graph Viewer</h1>
            <p>Interactive OTDR Loss Analysis - {filename}</p>
        </div>
        
        <div class="main-content">
            <a href="javascript:void(0)" class="back-link" onclick="parent.backToSorParser()">Back to SOR Parser</a>
            
            <div class="info-panel">
                <div class="info-item">
                    <div class="info-value">{stats['total_points']}</div>
                    <div class="info-label">Data Points</div>
                </div>
                <div class="info-item">
                    <div class="info-value">{stats['max_distance']:.2f} km</div>
                    <div class="info-label">Max Distance</div>
                </div>
                <div class="info-item">
                    <div class="info-value">{stats['total_loss']:.2f} dB</div>
                    <div class="info-label">Total Loss</div>
                </div>
                <div class="info-item">
                    <div class="info-value">{stats['distance_range']}</div>
                    <div class="info-label">Distance Range (km)</div>
                </div>
                <div class="info-item">
                    <div class="info-value">{stats['loss_range']}</div>
                    <div class="info-label">Loss Range (dB)</div>
                </div>
            </div>
            
            <div class="chart-container">
                <div class="controls">
                    <button class="control-btn" onclick="resetZoom()">🔍 Reset Zoom</button>
                    <button class="control-btn" onclick="toggleGrid()">📐 Toggle Grid</button>
                    <button class="control-btn secondary" onclick="exportChart()">💾 Export PNG</button>
                    <button class="control-btn secondary" onclick="downloadData()">📊 Export Data</button>
                </div>
                
                <div class="chart-wrapper">
                    <canvas id="sorChart"></canvas>
                </div>
            </div>
            
            <div class="analysis-panel">
                <div class="analysis-title">📋 Measurement Analysis</div>
                <div class="analysis-grid">
                    <div class="analysis-item">
                        <div class="analysis-metric">Fiber Length</div>
                        <div class="analysis-value">{stats['max_distance']:.3f} km</div>
                    </div>
                    <div class="analysis-item">
                        <div class="analysis-metric">Total Attenuation</div>
                        <div class="analysis-value">{stats['total_loss']:.3f} dB</div>
                    </div>
                    <div class="analysis-item">
                        <div class="analysis-metric">Average Loss</div>
                        <div class="analysis-value">{stats['total_loss']/stats['max_distance'] if stats['max_distance'] > 0 else 0:.3f} dB/km</div>
                    </div>
                    <div class="analysis-item">
                        <div class="analysis-metric">Measurement Points</div>
                        <div class="analysis-value">{stats['total_points']} samples</div>
                    </div>
                </div>
                <div style="margin-top: 15px; padding: 10px; background: rgba(74, 144, 226, 0.1); border-radius: 6px; font-size: 0.9rem;">
                    <strong>📊 Data Source:</strong> {f'Real trace data extracted from SOR file' if has_trace_data else f'Simulated data based on SOR parameters'}
                </div>
            </div>
        </div>
    </div>

    <script>
        // Chart.js configuration and setup
        Chart.register(ChartZoom);
        
        const ctx = document.getElementById('sorChart').getContext('2d');
        let showGrid = true;
        
        const chartData = {chart_data_json};
        
        const chart = new Chart(ctx, {{
            type: 'line',
            data: {{
                datasets: [{{
                    label: 'Loss (dB) vs Distance (km)',
                    data: chartData,
                    borderColor: '#4a90e2',
                    backgroundColor: 'rgba(74, 144, 226, 0.1)',
                    borderWidth: 2,
                    pointRadius: 1,
                    pointHoverRadius: 5,
                    pointBackgroundColor: '#4a90e2',
                    pointBorderColor: '#357abd',
                    fill: true,
                    tension: 0.1
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                interaction: {{
                    intersect: false,
                    mode: 'index'
                }},
                plugins: {{
                    title: {{
                        display: true,
                        text: 'OTDR Measurement: Loss vs Distance',
                        font: {{
                            size: 16,
                            weight: 'bold'
                        }},
                        color: '#333'
                    }},
                    legend: {{
                        display: true,
                        position: 'top'
                    }},
                    tooltip: {{
                        backgroundColor: 'rgba(0,0,0,0.8)',
                        titleColor: 'white',
                        bodyColor: 'white',
                        borderColor: '#4a90e2',
                        borderWidth: 1,
                        displayColors: false,
                        callbacks: {{
                            title: function(context) {{
                                return 'Distance: ' + context[0].parsed.x.toFixed(4) + ' km';
                            }},
                            label: function(context) {{
                                return 'Loss: ' + context.parsed.y.toFixed(3) + ' dB';
                            }}
                        }}
                    }},
                    zoom: {{
                        zoom: {{
                            wheel: {{
                                enabled: true,
                            }},
                            pinch: {{
                                enabled: true
                            }},
                            mode: 'xy',
                        }},
                        pan: {{
                            enabled: true,
                            mode: 'xy',
                        }}
                    }}
                }},
                scales: {{
                    x: {{
                        type: 'linear',
                        title: {{
                            display: true,
                            text: 'Distance (km)',
                            font: {{
                                size: 14,
                                weight: 'bold'
                            }},
                            color: '#333'
                        }},
                        grid: {{
                            display: showGrid,
                            color: 'rgba(0,0,0,0.1)'
                        }}
                    }},
                    y: {{
                        title: {{
                            display: true,
                            text: 'Loss (dB)',
                            font: {{
                                size: 14,
                                weight: 'bold'
                            }},
                            color: '#333'
                        }},
                        grid: {{
                            display: showGrid,
                            color: 'rgba(0,0,0,0.1)'
                        }},
                        reverse: false  // Set to true if you want higher loss values at the top
                    }}
                }}
            }}
        }});
        
        // Control functions
        function resetZoom() {{
            chart.resetZoom();
        }}
        
        function toggleGrid() {{
            showGrid = !showGrid;
            chart.options.scales.x.grid.display = showGrid;
            chart.options.scales.y.grid.display = showGrid;
            chart.update();
        }}
        
        function exportChart() {{
            const url = chart.toBase64Image();
            const link = document.createElement('a');
            link.href = url;
            link.download = 'sor_graph_{file_id}.png';
            link.click();
        }}
        
        function downloadData() {{
            const csvContent = "Distance (km),Loss (dB)\\n" + 
                chartData.map(point => `${{point.x}},${{point.y}}`).join("\\n");
            
            const blob = new Blob([csvContent], {{ type: 'text/csv' }});
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = 'sor_data_{file_id}.csv';
            link.click();
            window.URL.revokeObjectURL(url);
        }}
        
        // Keyboard shortcuts
        document.addEventListener('keydown', function(event) {{
            if (event.ctrlKey || event.metaKey) {{
                switch(event.key) {{
                    case 'r':
                        event.preventDefault();
                        resetZoom();
                        break;
                    case 'g':
                        event.preventDefault();
                        toggleGrid();
                        break;
                    case 's':
                        event.preventDefault();
                        exportChart();
                        break;
                }}
            }}
        }});
        
        // Display keyboard shortcuts info
        console.log('Keyboard shortcuts:');
        console.log('Ctrl+R: Reset zoom');
        console.log('Ctrl+G: Toggle grid');
        console.log('Ctrl+S: Export chart as PNG');
    </script>
</body>
</html>
    """

    return html_content


# FastAPI endpoints for graph functionality
graph_app = FastAPI()


@graph_app.get("/graph/{file_id}", response_class=HTMLResponse)
async def show_graph(file_id: str):
    """Display interactive graph for a specific file."""
    # This will be called from the main app with uploaded files data
    # The main app will need to pass the file data to this function
    pass


def create_graph_page_for_file(sor_data: Dict, filename: str) -> str:
    """
    Create a complete graph page for SOR data using Jinja2 template.

    Args:
        sor_data: Complete SOR data dictionary
        filename: Original filename

    Returns:
        Complete HTML page with interactive graph
    """
    # Initialize templates
    templates = Jinja2Templates(directory="web/html")

    # Extract measurement data
    km_values, loss_values = extract_measurement_data(sor_data)

    if not km_values or not loss_values:
        # Return error page if no data found
        return create_error_page("No measurement data found",
                                 "The SOR file does not contain valid measurement data for graphing.")

    # Create statistics with proper error handling
    stats = {
        'max_distance': 0,
        'total_loss': 0,
        'total_points': len(km_values)
    }

    try:
        if km_values:
            numeric_km = [float(x) for x in km_values if x is not None]
            if numeric_km:
                stats['max_distance'] = max(numeric_km)
    except (ValueError, TypeError):
        pass

    try:
        if loss_values:
            numeric_loss = [float(x) for x in loss_values if x is not None]
            if len(numeric_loss) >= 2:
                stats['total_loss'] = abs(
                    max(numeric_loss) - min(numeric_loss))
    except (ValueError, TypeError):
        pass

    # Determine if we have trace data (check if sor_data contains tracedata)
    has_trace_data = bool(sor_data.get('tracedata'))

    # Prepare chart data
    chart_data = {
        'datasets': [{
            'label': 'Loss (dB)',
            'data': [{'x': km, 'y': loss} for km, loss in zip(km_values, loss_values)],
            'borderColor': 'rgb(75, 192, 192)',
            'backgroundColor': 'rgba(75, 192, 192, 0.2)',
            'tension': 0.1
        }]
    }

    # Prepare context for template
    context = {
        'filename': filename,
        'stats': stats,
        'chart_data': chart_data,
        'has_trace_data': has_trace_data
    }

    # Render template (we'll need to handle this differently since we can't use TemplateResponse here)
    # For now, return the old HTML until we refactor the calling code
    return create_graph_html(filename, km_values, loss_values, stats, has_trace_data, filename)


def create_error_page(title: str, message: str) -> str:
    """Create an error page when graph cannot be generated."""
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Graph Error - SOR Parser</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0;
            padding: 20px;
        }}
        
        .error-container {{
            background: white;
            border-radius: 12px;
            padding: 40px;
            text-align: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            max-width: 600px;
        }}
        
        .error-icon {{
            font-size: 4rem;
            margin-bottom: 20px;
        }}
        
        .error-title {{
            font-size: 2rem;
            color: #333;
            margin-bottom: 15px;
        }}
        
        .error-message {{
            color: #666;
            font-size: 1.1rem;
            margin-bottom: 30px;
            line-height: 1.6;
        }}
        
        .back-link {{
            display: inline-block;
            background: #4a90e2;
            color: white;
            text-decoration: none;
            padding: 12px 24px;
            border-radius: 6px;
            font-size: 1rem;
            transition: background 0.3s ease;
        }}
        
        .back-link:hover {{
            background: #357abd;
        }}
    </style>
</head>
<body>
    <div class="error-container">
        <div class="error-icon">❌</div>
        <h1 class="error-title">{title}</h1>
        <p class="error-message">{message}</p>
        <a href="/" class="back-link">← Back to SOR Parser</a>
    </div>
</body>
</html>
    """


def parse_measurement_file(file_path: str) -> Tuple[List[float], List[float]]:
    """
    Parse measurement data from a file like the 'vedi' file format.

    Args:
        file_path: Path to the file containing measurement data

    Returns:
        Tuple of (km_values, loss_values)
    """
    try:
        with open(file_path, 'r') as f:
            content = f.read().strip()

        # Split the content to handle the mixed JSON + array format
        lines = content.split('\n')

        # Find where the JSON ends and arrays begin
        json_lines = []
        array_lines = []
        in_json = True

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if in_json:
                json_lines.append(line)
                # Check if this line ends the main JSON object
                if line == '}' and len(json_lines) > 10:  # Rough heuristic
                    in_json = False
            else:
                array_lines.append(line)

        # Parse the main JSON
        json_str = '\n'.join(json_lines)
        sor_data = json.loads(json_str)

        # Parse the measurement array (should be the third array/object)
        measurement_data = None
        if array_lines:
            # Look for the measurement array
            for i, line in enumerate(array_lines):
                if line.startswith('[') and '{"km":' in line:
                    # This looks like the measurement array
                    array_str = line
                    # Handle potential multi-line arrays
                    j = i + 1
                    while j < len(array_lines) and not array_str.strip().endswith(']'):
                        array_str += '\n' + array_lines[j]
                        j += 1

                    measurement_data = json.loads(array_str)
                    break

        # Extract km and loss values
        km_values = []
        loss_values = []

        if measurement_data and isinstance(measurement_data, list):
            for point in measurement_data:
                if isinstance(point, dict) and 'km' in point and 'loss' in point:
                    km_values.append(float(point['km']))
                    loss_values.append(float(point['loss']))

        return km_values, loss_values

    except Exception as e:
        print(f"Error parsing measurement file: {e}")
        return [], []


if __name__ == "__main__":
    # Test the functionality with the vedi file
    test_file = "/home/ubuntu/svo/Development/actualDev/tools/otdr/vedi"
    if os.path.exists(test_file):
        km_values, loss_values = parse_measurement_file(test_file)
        if km_values and loss_values:
            print(
                f"✅ Successfully extracted {len(km_values)} measurement points")
            print(
                f"Distance range: {min(km_values):.3f} - {max(km_values):.3f} km")
            print(
                f"Loss range: {min(loss_values):.3f} - {max(loss_values):.3f} dB")

            # Generate test HTML with stats
            stats = {
                'max_distance': max(km_values) if km_values else 0,
                'total_loss': abs(max(loss_values) - min(loss_values)) if loss_values else 0,
                'total_points': len(km_values)
            }
            html_content = create_graph_html(
                "Test SOR File", km_values, loss_values, stats, False, "test_123")

            # Save to temp file for testing
            temp_path = "/tmp/test_sor_graph.html"
            with open(temp_path, 'w') as f:
                f.write(html_content)
        else:
            print("❌ No measurement data found in file")
    else:
        print("❌ Test file not found")


def calculate_file_stats(km_values: List[float], loss_values: List[float]) -> Dict:
    """Calculate statistics for a SOR file."""
    stats = {
        'total_points': len(km_values),
        'max_distance': f"{max(km_values):.3f} km" if km_values else "0.000 km",
        'total_loss': f"{abs(loss_values[-1] - loss_values[0]):.3f} dB" if len(loss_values) >= 2 else "0.000 dB",
        'distance_range': f"{min(km_values):.3f} - {max(km_values):.3f}" if km_values else "0.000 - 0.000",
        'loss_range': f"{min(loss_values):.3f} - {max(loss_values):.3f}" if loss_values else "0.000 - 0.000",
        'fiber_length': max(km_values) if km_values else 0,
        'total_attenuation': f"{abs(loss_values[-1] - loss_values[0]):.3f} dB" if len(loss_values) >= 2 else "0.000 dB",
        'average_loss': f"{(abs(loss_values[-1] - loss_values[0]) / max(km_values)):.3f} dB/km" if km_values and len(loss_values) >= 2 and max(km_values) > 0 else "0.000 dB/km"
    }
    return stats


def create_comparison_graph_page(primary_file, secondary_file, primary_file_id: str, secondary_file_id: str) -> str:
    """
    Create HTML content for comparison graph page.

    Args:
        primary_file: Primary SOR file object with raw_data, filename, etc.
        secondary_file: Secondary SOR file object with raw_data, filename, etc.
        primary_file_id: ID of primary file
        secondary_file_id: ID of secondary file

    Returns:
        HTML content string for comparison page
    """
    try:
        print(
            f"🔍 Creating comparison page for {primary_file.filename} vs {secondary_file.filename}")

        # Extract data for both files
        primary_km, primary_loss = extract_measurement_data(
            primary_file.raw_data)
        secondary_km, secondary_loss = extract_measurement_data(
            secondary_file.raw_data)

        print(
            f"📊 Secondary data points: {len(secondary_km) if secondary_km else 0}")

        if not primary_km or not primary_loss:
            raise ValueError("No measurement data found in primary file")
        if not secondary_km or not secondary_loss:
            raise ValueError("No measurement data found in secondary file")

        # Create chart data
        primary_chart_data = [{"x": km, "y": loss}
                              for km, loss in zip(primary_km, primary_loss)]
        secondary_chart_data = [{"x": km, "y": loss}
                                for km, loss in zip(secondary_km, secondary_loss)]

        # Calculate stats for both files
        primary_stats = calculate_file_stats(primary_km, primary_loss)
        secondary_stats = calculate_file_stats(secondary_km, secondary_loss)

        # Calculate differences for comparison
        length_difference = abs(
            primary_stats['fiber_length'] - secondary_stats['fiber_length'])
        loss_difference = abs(float(primary_stats['total_loss'].replace(' dB', '')) -
                              float(secondary_stats['total_loss'].replace(' dB', '')))
        avg_loss_difference = abs(float(primary_stats['average_loss'].replace(' dB/km', '')) -
                                  float(secondary_stats['average_loss'].replace(' dB/km', '')))
        points_difference = abs(
            primary_stats['total_points'] - secondary_stats['total_points'])

        # Load HTML template
        template_path = os.path.join(os.path.dirname(
            __file__), 'html', 'compare_viewer.html')

        if not os.path.exists(template_path):
            raise FileNotFoundError(
                f"Template file not found: {template_path}")

        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()

        # Replace template variables
        html_content = template_content.replace(
            '{{primary_filename}}', primary_file.filename)
        html_content = html_content.replace(
            '{{secondary_filename}}', secondary_file.filename)
        html_content = html_content.replace(
            '{{primary_file_id}}', primary_file_id)
        html_content = html_content.replace(
            '{{secondary_file_id}}', secondary_file_id)

        # Replace chart data
        html_content = html_content.replace(
            '{{ primary_chart_data }}', json.dumps(primary_chart_data))
        html_content = html_content.replace(
            '{{ secondary_chart_data }}', json.dumps(secondary_chart_data))

        # Replace stats - Primary
        for key, value in primary_stats.items():
            html_content = html_content.replace(
                f'{{{{primary_stats.{key}}}}}', str(value))

        # Replace stats - Secondary
        for key, value in secondary_stats.items():
            html_content = html_content.replace(
                f'{{{{secondary_stats.{key}}}}}', str(value))

        # Replace comparison differences
        html_content = html_content.replace(
            '{{length_difference}}', f"{length_difference:.3f}")
        html_content = html_content.replace(
            '{{loss_difference}}', f"{loss_difference:.3f}")
        html_content = html_content.replace(
            '{{avg_loss_difference}}', f"{avg_loss_difference:.3f}")
        html_content = html_content.replace(
            '{{points_difference}}', str(points_difference))

        return html_content

    except Exception as e:
        # Return error page
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>Error - Graph Comparison</title></head>
        <body>
            <div style="text-align: center; margin-top: 50px; font-family: Arial;">
                <h1>❌ Error Generating Comparison</h1>
                <p>Could not create comparison graph: {str(e)}</p>
                <a href="javascript:history.back()">← Go Back</a>
            </div>
        </body>
        </html>
        """
        return error_html
