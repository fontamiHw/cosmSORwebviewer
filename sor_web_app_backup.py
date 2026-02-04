#!/usr/bin/env python3
"""
SOR File Parser - FastAPI Web Application

A modern web-based interface for parsing and visualizing SOR files.
Provides the same functionality as the GUI but accessible through any web browser.
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import uuid
import zipfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
# Import the graph viewer functionality (in web directory)
from web.sor_graph_viewer import create_graph_page_for_file

# Initialize Jinja2 templates
templates = Jinja2Templates(directory="web/html")

logger = logging.getLogger()

# Initialize FastAPI app
app = FastAPI(
    title="SOR File Parser Web Interface",
    description="Modern web-based SOR file analysis and visualization tool",
    version="1.0.0"
)

# Data models


class SORFile(BaseModel):
    """Represents an uploaded SOR file with metadata."""
    id: str
    filename: str
    size: int
    upload_time: str
    parsed: bool = False
    chapters: Dict = {}
    raw_data: Dict = {}
    graphs_enabled: bool = False
    is_secondary: bool = False  # Track if this is a secondary file for comparison
    primary_file_id: str = ""  # Link to primary file if this is secondary
    secondary_file_id: str = ""  # Link to secondary file if this is primary


class ChapterInfo(BaseModel):
    """Information about a SOR file chapter."""
    name: str
    item_count: int
    data_type: str
    icon: str


class ParseResponse(BaseModel):
    """Response from SOR file parsing."""
    success: bool
    file_id: str
    chapters: List[ChapterInfo]
    total_items: int
    message: str


# In-memory storage for demo (in production, use database)
uploaded_files: Dict[str, SORFile] = {}
temp_files: Dict[str, str] = {}  # file_id -> temp_file_path


def parse_sor_file(file_path: str, include_trace: bool = False, original_filename: str = None) -> Dict:
    """Parse SOR file using the existing dumpSOR.py script."""
    script_dir = Path(__file__).parent
    dump_sor_path = script_dir / 'dumpSOR.py'

    if not dump_sor_path.exists():
        raise Exception("dumpSOR.py not found in current directory")

    # Build command arguments
    cmd_args = [sys.executable, str(dump_sor_path), file_path]

    # Add trace argument if graph generation is enabled
    if include_trace:
        cmd_args.append('--trace')

    result = subprocess.run(cmd_args, capture_output=True, text=True)

    if result.returncode != 0:
        raise Exception(f"dumpSOR.py failed: {result.stderr}")

    # Write result to JSON file
    json_dir = script_dir / 'JSON'
    json_dir.mkdir(exist_ok=True)

    # Use the original filename if provided, otherwise fall back to temp file name
    if original_filename:
        base_name = Path(original_filename).stem
    else:
        base_name = Path(file_path).stem
    json_file_path = json_dir / f"{base_name}.json"

    # Parse JSON from stdout - handle multiple JSON objects when trace is included
    output = result.stdout.strip()
    parsed_data = parse_data(output, include_trace=include_trace)

    # Write to JSON file
    with open(json_file_path, 'w', encoding='utf-8') as f:
        json.dump(parsed_data, f, indent=2, ensure_ascii=False)
    return parsed_data


def parse_data(output: str, include_trace: bool = False) -> Dict:
    """
    Parse the dumpSOR.py output which can contain:
    - include_trace=True: JSON object + 2 arrays (like vedi file)
    - include_trace=False: Just JSON object (like vediSmall file)

    Returns dict with 3 components: sor_data, ml_events, tracedata
    """

    if include_trace:
        # Parse output with JSON object followed by 2 arrays
        # Structure: {JSON_OBJECT}\n[ARRAY1]\n[ARRAY2]

        # Find the end of the first JSON object
        brace_count = 0
        json_end_pos = 0

        for i, char in enumerate(output):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_end_pos = i + 1
                    break

        # Extract and parse the JSON object (sor_data)
        json_part = output[:json_end_pos].strip()
        sor_data = json.loads(json_part)

        # Extract the remaining part (arrays)
        remaining_output = output[json_end_pos:].strip()

        # Parse the two arrays
        arrays = []
        if remaining_output:
            # Split by lines and find array structures
            lines = remaining_output.split('\n')
            current_array = ""
            bracket_count = 0

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                current_array += line

                # Count brackets to detect complete arrays
                bracket_count += line.count('[') - line.count(']')

                # If brackets are balanced, we have a complete array
                if bracket_count == 0 and current_array:
                    try:
                        array_obj = json.loads(current_array)
                        arrays.append(array_obj)
                        current_array = ""
                    except json.JSONDecodeError:
                        # Continue accumulating if parsing fails
                        pass

        # Ensure we have exactly 2 arrays, pad with empty arrays if needed
        while len(arrays) < 2:
            arrays.append([])

        # Return the 3 JSON objects
        return {
            'sor_data': sor_data,
            'ml_events': arrays[0],  # First array becomes ml_events
            'tracedata': arrays[1]   # Second array becomes tracedata
        }

    else:
        # Standard parsing without trace data - just parse the JSON object
        sor_data = json.loads(output.strip())

        # Return the 3 JSON objects with empty arrays for the other two
        return {
            'sor_data': sor_data,
            'ml_events': [],  # Empty array when trace not included
            'tracedata': []   # Empty array when trace not included
        }


def organize_sor_chapters(data: Dict) -> List[ChapterInfo]:
    """Organize SOR data into chapters with metadata."""
    chapters = []

    # Icons for different data types
    icons = {
        'summary': '📊',
        'events': '⚡',
        'data': '📈',
        'params': '⚙️',
        'blocks': '🧱',
        'folder': '📁'
    }

    # Extract the main SOR data from the new structure
    sor_data = data.get('sor_data', {})

    # 1. Summary chapter (everything not in specific blocks)
    summary_data = {}
    for key, value in sor_data.items():
        if key not in ['blocks', 'KeyEvents', 'DataPts', 'FxdParams', 'GenParams', 'SupParams']:
            summary_data[key] = value

    if summary_data:
        chapters.append(ChapterInfo(
            name="Summary",
            item_count=len(summary_data),
            data_type="Overview",
            icon=icons['summary']
        ))

    # 2. Data sections
    data_sections = [
        ('KeyEvents', 'Key Events', 'Events', 'events'),
        ('DataPts', 'Data Points', 'Measurements', 'data')
    ]

    for key, display_name, type_name, icon_key in data_sections:
        if key in sor_data:
            item_count = len(sor_data[key]) if isinstance(
                sor_data[key], (dict, list)) else 1
            chapters.append(ChapterInfo(
                name=display_name,
                item_count=item_count,
                data_type=type_name,
                icon=icons[icon_key]
            ))

    # 3. Parameters sections
    param_sections = [
        ('FxdParams', 'Fixed Parameters', 'Fixed'),
        ('GenParams', 'General Parameters', 'General'),
        ('SupParams', 'Supplier Parameters', 'Supplier')
    ]

    for key, display_name, type_name in param_sections:
        if key in sor_data:
            item_count = len(sor_data[key]) if isinstance(
                sor_data[key], (dict, list)) else 1
            chapters.append(ChapterInfo(
                name=display_name,
                item_count=item_count,
                data_type=type_name,
                icon=icons['params']
            ))

    # 4. Blocks section
    if 'blocks' in sor_data and sor_data['blocks']:
        blocks_data = sor_data['blocks']
        chapters.append(ChapterInfo(
            name="Blocks",
            item_count=len(blocks_data),
            data_type="Container",
            icon=icons['blocks']
        ))

        # Add individual blocks
        for block_name, block_data in blocks_data.items():
            item_count = len(block_data) if isinstance(
                block_data, (dict, list)) else 1

            # Determine block type
            block_type = "Data Block"
            if isinstance(block_data, dict):
                block_type = block_data.get(
                    'blockType', block_data.get('type', 'Data Block'))

            chapters.append(ChapterInfo(
                name=f"Block: {block_name}",
                item_count=item_count,
                data_type=block_type,
                icon=icons['blocks']
            ))

    # 5. ML Events section (if available from trace data)
    if 'ml_events' in data and data['ml_events']:
        ml_events = data['ml_events']
        if isinstance(ml_events, list) and len(ml_events) > 0:
            chapters.append(ChapterInfo(
                name="ML Events",
                item_count=len(ml_events),
                data_type="ML Analysis",
                icon=icons['events']
            ))

    # 6. Trace Data section (if available from trace data)
    if 'tracedata' in data and data['tracedata']:
        trace_data = data['tracedata']
        if isinstance(trace_data, list) and len(trace_data) > 0:
            chapters.append(ChapterInfo(
                name="Trace Data",
                item_count=len(trace_data),
                data_type="Raw Measurements",
                icon=icons['data']
            ))

    return chapters


def create_chapter_data(data: Dict) -> Dict:
    """Create organized chapter data for frontend."""
    chapters = {}

    # Extract the main SOR data from the new structure
    sor_data = data.get('sor_data', {})

    # 1. Summary chapter
    summary_data = {}
    for key, value in sor_data.items():
        if key not in ['blocks', 'KeyEvents', 'DataPts', 'FxdParams', 'GenParams', 'SupParams']:
            summary_data[key] = value

    if summary_data:
        chapters['Summary'] = summary_data

    # 2. Direct sections
    section_mapping = {
        'KeyEvents': 'Key Events',
        'DataPts': 'Data Points',
        'FxdParams': 'Fixed Parameters',
        'GenParams': 'General Parameters',
        'SupParams': 'Supplier Parameters'
    }

    for key, display_name in section_mapping.items():
        if key in sor_data:
            chapters[display_name] = sor_data[key]

    # 3. Blocks
    if 'blocks' in sor_data:
        chapters['Blocks'] = sor_data['blocks']

        # Add individual blocks
        for block_name, block_data in sor_data['blocks'].items():
            chapters[f'Block: {block_name}'] = {block_name: block_data}

    # 4. ML Events and Trace Data (if available)
    if 'ml_events' in data and data['ml_events']:
        chapters['ML Events'] = data['ml_events']

    if 'tracedata' in data and data['tracedata']:
        chapters['Trace Data'] = data['tracedata']

    return chapters


@app.get("/", response_class=HTMLResponse)
async def get_main_page(request: Request):
    """Serve the main web interface."""
    return templates.TemplateResponse("main_interface.html", {"request": request})


@app.post("/upload")
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SOR File Parser - Web Interface</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(135deg, #4a90e2 0%, #357abd 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
        }
        
        .header p {
            opacity: 0.9;
            font-size: 1.1rem;
        }
        
        .main-content {
            display: flex;
            min-height: 600px;
        }
        
        .upload-section {
            flex: 1;
            padding: 40px;
            border-right: 2px solid #f0f0f0;
        }
        
        .content-section {
            flex: 2;
            padding: 40px;
            display: none;
        }
        
        .upload-area {
            border: 3px dashed #ddd;
            border-radius: 12px;
            padding: 60px 40px;
            text-align: center;
            transition: all 0.3s ease;
            cursor: pointer;
        }
        
        .upload-area:hover,
        .upload-area.dragover {
            border-color: #4a90e2;
            background-color: #f8f9ff;
        }
        
        .upload-icon {
            font-size: 4rem;
            margin-bottom: 20px;
            color: #4a90e2;
        }
        
        .upload-text {
            font-size: 1.2rem;
            color: #666;
            margin-bottom: 20px;
        }
        
        .upload-button {
            background: #4a90e2;
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 8px;
            font-size: 1rem;
            cursor: pointer;
            transition: background 0.3s ease;
        }
        
        .upload-button:hover {
            background: #357abd;
        }
        
        .compare-button {
            background: #6c757d;
            color: white;
            border: none;
            padding: 12px 25px;
            border-radius: 8px;
            font-size: 1rem;
            cursor: not-allowed;
            transition: all 0.3s ease;
            width: 100%;
            margin-bottom: 8px;
        }
        
        .compare-button:enabled {
            background: #28a745;
            cursor: pointer;
        }
        
        .compare-button:enabled:hover {
            background: #218838;
            transform: translateY(-1px);
            box-shadow: 0 4px 15px rgba(40, 167, 69, 0.3);
        }
        
        .button-description {
            font-size: 0.85rem;
            color: #6c757d;
            text-align: center;
            margin-top: 5px;
        }
        
        .file-input {
            display: none;
        }
        
        .options-section {
            margin-top: 25px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            border: 1px solid #e9ecef;
        }
        
        .checkbox-container {
            display: flex;
            align-items: center;
            margin-bottom: 10px;
        }
        
        .checkbox-input {
            margin-right: 12px;
            width: 18px;
            height: 18px;
            cursor: pointer;
            accent-color: #4a90e2;
        }
        
        .checkbox-label {
            font-size: 1rem;
            color: #495057;
            cursor: pointer;
            user-select: none;
            display: flex;
            align-items: center;
        }
        
        .checkbox-label:hover {
            color: #4a90e2;
        }
        
        .checkbox-description {
            font-size: 0.85rem;
            color: #6c757d;
            margin-top: 5px;
            margin-left: 30px;
        }
        
        .loading {
            display: none;
            text-align: center;
            padding: 40px;
        }
        
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #4a90e2;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .chapters-panel {
            background: #f8f9fa;
            border-radius: 8px;
            margin-bottom: 30px;
        }
        
        .chapters-header {
            background: #e9ecef;
            padding: 15px 20px;
            border-radius: 8px 8px 0 0;
            border-bottom: 1px solid #ddd;
        }
        
        .chapters-list {
            max-height: 300px;
            overflow-y: auto;
        }
        
        .chapter-item {
            display: flex;
            align-items: center;
            padding: 12px 20px;
            cursor: pointer;
            transition: background 0.2s ease;
            border-bottom: 1px solid #eee;
        }
        
        .chapter-item:hover {
            background: #e3f2fd;
        }
        
        .chapter-item.active {
            background: #4a90e2;
            color: white;
        }
        
        .chapter-icon {
            margin-right: 12px;
            font-size: 1.2rem;
        }
        
        .chapter-info {
            flex: 1;
        }
        
        .chapter-name {
            font-weight: 500;
            margin-bottom: 2px;
        }
        
        .chapter-details {
            font-size: 0.85rem;
            opacity: 0.7;
        }
        
        .chapter-count {
            background: rgba(0,0,0,0.1);
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.8rem;
        }
        
        .content-viewer {
            background: #f8f9fa;
            border-radius: 8px;
            border: 1px solid #ddd;
        }
        
        .content-header {
            background: #e9ecef;
            padding: 15px 20px;
            border-radius: 8px 8px 0 0;
            border-bottom: 1px solid #ddd;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .content-title {
            font-weight: 600;
            font-size: 1.1rem;
        }
        
        .format-toggle {
            display: flex;
            background: white;
            border-radius: 6px;
            border: 1px solid #ddd;
        }
        
        .format-btn {
            padding: 8px 16px;
            border: none;
            background: none;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        
        .format-btn.active {
            background: #4a90e2;
            color: white;
        }
        
        .content-body {
            padding: 20px;
            max-height: 500px;
            overflow-y: auto;
            font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
            font-size: 0.9rem;
            line-height: 1.5;
        }
        
        .search-box {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 6px;
            margin-bottom: 20px;
            font-size: 1rem;
        }
        
        .stats-panel {
            background: #e8f5e8;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
        }
        
        .stat-item {
            text-align: center;
        }
        
        .stat-value {
            font-size: 2rem;
            font-weight: bold;
            color: #2e7d32;
        }
        
        .stat-label {
            font-size: 0.9rem;
            color: #666;
        }
        
        .clickable-stat {
            cursor: pointer;
            transition: all 0.3s ease;
            border: 2px solid transparent;
            position: relative;
        }
        
        .clickable-stat:hover {
            background: #e3f2fd;
            border-color: #4a90e2;
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(74, 144, 226, 0.3);
        }
        
        .clickable-stat:hover .stat-value {
            color: #357abd;
        }
        
        .clickable-stat::after {
            content: "🔗";
            position: absolute;
            top: 5px;
            right: 5px;
            font-size: 0.8rem;
            opacity: 0.6;
        }
        
        .export-buttons {
            display: flex;
            gap: 10px;
            margin-top: 20px;
        }
        
        .export-btn {
            background: #28a745;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9rem;
            transition: background 0.3s ease;
        }
        
        .export-btn:hover {
            background: #218838;
        }
        
        .error-message {
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
            border: 1px solid #f5c6cb;
        }
        
        .success-message {
            background: #d4edda;
            color: #155724;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
            border: 1px solid #c3e6cb;
        }
        
        /* Dual File Display Styles */
        .secondary-upload-section {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            border: 2px solid #e9ecef;
        }
        
        .secondary-upload-area {
            border: 2px dashed #6c757d;
            border-radius: 8px;
            padding: 30px 20px;
            text-align: center;
            transition: all 0.3s ease;
            cursor: pointer;
            background: white;
        }
        
        .secondary-upload-area:hover {
            border-color: #4a90e2;
            background-color: #f8f9ff;
        }
        
        .dual-file-container {
            display: flex;
            gap: 20px;
            min-height: 600px;
        }
        
        .file-panel {
            flex: 1;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            overflow: hidden;
        }
        
        .primary-panel {
            border-left: 4px solid #4a90e2;
        }
        
        .secondary-panel {
            border-left: 4px solid #28a745;
        }
        
        .panel-header {
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            padding: 15px 20px;
            border-bottom: 1px solid #e0e0e0;
        }
        
        .panel-header h3, .panel-header h4 {
            margin: 0;
            color: #495057;
        }
        
        .file-panel .stats-panel {
            margin: 15px;
            background: #f8f9fa;
        }
        
        .file-panel .search-box {
            margin: 15px;
            width: calc(100% - 30px);
        }
        
        .file-panel .chapters-panel {
            margin: 15px;
        }
        
        .file-panel .content-viewer {
            margin: 15px;
        }
        
        .file-panel .chapters-list {
            max-height: 200px;
            overflow-y: auto;
        }
        
        .file-panel .content-body {
            max-height: 250px;
            overflow-y: auto;
        }

        @media (max-width: 1200px) {
            .dual-file-container {
                flex-direction: column;
            }
            
            .file-panel {
                flex: none;
            }
        }

        /* Graph Container Styles */
        #graphContainer {
            display: none;
        }

        @media (max-width: 768px) {
            .main-content {
                flex-direction: column;
            }
            
            .upload-section {
                border-right: none;
                border-bottom: 2px solid #f0f0f0;
            }
            
            .header h1 {
                font-size: 2rem;
            }
            
            .upload-area {
                padding: 40px 20px;
            }
            
            .dual-file-container {
                flex-direction: column;
                gap: 15px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 SOR File Parser</h1>
            <p>Modern Web-Based Optical Time-Domain Reflectometer Analysis Tool</p>
        </div>
        
        <div class="main-content">
            <div class="upload-section" id="uploadSection">
                <div class="upload-area" id="uploadArea">
                    <div class="upload-icon">📁</div>
                    <div class="upload-text">
                        Drag and drop your SOR file here<br>
                        or click to browse
                    </div>
                    <button class="upload-button" id="chooseFileBtn">
                        Choose File
                    </button>
                    <input type="file" id="fileInput" class="file-input" accept=".sor" onchange="handleFileSelect(this.files[0])">
                </div>
                
                <div class="options-section">
                    <div class="checkbox-container">
                        <input type="checkbox" id="enableGraphs" class="checkbox-input" checked>
                        <label for="enableGraphs" class="checkbox-label">
                            📈 Generate Graph Plots
                        </label>
                    </div>
                    <div class="checkbox-description">
                        Generate visual graphs and plots from the SOR data for enhanced analysis and visualization
                    </div>
                    
                    <div style="margin-top: 20px;">
                        <button class="compare-button" id="compareSorBtn" onclick="compareSorFiles()" disabled>
                            🔍 Compare the 2 SOR
                        </button>
                        <div class="button-description">
                            Compare both SOR files side by side <br> (available when second file is loaded)
                        </div>
                    </div>
                </div>
                
                <div class="loading" id="loadingArea">
                    <div class="spinner"></div>
                    <div>Parsing SOR file...</div>
                </div>
            </div>
            
            <div class="content-section" id="contentSection">
                <!-- Secondary File Upload Section (hidden initially) -->
                <div class="secondary-upload-section" id="secondaryUploadSection" style="display: none;">
                    <h3>📋 Compare with Second SOR File</h3>
                    <div class="secondary-upload-area" id="secondaryUploadArea">
                        <div class="upload-icon">📁</div>
                        <div class="upload-text">Upload second SOR file for comparison</div>
                        <button class="upload-button" id="chooseSecondFileBtn">Choose Second File</button>
                        <input type="file" id="secondFileInput" class="file-input" accept=".sor" onchange="handleSecondFileSelect(this.files[0])">
                    </div>
                </div>
                
                <!-- Dual File Display Container -->
                <div class="dual-file-container" id="dualFileContainer">
                    <!-- Primary File Panel -->
                    <div class="file-panel primary-panel" id="primaryPanel">
                        <div class="panel-header">
                            <h3 id="primaryFileName">� Primary File</h3>
                        </div>
                        
                        <div class="stats-panel" id="primaryStatsPanel">
                            <h4>�📊 File Statistics</h4>
                            <div class="stats-grid" id="primaryStatsGrid">
                                <!-- Primary stats will be populated dynamically -->
                            </div>
                        </div>
                        
                        <input type="text" class="search-box" id="primarySearchBox" placeholder="🔍 Search chapters..." onkeyup="filterChapters('primary')">
                        
                        <div class="chapters-panel">
                            <div class="chapters-header">
                                <h4>📋 SOR Structure Explorer</h4>
                            </div>
                            <div class="chapters-list" id="primaryChaptersList">
                                <!-- Primary chapters will be populated dynamically -->
                            </div>
                        </div>
                        
                        <div class="content-viewer">
                            <div class="content-header">
                                <div class="content-title" id="primaryContentTitle">Select a chapter to view content</div>
                                <div class="format-toggle">
                                    <button class="format-btn active" onclick="setFormat('pretty', 'primary')">Pretty</button>
                                    <button class="format-btn" onclick="setFormat('raw', 'primary')">Raw JSON</button>
                                </div>
                            </div>
                            <div class="content-body" id="primaryContentBody">
                                <div style="text-align: center; color: #666; padding: 40px;">
                                    📄 Content will appear here when you select a chapter
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Secondary File Panel (hidden initially) -->
                    <div class="file-panel secondary-panel" id="secondaryPanel" style="display: none;">
                        <div class="panel-header">
                            <h3 id="secondaryFileName">📄 Secondary File</h3>
                        </div>
                        
                        <div class="stats-panel" id="secondaryStatsPanel">
                            <h4>📊 File Statistics</h4>
                            <div class="stats-grid" id="secondaryStatsGrid">
                                <!-- Secondary stats will be populated dynamically -->
                            </div>
                        </div>
                        
                        <input type="text" class="search-box" id="secondarySearchBox" placeholder="🔍 Search chapters..." onkeyup="filterChapters('secondary')">
                        
                        <div class="chapters-panel">
                            <div class="chapters-header">
                                <h4>📋 SOR Structure Explorer</h4>
                            </div>
                            <div class="chapters-list" id="secondaryChaptersList">
                                <!-- Secondary chapters will be populated dynamically -->
                            </div>
                        </div>
                        
                        <div class="content-viewer">
                            <div class="content-header">
                                <div class="content-title" id="secondaryContentTitle">Select a chapter to view content</div>
                                <div class="format-toggle">
                                    <button class="format-btn active" onclick="setFormat('pretty', 'secondary')">Pretty</button>
                                    <button class="format-btn" onclick="setFormat('raw', 'secondary')">Raw JSON</button>
                                </div>
                            </div>
                            <div class="content-body" id="secondaryContentBody">
                                <div style="text-align: center; color: #666; padding: 40px;">
                                    📄 Content will appear here when you select a chapter
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="export-buttons">
                    <button class="export-btn" onclick="exportCurrent('primary')">💾 Export Primary Chapter</button>
                    <button class="export-btn" onclick="exportAll('primary')">📦 Export All Primary</button>
                    <button class="export-btn" id="exportSecondaryBtn" onclick="exportCurrent('secondary')" style="display: none;">💾 Export Secondary Chapter</button>
                    <button class="export-btn" id="exportAllSecondaryBtn" onclick="exportAll('secondary')" style="display: none;">📦 Export All Secondary</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentFile = null;
        let currentData = null;
        let chapters = {};
        let currentChapter = null;
        let currentFormat = 'pretty';
        
        // Dual file support variables
        let secondaryFile = null;
        let secondaryData = null;
        let secondaryChapters = {};
        let secondaryCurrentChapter = null;
        let secondaryCurrentFormat = 'pretty';
        
        // File upload handling
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        
        // Drag and drop
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });
        
        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });
        
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            
            const files = e.dataTransfer.files;
            if (files.length > 0 && files[0].name.endsWith('.sor')) {
                handleFileSelect(files[0]);
            } else {
                showError('Please select a valid SOR file');
            }
        });
        
        uploadArea.addEventListener('click', (e) => {
            // Only trigger file input if not clicking the button directly
            if (e.target.id !== 'chooseFileBtn') {
                fileInput.click();
            }
        });
        
        // Handle button click separately
        const chooseFileBtn = document.getElementById('chooseFileBtn');
        chooseFileBtn.addEventListener('click', (e) => {
            e.stopPropagation(); // Prevent event bubbling to uploadArea
            fileInput.click();
        });
        
        // Secondary file upload handling
        const secondaryUploadArea = document.getElementById('secondaryUploadArea');
        const secondFileInput = document.getElementById('secondFileInput');
        const chooseSecondFileBtn = document.getElementById('chooseSecondFileBtn');
        
        secondaryUploadArea.addEventListener('click', (e) => {
            if (e.target.id !== 'chooseSecondFileBtn') {
                secondFileInput.click();
            }
        });
        
        chooseSecondFileBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            secondFileInput.click();
        });
        
        secondaryUploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            secondaryUploadArea.classList.add('dragover');
        });
        
        secondaryUploadArea.addEventListener('dragleave', () => {
            secondaryUploadArea.classList.remove('dragover');
        });
        
        secondaryUploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            secondaryUploadArea.classList.remove('dragover');
            
            const files = e.dataTransfer.files;
            if (files.length > 0 && files[0].name.endsWith('.sor')) {
                handleSecondFileSelect(files[0]);
            } else {
                showError('Please select a valid SOR file');
            }
        });
        
        async function handleFileSelect(file) {
            if (!file) return;
            
            if (!file.name.endsWith('.sor')) {
                showError('Please select a valid SOR file (.sor extension)');
                return;
            }
            
            showLoading(true);
            
            const formData = new FormData();
            formData.append('file', file);
            
            // Include graph plotting option
            const enableGraphs = document.getElementById('enableGraphs').checked;
            formData.append('enable_graphs', enableGraphs);
            
            try {
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (result.success) {
                    currentFile = result;
                    currentFile.filename = file.name; // Store the original filename
                    await loadFileData(result.file_id);
                    showSuccess(`Successfully parsed ${file.name}`);
                } else {
                    showError(result.message);
                }
            } catch (error) {
                showError(`Upload failed: ${error.message}`);
            } finally {
                showLoading(false);
            }
        }
        
        async function loadFileData(fileId, isSecondary = false) {
            try {
                const response = await fetch(`/file/${fileId}/chapters`);
                const data = await response.json();
                
                if (isSecondary) {
                    secondaryChapters = data.chapters;
                    secondaryData = data.raw_data;
                    
                    displayStats(data.stats, 'secondary');
                    displayChapters(data.chapter_info, 'secondary');
                    
                    // Show secondary panel and update layout
                    document.getElementById('secondaryPanel').style.display = 'block';
                    document.getElementById('exportSecondaryBtn').style.display = 'inline-block';
                    document.getElementById('exportAllSecondaryBtn').style.display = 'inline-block';
                    
                    // Enable compare button
                    const compareBtn = document.getElementById('compareSorBtn');
                    if (compareBtn) {
                        compareBtn.disabled = false;
                        compareBtn.style.cursor = 'pointer';
                    }
                    
                    // Update secondary file name
                    document.getElementById('secondaryFileName').textContent = `📄 ${secondaryFile.filename || 'Secondary File'}`;
                } else {
                    chapters = data.chapters;
                    currentData = data.raw_data;
                    
                    displayStats(data.stats, 'primary');
                    displayChapters(data.chapter_info, 'primary');
                    
                    // Show content section and secondary upload option
                    document.getElementById('contentSection').style.display = 'block';
                    document.getElementById('secondaryUploadSection').style.display = 'block';
                    
                    // Update primary file name
                    document.getElementById('primaryFileName').textContent = `📄 ${currentFile.filename || 'Primary File'}`;
                }
                
            } catch (error) {
                showError(`Failed to load file data: ${error.message}`);
            }
        }
        
        async function handleSecondFileSelect(file) {
            if (!file) return;
            
            if (!file.name.endsWith('.sor')) {
                showError('Please select a valid SOR file (.sor extension)');
                return;
            }
            
            if (!currentFile) {
                showError('Please upload a primary file first');
                return;
            }
            
            showLoading(true);
            
            const formData = new FormData();
            formData.append('file', file);
            
            // Include graph plotting option
            const enableGraphs = document.getElementById('enableGraphs').checked;
            formData.append('enable_graphs', enableGraphs);
            
            try {
                const response = await fetch(`/upload-secondary/${currentFile.file_id}`, {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (result.success) {
                    secondaryFile = result;
                    secondaryFile.filename = file.name; // Store the original filename
                    await loadFileData(result.file_id, true);
                    showSuccess(`Successfully parsed secondary file ${file.name}`);
                    
                    // Hide secondary upload section
                    document.getElementById('secondaryUploadSection').style.display = 'none';
                } else {
                    showError(result.message);
                }
            } catch (error) {
                showError(`Secondary upload failed: ${error.message}`);
            } finally {
                showLoading(false);
            }
        }
        
        function displayStats(stats, panel = 'primary') {
            const statsGrid = document.getElementById(panel === 'secondary' ? 'secondaryStatsGrid' : 'primaryStatsGrid');
            const fileId = panel === 'secondary' ? (secondaryFile ? secondaryFile.file_id : null) : (currentFile ? currentFile.file_id : null);
            
            statsGrid.innerHTML = `
                <div class="stat-item">
                    <div class="stat-value">${stats.total_chapters}</div>
                    <div class="stat-label">Chapters</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${stats.total_items}</div>
                    <div class="stat-label">Total Items</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${stats.file_size}</div>
                    <div class="stat-label">File Size (KB)</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${stats.blocks_count}</div>
                    <div class="stat-label">Blocks</div>
                </div>
                <div class="stat-item ${stats.graphs_enabled ? 'clickable-stat' : ''}" ${stats.graphs_enabled && fileId ? `onclick="openGraphPage('${fileId}')" title="Click to view interactive graph"` : ''}>
                    <div class="stat-value">${stats.graphs_enabled ? '📈' : '📊'}</div>
                    <div class="stat-label">${stats.graphs_enabled ? 'Graphs Enabled (Click to View)' : 'Data Only'}</div>
                </div>
            `;
        }
        
        function displayChapters(chapterInfo, panel = 'primary') {
            const chaptersList = document.getElementById(panel === 'secondary' ? 'secondaryChaptersList' : 'primaryChaptersList');
            chaptersList.innerHTML = '';
            
            chapterInfo.forEach((chapter, index) => {
                const chapterElement = document.createElement('div');
                chapterElement.className = 'chapter-item';
                chapterElement.onclick = () => selectChapter(chapter.name, chapterElement, panel);
                
                chapterElement.innerHTML = `
                    <div class="chapter-icon">${chapter.icon}</div>
                    <div class="chapter-info">
                        <div class="chapter-name">${chapter.name}</div>
                        <div class="chapter-details">${chapter.data_type}</div>
                    </div>
                    <div class="chapter-count">${chapter.item_count}</div>
                `;
                
                chaptersList.appendChild(chapterElement);
            });
        }
        
        function selectChapter(chapterName, element, panel = 'primary') {
            // Remove active class from chapters in the same panel
            const panelChapters = document.querySelectorAll(`#${panel}ChaptersList .chapter-item`);
            panelChapters.forEach(item => {
                item.classList.remove('active');
            });
            
            // Add active class to selected chapter
            element.classList.add('active');
            
            if (panel === 'secondary') {
                secondaryCurrentChapter = chapterName;
            } else {
                currentChapter = chapterName;
            }
            
            displayChapterContent(chapterName, panel);
        }
        
        function displayChapterContent(chapterName, panel = 'primary') {
            const contentTitle = document.getElementById(panel === 'secondary' ? 'secondaryContentTitle' : 'primaryContentTitle');
            const contentBody = document.getElementById(panel === 'secondary' ? 'secondaryContentBody' : 'primaryContentBody');
            
            contentTitle.textContent = `📄 ${chapterName}`;
            
            const data = panel === 'secondary' ? secondaryChapters[chapterName] : chapters[chapterName];
            const format = panel === 'secondary' ? secondaryCurrentFormat : currentFormat;
            
            if (!data) {
                contentBody.innerHTML = '<div style="text-align: center; color: #666;">No data available for this chapter</div>';
                return;
            }
            
            if (format === 'pretty') {
                contentBody.innerHTML = formatPretty(data);
            } else {
                contentBody.innerHTML = `<pre>${JSON.stringify(data, null, 2)}</pre>`;
            }
        }
        
        function formatPretty(data) {
            if (typeof data !== 'object') {
                return `<div>${data}</div>`;
            }
            
            let html = '';
            
            if (Array.isArray(data)) {
                data.forEach((item, index) => {
                    html += `<div style="margin-bottom: 20px;">
                        <strong>📋 Item ${index + 1}:</strong>
                        <div style="margin-left: 20px; margin-top: 10px;">
                            ${typeof item === 'object' ? `<pre>${JSON.stringify(item, null, 2)}</pre>` : item}
                        </div>
                    </div>`;
                });
            } else {
                Object.entries(data).forEach(([key, value]) => {
                    html += `<div style="margin-bottom: 15px;">
                        <strong>🔹 ${key}:</strong>
                        <div style="margin-left: 20px; margin-top: 5px;">
                            ${typeof value === 'object' ? `<pre>${JSON.stringify(value, null, 2)}</pre>` : value}
                        </div>
                    </div>`;
                });
            }
            
            return html || '<div>No data to display</div>';
        }
        
        function setFormat(format, panel = 'primary') {
            if (panel === 'secondary') {
                secondaryCurrentFormat = format;
            } else {
                currentFormat = format;
            }
            
            // Update button states for the specific panel
            const panelButtons = document.querySelectorAll(`#${panel}Panel .format-btn`);
            panelButtons.forEach(btn => {
                btn.classList.remove('active');
            });
            event.target.classList.add('active');
            
            // Refresh content if chapter is selected
            const selectedChapter = panel === 'secondary' ? secondaryCurrentChapter : currentChapter;
            if (selectedChapter) {
                displayChapterContent(selectedChapter, panel);
            }
        }
        
        function filterChapters(panel = 'primary') {
            const searchBox = document.getElementById(panel === 'secondary' ? 'secondarySearchBox' : 'primarySearchBox');
            const searchTerm = searchBox.value.toLowerCase();
            const chapterItems = document.querySelectorAll(`#${panel}ChaptersList .chapter-item`);
            
            chapterItems.forEach(item => {
                const chapterName = item.querySelector('.chapter-name').textContent.toLowerCase();
                if (chapterName.includes(searchTerm)) {
                    item.style.display = 'flex';
                } else {
                    item.style.display = 'none';
                }
            });
        }
        
        async function exportCurrent(panel = 'primary') {
            const file = panel === 'secondary' ? secondaryFile : currentFile;
            const chapter = panel === 'secondary' ? secondaryCurrentChapter : currentChapter;
            
            if (!chapter) {
                showError(`Please select a chapter to export from ${panel} file`);
                return;
            }
            
            if (!file) {
                showError(`No ${panel} file loaded`);
                return;
            }
            
            try {
                const response = await fetch(`/file/${file.file_id}/export/${encodeURIComponent(chapter)}`);
                const blob = await response.blob();
                
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `${panel}_${chapter.replace(/[^a-zA-Z0-9]/g, '_')}.json`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                
                showSuccess(`Exported ${panel} ${chapter} successfully`);
            } catch (error) {
                showError(`Export failed: ${error.message}`);
            }
        }
        
        async function exportAll(panel = 'primary') {
            const file = panel === 'secondary' ? secondaryFile : currentFile;
            
            if (!file) {
                showError(`No ${panel} file loaded`);
                return;
            }
            
            try {
                const response = await fetch(`/file/${file.file_id}/export-all`);
                const blob = await response.blob();
                
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `${file.file_id}_all_chapters.zip`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                
                showSuccess('Exported all chapters successfully');
            } catch (error) {
                showError(`Export failed: ${error.message}`);
            }
        }
        
        function showLoading(show) {
            document.getElementById('uploadArea').style.display = show ? 'none' : 'block';
            document.getElementById('loadingArea').style.display = show ? 'block' : 'none';
        }
        
        function showError(message) {
            removeMessages();
            const uploadSection = document.getElementById('uploadSection');
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error-message';
            errorDiv.textContent = `❌ ${message}`;
            uploadSection.insertBefore(errorDiv, uploadSection.firstChild);
        }
        
        function showSuccess(message) {
            removeMessages();
            const uploadSection = document.getElementById('uploadSection');
            const successDiv = document.createElement('div');
            successDiv.className = 'success-message';
            successDiv.textContent = `✅ ${message}`;
            uploadSection.insertBefore(successDiv, uploadSection.firstChild);
        }
        
        function removeMessages() {
            const messages = document.querySelectorAll('.error-message, .success-message');
            messages.forEach(msg => msg.remove());
        }
        
        async function openGraphPage(fileId) {
            if (fileId) {
                try {
                    // Fetch graph HTML content
                    const response = await fetch(`/graph/${fileId}`);
                    const graphHtml = await response.text();
                    
                    // Hide main content sections
                    document.getElementById('uploadSection').style.display = 'none';
                    document.getElementById('contentSection').style.display = 'none';
                    
                    // Create or update graph container
                    let graphContainer = document.getElementById('graphContainer');
                    if (!graphContainer) {
                        graphContainer = document.createElement('div');
                        graphContainer.id = 'graphContainer';
                        graphContainer.style.cssText = `
                            position: absolute;
                            top: 0;
                            left: 0;
                            right: 0;
                            bottom: 0;
                            z-index: 1000;
                            background: white;
                            overflow: auto;
                        `;
                        document.body.appendChild(graphContainer);
                    }
                    
                    // Create iframe to contain the graph HTML properly
                    const iframe = document.createElement('iframe');
                    iframe.style.cssText = `
                        width: 100%;
                        height: 100vh;
                        border: none;
                        margin: 0;
                        padding: 0;
                    `;
                    
                    graphContainer.innerHTML = '';
                    graphContainer.appendChild(iframe);
                    
                    // Write the graph HTML to iframe
                    iframe.contentWindow.document.open();
                    iframe.contentWindow.document.write(graphHtml);
                    iframe.contentWindow.document.close();
                    
                    // Make backToSorParser available to iframe
                    iframe.contentWindow.parent.backToSorParser = backToSorParser;
                    
                    graphContainer.style.display = 'block';
                    
                } catch (error) {
                    showError(`Failed to load graph: ${error.message}`);
                }
            } else {
                showError('No file ID provided for graph display');
            }
        }
        
        function backToSorParser() {
            // Hide graph container
            const graphContainer = document.getElementById('graphContainer');
            if (graphContainer) {
                graphContainer.style.display = 'none';
            }
            
            // Show main content
            document.getElementById('uploadSection').style.display = 'block';
            if (currentFile) {
                document.getElementById('contentSection').style.display = 'block';
            }
        }
        
        function compareSorFiles() {
            // Placeholder function - do nothing at the moment as requested
            console.log('Compare SOR files button clicked');
            // Future functionality will be implemented here
        }
    </script>
</body>
</html>
    """


