"""
Simple Local Grazie API Server

This server provides API endpoints that use ChatGrazie to invoke LLMs.

Usage:
    python grazie_local_server.py

Environment Variables (can be set in .env file):
    GRAZIE_LOCAL_PORT: Port to run the server on (default: 8000)
    GRAZIE_JWT_TOKEN: JWT token (required for ChatGrazie)
    GRAZIE_PROFILE: Grazie profile to use (default: openai-gpt-4o-mini)
"""

import os
import sys
import json
import uuid
from datetime import datetime

# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not installed. Install with: pip install python-dotenv")
    print("Continuing without .env file support...")

try:
    from flask import Flask, request, jsonify

    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    print("Error: Flask not installed. Install with: pip install flask")
    sys.exit(1)

try:
    from grazie_langchain_utils.language_models.grazie import ChatGrazie
    from grazie.api.client.endpoints import GrazieApiGatewayUrls
    from grazie.api.client.gateway import AuthType
    from pydantic.v1 import SecretStr
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

    GRAZIE_AVAILABLE = True
except ImportError:
    GRAZIE_AVAILABLE = False
    print("Error: ChatGrazie not available. Install with: pip install grazie-langchain-utils")
    sys.exit(1)


def convert_to_langchain_messages(messages):
    """Convert message dicts to LangChain message objects."""
    langchain_messages = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get('role', 'user')
            content = msg.get('content', '')

            if role == 'system':
                langchain_messages.append(SystemMessage(content=content))
            elif role == 'assistant':
                langchain_messages.append(AIMessage(content=content))
            else:  # user
                langchain_messages.append(HumanMessage(content=content))
        else:
            # Already a LangChain message object
            langchain_messages.append(msg)

    return langchain_messages


def handle_chat_completion(request_data, grazie_client):
    """Handle chat completion requests using ChatGrazie."""
    # Handle different request formats
    messages = request_data.get('messages', [])
    if not messages and 'message' in request_data:
        messages = [request_data['message']]

    profile = request_data.get('profile', request_data.get('model', 'openai-gpt-4o-mini'))
    temperature = request_data.get('temperature', request_data.get('temp', 1.0))

    # Convert to LangChain message format
    langchain_messages = convert_to_langchain_messages(messages)

    # Invoke ChatGrazie
    response = grazie_client.invoke(langchain_messages)

    # Convert response to API format
    return {
        'id': f'chatcmpl-{uuid.uuid4().hex[:8]}',
        'object': 'chat.completion',
        'created': int(datetime.now().timestamp()),
        'model': profile,
        'choices': [{
            'index': 0,
            'message': {
                'role': 'assistant',
                'content': response.content
            },
            'finish_reason': 'stop'
        }],
        'usage': {
            'prompt_tokens': 0,  # ChatGrazie doesn't always provide token counts
            'completion_tokens': 0,
            'total_tokens': 0
        }
    }


def create_app(grazie_client):
    """Create Flask application with Grazie API endpoints."""
    app = Flask(__name__)

    # Enable CORS for all routes
    @app.after_request
    def after_request(response):
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        return response

    @app.route('/v1/chat/completions', methods=['POST', 'OPTIONS'])
    def chat_completions():
        """Handle chat completion requests."""
        if request.method == 'OPTIONS':
            return '', 200

        try:
            request_data = request.get_json() or {}
            print(f"[Grazie Local Server] Received request with {len(request_data.get('messages', []))} messages")

            response_data = handle_chat_completion(request_data, grazie_client)
            print(f"[Grazie Local Server] Sending response")

            return jsonify(response_data)
        except Exception as e:
            import traceback
            error_msg = str(e)
            traceback.print_exc()
            print(f"[Grazie Local Server] Error: {error_msg}")
            return jsonify({'error': error_msg}), 500

    # Support alternative endpoint paths
    @app.route('/api/v1/chat/completions', methods=['POST', 'OPTIONS'])
    def chat_completions_alt():
        """Alternative chat completion endpoint."""
        return chat_completions()

    @app.route('/health', methods=['GET'])
    def health():
        """Health check endpoint."""
        return jsonify({'status': 'ok', 'backend': 'ChatGrazie'})

    @app.route('/', methods=['GET'])
    def root():
        """Root endpoint."""
        return jsonify({
            'service': 'Grazie Local Server',
            'backend': 'ChatGrazie',
            'endpoints': ['/v1/chat/completions', '/api/v1/chat/completions', '/health']
        })

    return app


def main():
    """Main entry point."""
    port = int(os.getenv('GRAZIE_LOCAL_PORT', '8000'))

    # Read GRAZIE_JWT_TOKEN from environment
    grazie_jwt_token = os.getenv('GRAZIE_JWT_TOKEN')
    if not grazie_jwt_token:
        print("Error: GRAZIE_JWT_TOKEN environment variable is required")
        print("Set it with: export GRAZIE_JWT_TOKEN='your-token'")
        sys.exit(1)

    # Read profile from environment
    grazie_profile = os.getenv('GRAZIE_PROFILE', 'openai-gpt-4o-mini')

    # Initialize ChatGrazie client
    print("Initializing ChatGrazie client...")
    grazie_client = ChatGrazie(
        grazie_jwt_token=SecretStr(grazie_jwt_token),
        client_auth_type=AuthType.APPLICATION,
        client_url=GrazieApiGatewayUrls.PRODUCTION,
        profile=grazie_profile,
        client_agent_name='grazie-local-server',
        client_agent_version='0.1'
    )

    app = create_app(grazie_client)

    print(f"Starting Grazie Local Server on http://localhost:{port}")
    print(f"Backend: ChatGrazie")
    print(f"Profile: {grazie_profile}")
    print(f"GRAZIE_JWT_TOKEN: ***{grazie_jwt_token[-10:] if len(grazie_jwt_token) > 10 else '***'}")
    print(f"Health check: http://localhost:{port}/health")
    print(f"\nServer ready to receive requests!")

    app.run(host='0.0.0.0', port=port, debug=False)


if __name__ == '__main__':
    main()
