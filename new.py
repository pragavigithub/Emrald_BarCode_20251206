from flask import Flask, request, jsonify, send_from_directory
from datetime import datetime
import os

app = Flask(__name__)

@app.route('/', methods=['GET'])
def serve_html():
    # The HTML file should be placed in a folder named 'static'
    return send_from_directory('templates', 'Qr.html')

@app.route('/receive_qr', methods=['POST'])
def receive_qr():
    try:
        data = request.get_json(force=True)
        # basic validation/example processing
        required = ['id','po','item','batch','qty','pack','grn_date','exp_date']
        missing = [k for k in required if k not in data]
        if missing:
            return jsonify({"ok": False, "error": "Missing fields", "missing": missing}), 400

        # example: convert dates to iso format if needed
        try:
            grn = datetime.fromisoformat(data['grn_date']).date().isoformat()
            exp = datetime.fromisoformat(data['exp_date']).date().isoformat()
        except Exception:
            grn = data['grn_date']
            exp = data['exp_date']

        # TODO: persist to DB or process as required
        print("Received QR payload:", data)

        return jsonify({"ok": True, "received": data}), 200

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == '__main__':
    # for development only
    app.run(host="0.0.0.0", port=5001, debug=True)