@app.post("/upload", response_model=ParseResponse)
async def upload_sor_file(
    file: UploadFile = File(...),
    enable_graphs: bool = Form(default=False)
):
    """Upload and parse a SOR file."""

    # Validate file type
    if not file.filename or not file.filename.endswith('.sor'):
        raise HTTPException(
            status_code=400, detail="Only .sor files are supported")

    # Generate unique file ID
    file_id = str(uuid.uuid4())
    temp_path = None

    try:
        # Save uploaded file to temporary location
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"{file_id}.sor")

        with open(temp_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # Parse the SOR file (include trace data if graphs are enabled)
        raw_data = parse_sor_file(
            temp_path, include_trace=enable_graphs, original_filename=file.filename)

        # Organize chapters
        chapter_info = organize_sor_chapters(raw_data)
        chapters = create_chapter_data(raw_data)

        # Store file information
        sor_file = SORFile(
            id=file_id,
            filename=file.filename,
            size=len(content),
            upload_time=datetime.now().isoformat(),
            parsed=True,
            chapters=chapters,
            raw_data=raw_data,
            graphs_enabled=enable_graphs
        )

        uploaded_files[file_id] = sor_file
        temp_files[file_id] = temp_path

        return ParseResponse(
            success=True,
            file_id=file_id,
            chapters=chapter_info,
            total_items=sum(chapter.item_count for chapter in chapter_info),
            message=f"SOR file '{file.filename}' uploaded and parsed successfully!"
        )

    except Exception as e:
        # Cleanup on error
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        if file_id in temp_files:
            del temp_files[file_id]
        if file_id in uploaded_files:
            del uploaded_files[file_id]

        raise HTTPException(
            status_code=500, detail=f"Error parsing SOR file: {str(e)}")


@app.post("/upload-secondary/{primary_file_id}", response_model=ParseResponse)
async def upload_secondary_sor_file(
    primary_file_id: str,
    file: UploadFile = File(...),
    enable_graphs: bool = Form(default=False)
):
    """Upload a secondary SOR file for comparison with a primary file."""
    # Validate primary file exists
    if primary_file_id not in uploaded_files:
        raise HTTPException(status_code=404, detail="Primary file not found")

    # Validate file type
    if not file.filename or not file.filename.endswith('.sor'):
        raise HTTPException(
            status_code=400, detail="Only .sor files are supported")

    # Generate unique ID for secondary file
    file_id = str(uuid.uuid4())

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix='.sor') as temp_file:
        content = await file.read()
        temp_file.write(content)
        temp_path = temp_file.name

    try:
        # Parse the SOR file
        parsed_data = parse_sor_file(
            temp_path, include_trace=enable_graphs, original_filename=file.filename)

        # Organize data into chapters
        chapters_info = organize_sor_chapters(parsed_data)
        chapter_data = create_chapter_data(parsed_data)

        # Create SOR file object for secondary file
        sor_file = SORFile(
            id=file_id,
            filename=file.filename,
            size=len(content),
            upload_time=datetime.now().isoformat(),
            parsed=True,
            chapters=chapter_data,
            raw_data=parsed_data,
            graphs_enabled=enable_graphs,
            is_secondary=True,
            primary_file_id=primary_file_id
        )

        # Store in memory
        uploaded_files[file_id] = sor_file
        temp_files[file_id] = temp_path

        # Update primary file to reference this secondary file
        primary_file = uploaded_files[primary_file_id]
        if not hasattr(primary_file, 'secondary_file_id'):
            primary_file.secondary_file_id = file_id

        return ParseResponse(
            success=True,
            file_id=file_id,
            chapters=chapters_info,
            total_items=sum(chapter.item_count for chapter in chapters_info),
            message=f"Secondary SOR file '{file.filename}' uploaded and parsed successfully!"
        )

    except Exception as e:
        # Cleanup on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        if file_id in temp_files:
            del temp_files[file_id]
        if file_id in uploaded_files:
            del uploaded_files[file_id]

        raise HTTPException(
            status_code=500, detail=f"Error parsing SOR file: {str(e)}")
    """Upload and parse a SOR file."""

    # Validate file type
    if not file.filename.endswith('.sor'):
        raise HTTPException(
            status_code=400, detail="Only .sor files are supported")

    # Generate unique file ID
    file_id = str(uuid.uuid4())

    try:
        # Save uploaded file to temporary location
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"{file_id}.sor")

        with open(temp_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # Parse the SOR file (include trace data if graphs are enabled)
        raw_data = parse_sor_file(
            temp_path, include_trace=enable_graphs, original_filename=file.filename)

        # Organize chapters
        chapter_info = organize_sor_chapters(raw_data)
        chapters = create_chapter_data(raw_data)

        # Store file information
        sor_file = SORFile(
            id=file_id,
            filename=file.filename,
            size=len(content),
            upload_time=datetime.now().isoformat(),
            parsed=True,
            chapters=chapters,
            raw_data=raw_data,
            graphs_enabled=enable_graphs
        )

        uploaded_files[file_id] = sor_file
        temp_files[file_id] = temp_path

        graph_status = " with trace data extraction" if enable_graphs else ""
        return ParseResponse(
            success=True,
            file_id=file_id,
            chapters=chapter_info,
            total_items=sum(ch.item_count for ch in chapter_info),
            message=f"Successfully parsed {file.filename}{graph_status}"
        )

    except Exception as e:
        # Clean up on error
        if file_id in temp_files and os.path.exists(temp_files[file_id]):
            os.remove(temp_files[file_id])
            del temp_files[file_id]

        raise HTTPException(
            status_code=500, detail=f"Failed to parse SOR file: {str(e)}")


@app.get("/file/{file_id}/dual-view")
async def get_dual_file_view(file_id: str):
    """Get dual view data for primary and secondary files."""
    if file_id not in uploaded_files:
        raise HTTPException(status_code=404, detail="File not found")

    primary_file = uploaded_files[file_id]

    # Check if this is a primary file with a secondary file
    secondary_file = None
    if hasattr(primary_file, 'secondary_file_id') and primary_file.secondary_file_id:
        secondary_file_id = primary_file.secondary_file_id
        if secondary_file_id in uploaded_files:
            secondary_file = uploaded_files[secondary_file_id]

    # Or check if this is a secondary file
    elif primary_file.is_secondary and primary_file.primary_file_id:
        primary_file_id = primary_file.primary_file_id
        if primary_file_id in uploaded_files:
            actual_primary = uploaded_files[primary_file_id]
            return {
                "primary_file": {
                    "id": actual_primary.id,
                    "filename": actual_primary.filename,
                    "chapters": list(actual_primary.chapters.keys()),
                    "graphs_enabled": actual_primary.graphs_enabled
                },
                "secondary_file": {
                    "id": primary_file.id,
                    "filename": primary_file.filename,
                    "chapters": list(primary_file.chapters.keys()),
                    "graphs_enabled": primary_file.graphs_enabled
                },
                "has_secondary": True
            }

    return {
        "primary_file": {
            "id": primary_file.id,
            "filename": primary_file.filename,
            "chapters": list(primary_file.chapters.keys()),
            "graphs_enabled": primary_file.graphs_enabled
        },
        "secondary_file": {
            "id": secondary_file.id,
            "filename": secondary_file.filename,
            "chapters": list(secondary_file.chapters.keys()),
            "graphs_enabled": secondary_file.graphs_enabled
        } if secondary_file else None,
        "has_secondary": secondary_file is not None
    }


@app.get("/file/{file_id}/chapters")
async def get_file_chapters(file_id: str):
    """Get organized chapters for a parsed file."""

    if file_id not in uploaded_files:
        raise HTTPException(status_code=404, detail="File not found")

    sor_file = uploaded_files[file_id]

    if not sor_file.parsed:
        raise HTTPException(status_code=400, detail="File not parsed yet")

    # Calculate statistics
    stats = {
        "total_chapters": len(sor_file.chapters),
        "total_items": sum(
            len(data) if isinstance(data, (dict, list)) else 1
            for data in sor_file.chapters.values()
        ),
        "file_size": round(sor_file.size / 1024, 1),  # KB
        "blocks_count": len(sor_file.raw_data.get('blocks', {})),
        "graphs_enabled": sor_file.graphs_enabled
    }

    # Organize chapter info
    chapter_info = organize_sor_chapters(sor_file.raw_data)

    return {
        "success": True,
        "chapters": sor_file.chapters,
        "raw_data": sor_file.raw_data,
        "chapter_info": [ch.dict() for ch in chapter_info],
        "stats": stats
    }


@app.get("/file/{file_id}/export/{chapter_name}")
async def export_chapter(file_id: str, chapter_name: str):
    """Export a specific chapter as JSON."""

    if file_id not in uploaded_files:
        raise HTTPException(status_code=404, detail="File not found")

    sor_file = uploaded_files[file_id]

    if chapter_name not in sor_file.chapters:
        raise HTTPException(status_code=404, detail="Chapter not found")

    # Create temporary JSON file
    temp_dir = tempfile.gettempdir()
    export_path = os.path.join(temp_dir, f"{file_id}_{chapter_name}.json")

    with open(export_path, 'w', encoding='utf-8') as f:
        json.dump(sor_file.chapters[chapter_name],
                  f, indent=2, ensure_ascii=False)

    return FileResponse(
        export_path,
        media_type='application/json',
        filename=f"{chapter_name.replace(' ', '_')}.json"
    )


@app.get("/file/{file_id}/export-all")
async def export_all_chapters(file_id: str):
    """Export all chapters as a ZIP file."""
    import zipfile

    if file_id not in uploaded_files:
        raise HTTPException(status_code=404, detail="File not found")

    sor_file = uploaded_files[file_id]

    # Create temporary ZIP file
    temp_dir = tempfile.gettempdir()
    zip_path = os.path.join(temp_dir, f"{file_id}_all_chapters.zip")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for chapter_name, chapter_data in sor_file.chapters.items():
            # Create JSON content
            json_content = json.dumps(
                chapter_data, indent=2, ensure_ascii=False)

            # Add to ZIP
            safe_name = chapter_name.replace(
                ' ', '_').replace(':', '').replace('/', '_')
            zipf.writestr(f"{safe_name}.json", json_content)

    return FileResponse(
        zip_path,
        media_type='application/zip',
        filename=f"{sor_file.filename}_all_chapters.zip"
    )


@app.get("/graph/{file_id}", response_class=HTMLResponse)
async def show_graph_page(file_id: str):
    """Display interactive graph page for a specific SOR file."""

    if file_id not in uploaded_files:
        raise HTTPException(status_code=404, detail="File not found")

    sor_file = uploaded_files[file_id]

    if not sor_file.graphs_enabled:
        raise HTTPException(
            status_code=400, detail="Graphs not enabled for this file")

    # Create graph page using the raw SOR data
    html_content = create_graph_page_for_file(
        sor_data=sor_file.raw_data,
        filename=sor_file.filename,
        file_id=file_id
    )

    return html_content


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "message": "SOR Parser Web API is running"}

if __name__ == "__main__":
    print("🚀 Starting SOR File Parser Web Application...")
    print("📱 Access the web interface at: http://localhost:8000")
    print("📖 API documentation at: http://localhost:8000/docs")
    print("💡 Tip: Use Ctrl+C to stop the server")

    uvicorn.run(
        "sor_web_app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
