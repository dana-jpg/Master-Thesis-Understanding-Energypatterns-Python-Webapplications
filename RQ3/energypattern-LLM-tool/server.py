"""
Flask server with WebSocket support for the green code analyzer.
"""
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import os
import traceback
from threading import Thread

from app.graph import build_graph, GraphState, set_websocket_callback
from app.git_handler import GitHandler
import argparse

app = Flask(__name__, 
            static_folder='static',
            template_folder='static')
app.config['SECRET_KEY'] = 'green-code-analyzer-secret-key'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize Git handler
git_handler = GitHandler()

# Build the analysis graph once
graph = build_graph()


def emit_progress_to_client(message: str, sid=None):
    """Emit progress update to the connected client."""
    if sid:
        socketio.emit('progress', {'message': message}, room=sid)
    else:
        socketio.emit('progress', {'message': message})


def run_analysis(data: dict, sid: str):
    """Run the analysis in a background thread."""
    try:
        input_type = data.get('input_type')
        
        # Set up WebSocket callback
        def progress_callback(msg):
            emit_progress_to_client(msg, sid)
        
        set_websocket_callback(progress_callback)
        
        # Create state based on input type
        if input_type == 'code':
            # Direct code input
            code_content = data.get('code', '')
            if not code_content.strip():
                socketio.emit('error', {'message': 'No code provided'}, room=sid)
                return
            
            emit_progress_to_client('Processing code snippet...', sid)
            emit_progress_to_client('Processing code snippet...', sid)
            state = GraphState(
                input_type='code',
                code_content=code_content,
                analysis_mode=app.config.get('ANALYSIS_MODE', 'suggestion')
            )
            
        elif input_type == 'repo':
            # Git repository URL
            repo_url = data.get('repo_url', '')
            branch = data.get('branch')
            
            if not repo_url:
                socketio.emit('error', {'message': 'No repository URL provided'}, room=sid)
                return
            
            emit_progress_to_client(f'Fetching repository: {repo_url}', sid)
            
            try:
                # Clone or update the repository
                repo_path = git_handler.clone_or_update(
                    repo_url, 
                    branch=branch,
                    progress_callback=lambda msg: emit_progress_to_client(msg, sid)
                )
                
                state = GraphState(
                    input_type='repo',
                    repo_path=repo_path,
                    analysis_mode=app.config.get('ANALYSIS_MODE', 'suggestion')
                )
                
            except Exception as e:
                socketio.emit('error', {'message': f'Failed to fetch repository: {str(e)}'}, room=sid)
                return
                
        elif input_type == 'path':
            # Local file path
            path = data.get('path', '')
            
            if not path:
                socketio.emit('error', {'message': 'No path provided'}, room=sid)
                return
            
            if not os.path.exists(path):
                socketio.emit('error', {'message': f'Path does not exist: {path}'}, room=sid)
                return
            
            emit_progress_to_client(f'Analyzing local path: {path}', sid)
            state = GraphState(
                input_type='path',
                repo_path=path,
                analysis_mode=app.config.get('ANALYSIS_MODE', 'suggestion')
            )
            
        else:
            socketio.emit('error', {'message': f'Invalid input type: {input_type}'}, room=sid)
            return
        
        # Run the analysis
        emit_progress_to_client('Starting analysis...', sid)
        final_state_dict = graph.invoke(state, {"recursion_limit": 10000})
        final_state = GraphState(**final_state_dict)
        
        # Convert findings to JSON-serializable format
        findings_data = [f.to_dict() for f in final_state.findings]
        
        emit_progress_to_client('Analysis complete!', sid)
        
        # Emit the results
        socketio.emit('analysis_complete', {
            'findings': findings_data,
            'total_findings': len(findings_data)
        }, room=sid)
        
    except Exception as e:
        error_msg = f'Analysis failed: {str(e)}'
        print(f"Error during analysis: {traceback.format_exc()}")
        socketio.emit('error', {'message': error_msg}, room=sid)
    finally:
        # Clear the WebSocket callback
        set_websocket_callback(None)


@app.route('/')
def index():
    """Serve the main page."""
    return render_template('index.html')


@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    print(f'Client connected: {request.sid}')
    emit('connected', {'message': 'Connected to Green Code Analyzer'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    print(f'Client disconnected: {request.sid}')


@socketio.on('analyze')
def handle_analyze(data):
    """Handle analysis request from client."""
    print(f'Received analysis request: {data}')
    
    # Run analysis in a background thread
    thread = Thread(target=run_analysis, args=(data, request.sid))
    thread.daemon = True
    thread.start()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Green Code Analyzer Server")
    parser.add_argument(
        "--mode", 
        choices=["suggestion", "detection"], 
        default="suggestion",
        help="Analysis mode: 'suggestion' (patches) or 'detection' (issues only)"
    )
    args = parser.parse_args()
    
    # Store mode in app config
    app.config['ANALYSIS_MODE'] = args.mode

    print("\\n" + "="*60)
    print("Green Code Analyzer - Web Interface")
    print(f"Mode: {args.mode.upper()}")
    print("="*60)
    print("Server starting on http://localhost:5001")
    print("Open your browser and navigate to the URL above")
    print("="*60 + "\\n")
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5001, allow_unsafe_werkzeug=True)
