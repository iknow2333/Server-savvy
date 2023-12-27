from flask import Flask, request, jsonify, send_file, Response
import paramiko
import select
import os
import time
import re
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://chat.openai.com/"}})

# 存储会话的字典
sessions = {}

def clean_ansi_codes(string):
    ansi_escape = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', string)


# 从环境变量中加载 SSH 私钥
SSH_KEY = os.getenv("SSH_KEY")
if SSH_KEY is None:
    raise ValueError("The environment variable 'SSH_KEY' must be set.")
private_key = paramiko.RSAKey.from_private_key_file(SSH_KEY)

@app.route('/start', methods=['POST'])
def start():
    try:
        data = request.get_json()
        ip = data.get('ip')
        username = data.get('username')
        port = data.get('port', 22)
        
        # 生成默认的 session_id
        default_id = hash(f"{hash(username)}{hash(ip)}{hash(port)}")
        session_id = data.get('session_id', str(default_id))

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, port=port, username=username, key_filename=SSH_KEY)

        shell = client.invoke_shell()
        shell.send("export TERM=dumb\n")
        shell.send("stty -icanon -echo\n")
        shell.send("export PS1=''\n")

        sessions[session_id] = shell

        return jsonify({'status': 'Session started', 'session_id': session_id})  # 在响应中返回 session_id

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/execute', methods=['POST'])
def execute():
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        command = data.get('command')
        full_output = data.get('full_output', False)

        shell = sessions.get(session_id)
        if shell is None:
            return jsonify({'error': 'Session not found'}), 404

        shell.send(command + "\n")
        output = ''

        timeout = 5
        start_time = time.time()
        while True:
            readable, _, _ = select.select([shell], [], [], timeout)
            if readable:
                output += shell.recv(1024).decode(errors='ignore')
            if time.time() - start_time >= timeout:
                break

        output = clean_ansi_codes(output)

        if not full_output:
            output = output[-1024:]

        return output

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_output', methods=['POST'])
def get_output():
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        full_output = data.get('full_output', False)

        shell = sessions.get(session_id)
        if shell is None:
            return jsonify({'error': 'Session not found'}), 404

        output = ''

        timeout = 10   # longer timeout for this route
        start_time = time.time()
        while True:
            readable, _, _ = select.select([shell], [], [], timeout)
            if readable:
                output += shell.recv(1024).decode(errors='ignore')
            if time.time() - start_time >= timeout:
                break

        output = clean_ansi_codes(output)

        if not full_output:
            output = output[-1024:]

        return jsonify({'output': output})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/stop', methods=['POST'])
def stop():
    try:
        data = request.get_json()
        session_id = data.get('session_id')

        shell = sessions.get(session_id)
        if shell is None:
            return jsonify({'error': 'Session not found'}), 404

        shell.close()
        del sessions[session_id]

        return jsonify({'status': 'Session stopped'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/read_ssh_info', methods=['GET'])
def read_ssh_info():
    try:
        # 根据您的操作系统和安全需求，您可能需要更改此文件路径
        file_path = "/home/admin/webdav/private/ssh.txt"

        # 在Python中，'r'标志用于读取文件，'t'标志用于将文件内容解释为文本
        with open(file_path, 'rt') as file:
            file_content = file.read()
        
        return jsonify({'file_content': file_content})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/logo.png', methods=['GET'])
def plugin_logo():
    filename = 'logo.png'
    return send_file(filename, mimetype='image/png')

@app.route('/.well-known/ai-plugin.json', methods=['GET'])
def plugin_manifest():
    with open("./.well-known/ai-plugin.json") as f:
        text = f.read()
    return Response(text, mimetype="application/json")

@app.route('/openapi.yaml', methods=['GET'])
def openapi_spec():
    with open("openapi.yaml") as f:
        text = f.read()
    return Response(text, mimetype="text/yaml")

def main():
    app.run(debug=True, host="0.0.0.0", port=5003)

if __name__ == "__main__":
    main()
