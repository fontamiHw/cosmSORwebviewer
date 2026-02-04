#!/usr/bin/env python3
"""
SOR File Parser - FastAPI Web Application

A modern web-based interface for parsing and visualizing SOR files.
Provides the same functionality as the GUI but accessible through any web browser.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
# Import the graph viewer functionality (in web directory)
from web.sor_graph_viewer import (create_comparison_graph_page,
                                  create_graph_page_for_file)

# Initialize Jinja2 templates (will be initialized when first used)
templates = None

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
    global templates
    if templates is None:
        try:
            templates = Jinja2Templates(directory="web/html")
        except Exception:
            # Fallback to simple HTML if Jinja2 is not available
            with open("web/html/main_interface.html", "r") as f:
                html_content = f.read()
            return HTMLResponse(content=html_content)

    return templates.TemplateResponse("main_interface.html", {"request": request})


@app.post("/upload")
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

        return {
            "success": True if chapter_info else False,
            "status": "success" if chapter_info else "error",
            "filename": file.filename,
            "file_id": file_id,
            "stats": {
                "total_points": sum(ch.item_count for ch in chapter_info),
                "total_chapters": len(chapter_info),
                "total_items": sum(ch.item_count for ch in chapter_info),
                "file_size": round(len(content) / 1024, 1),
                "blocks_count": len(raw_data.get('sor_data', {}).get('blocks', {})),
                "wavelength": raw_data.get('sor_data', {}).get('FxdParams', {}).get('wavelength', 'N/A'),
                "pulse_width": raw_data.get('sor_data', {}).get('FxdParams', {}).get('pulse width', 'N/A'),
                "range": raw_data.get('sor_data', {}).get('FxdParams', {}).get('range distance', 'N/A'),
                "resolution": raw_data.get('sor_data', {}).get('FxdParams', {}).get('range resolution', 'N/A'),
                "graphs_enabled": enable_graphs
            } if chapter_info else None,
            "graph_available": enable_graphs,
            "message": f"Successfully parsed {file.filename}" if chapter_info else "Failed to parse file",
            "error": None if chapter_info else "Failed to parse file"
        }

    except Exception as e:
        # Cleanup on error
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        if file_id in temp_files:
            del temp_files[file_id]
        if file_id in uploaded_files:
            del uploaded_files[file_id]

        return {
            "success": False,
            "status": "error",
            "filename": file.filename,
            "file_id": None,
            "stats": None,
            "graph_available": False,
            "message": f"Error parsing {file.filename}: {str(e)}",
            "error": str(e)
        }


@app.post("/upload-secondary/{primary_file_id}")
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

        return {
            "success": True if chapter_info else False,
            "status": "success" if chapter_info else "error",
            "filename": file.filename,
            "file_id": file_id,
            "stats": {
                "total_points": sum(ch.item_count for ch in chapter_info),
                "total_chapters": len(chapter_info),
                "total_items": sum(ch.item_count for ch in chapter_info),
                "file_size": round(len(content) / 1024, 1),
                "blocks_count": len(raw_data.get('sor_data', {}).get('blocks', {})),
                "wavelength": raw_data.get('sor_data', {}).get('FxdParams', {}).get('wavelength', 'N/A'),
                "pulse_width": raw_data.get('sor_data', {}).get('FxdParams', {}).get('pulse width', 'N/A'),
                "range": raw_data.get('sor_data', {}).get('FxdParams', {}).get('range distance', 'N/A'),
                "resolution": raw_data.get('sor_data', {}).get('FxdParams', {}).get('range resolution', 'N/A'),
                "graphs_enabled": enable_graphs
            } if chapter_info else None,
            "graph_available": enable_graphs,
            "message": f"Successfully parsed secondary file {file.filename}" if chapter_info else "Failed to parse file",
            "error": None if chapter_info else "Failed to parse file"
        }

    except Exception as e:
        # Cleanup on error
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        if file_id in temp_files:
            del temp_files[file_id]
        if file_id in uploaded_files:
            del uploaded_files[file_id]

        return {
            "success": False,
            "status": "error",
            "filename": file.filename,
            "file_id": None,
            "stats": None,
            "graph_available": False,
            "message": f"Error parsing secondary file {file.filename}: {str(e)}",
            "error": str(e)
        }


@app.get("/file/{file_id}/chapters")
async def get_file_chapters(file_id: str):
    """Get chapters and metadata for a specific file."""
    if file_id not in uploaded_files:
        raise HTTPException(status_code=404, detail="File not found")

    sor_file = uploaded_files[file_id]
    chapter_info = organize_sor_chapters(sor_file.raw_data)

    return {
        "success": True,
        "chapters": sor_file.chapters,
        "chapter_info": [
            {
                "name": ch.name,
                "item_count": ch.item_count,
                "data_type": ch.data_type,
                "icon": ch.icon
            } for ch in chapter_info
        ],
        "stats": {
            "total_points": sum(ch.item_count for ch in chapter_info),
            "total_chapters": len(chapter_info),
            "total_items": sum(ch.item_count for ch in chapter_info),
            "file_size": round(sor_file.size / 1024, 1),
            "blocks_count": len(sor_file.raw_data.get('sor_data', {}).get('blocks', {})),
            "wavelength": sor_file.raw_data.get('sor_data', {}).get('FxdParams', {}).get('wavelength', 'N/A'),
            "pulse_width": sor_file.raw_data.get('sor_data', {}).get('FxdParams', {}).get('pulse width', 'N/A'),
            "range": sor_file.raw_data.get('sor_data', {}).get('FxdParams', {}).get('range distance', 'N/A'),
            "resolution": sor_file.raw_data.get('sor_data', {}).get('FxdParams', {}).get('range resolution', 'N/A'),
            "graphs_enabled": sor_file.graphs_enabled
        },
        "raw_data": sor_file.raw_data
    }


@app.get("/file/{file_id}/export/{chapter_name}")
async def export_chapter(file_id: str, chapter_name: str):
    """Export a specific chapter as JSON."""
    if file_id not in uploaded_files:
        raise HTTPException(status_code=404, detail="File not found")

    sor_file = uploaded_files[file_id]
    if chapter_name not in sor_file.chapters:
        raise HTTPException(status_code=404, detail="Chapter not found")

    chapter_data = sor_file.chapters[chapter_name]

    # Create a temporary JSON file
    temp_file = tempfile.NamedTemporaryFile(
        mode='w', suffix='.json', delete=False)
    json.dump(chapter_data, temp_file, indent=2, ensure_ascii=False)
    temp_file.close()

    return FileResponse(
        temp_file.name,
        filename=f"{sor_file.filename}_{chapter_name}.json",
        media_type="application/json"
    )


@app.get("/file/{file_id}/export-all")
async def export_all_chapters(file_id: str):
    """Export all chapters as a ZIP file."""
    if file_id not in uploaded_files:
        raise HTTPException(status_code=404, detail="File not found")

    sor_file = uploaded_files[file_id]

    # Create a temporary ZIP file
    temp_zip = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
    temp_zip.close()

    with zipfile.ZipFile(temp_zip.name, 'w') as zip_file:
        for chapter_name, chapter_data in sor_file.chapters.items():
            chapter_json = json.dumps(
                chapter_data, indent=2, ensure_ascii=False)
            zip_file.writestr(f"{chapter_name}.json", chapter_json)

    return FileResponse(
        temp_zip.name,
        filename=f"{sor_file.filename}_all_chapters.zip",
        media_type="application/zip"
    )


@app.get("/graph/{file_id}")
async def get_graph_page(file_id: str):
    """Get graph page for a specific file."""
    try:
        # Find the file by file_id
        if file_id not in uploaded_files:
            raise HTTPException(status_code=404, detail="File not found")

        sor_file = uploaded_files[file_id]

        if not sor_file.graphs_enabled:
            raise HTTPException(
                status_code=400, detail="Graphs not enabled for this file")

        # Create the graph page HTML content
        html_content = create_graph_page_for_file(
            sor_file.raw_data, sor_file.filename)
        return HTMLResponse(content=html_content)

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error generating graph: {str(e)}")


@app.get("/compare-graph/{primary_file_id}/{secondary_file_id}")
async def get_compare_graph_page(primary_file_id: str, secondary_file_id: str):
    """Get comparison graph page for two files."""
    print(
        f"🔍 Compare graph requested: primary={primary_file_id}, secondary={secondary_file_id}")

    try:
        # Find both files
        if primary_file_id not in uploaded_files:
            raise HTTPException(
                status_code=404, detail="Primary file not found")
        if secondary_file_id not in uploaded_files:
            raise HTTPException(
                status_code=404, detail="Secondary file not found")

        primary_file = uploaded_files[primary_file_id]
        secondary_file = uploaded_files[secondary_file_id]

        print(
            f"✅ Found files: {primary_file.filename} and {secondary_file.filename}")

        if not primary_file.graphs_enabled:
            print(
                f"❌ Graphs not enabled for primary file: {primary_file.filename}")
            raise HTTPException(
                status_code=400, detail="Graphs not enabled for primary file")
        if not secondary_file.graphs_enabled:
            print(
                f"❌ Graphs not enabled for secondary file: {secondary_file.filename}")
            raise HTTPException(
                status_code=400, detail="Graphs not enabled for secondary file")

        # Create the comparison graph page HTML content
        html_content = create_comparison_graph_page(
            primary_file, secondary_file, primary_file_id, secondary_file_id)

        return HTMLResponse(content=html_content)

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error generating comparison graph: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "message": "SOR Parser Web API is running"}


if __name__ == "__main__":
    print("🚀 Starting SOR File Parser Web Application...")
    print("📱 Access the web interface at: http://localhost:8800")
    print("📖 API documentation at: http://localhost:8800/docs")
    print("💡 Tip: Use Ctrl+C to stop the server")

    uvicorn.run(
        "sor_web_app:app",
        host="0.0.0.0",
        port=8800,
        reload=True,
        log_level="info"
    )
