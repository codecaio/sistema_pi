import cv2
from flask import Flask, Response, request, jsonify, render_template
import os
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from ultralytics import YOLO
from flask_cors import CORS





template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../frontend_web'))

app = Flask(__name__, template_folder=template_dir)
app.config['JWT_SECRET_KEY'] = 'change-me'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_TOKEN_LOCATION'] = ['headers', 'query_string']
app.config['JWT_QUERY_STRING_NAME'] = 'token'
CORS(app)


jwt = JWTManager(app)
db = SQLAlchemy(app)

CAMERAS = {
    1: 0  # Default to webcam 0
}
active_camera = 1


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

# Load model (weights must be available in the environment)
try:
    model = YOLO('yolov8x.pt')
except Exception as e:
    model = None
    print(f"Model not loaded: {e}")

def detect_objects(frame):
    """Detecta facas ou tesouras e mostra alerta visual."""
    if model is None:
        return frame

    results = model(frame)[0]
    alerta_ativo = False

    for box in results.boxes.data.tolist():
        x1, y1, x2, y2, score, cls = box
        classe = int(cls)

        if classe in (43, 76):  # 43: faca, 76: tesoura
            alerta_ativo = True
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)
            cv2.putText(frame, f"ALERTA: {int(cls)} {score:.2f}", (int(x1), int(y1) - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)

    if alerta_ativo:
        print("🚨 OBJETO PERIGOSO DETECTADO! (faca ou tesoura)")

        # Exibe um alerta na tela no topo do frame
        cv2.putText(frame, "!!! ALERTA: OBJETO DETECTADO !!!", (50, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)

    return frame


def gen_frames():
    cap = cv2.VideoCapture(0)
    while True:
        success, frame = cap.read()
        if not success:
            break
        frame = detect_objects(frame)
        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Recebendo dados via JSON do fetch()
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return jsonify({'msg': 'Preencha todos os campos'}), 400

        if User.query.filter_by(username=username).first():
            return jsonify({'msg': 'Usuário já existe'}), 400

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        return jsonify({'msg': 'Usuário criado com sucesso'}), 200

    # GET: renderiza o HTML normalmente
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            return jsonify({'msg': 'Credenciais inválidas'}), 401

        token = create_access_token(identity=username)
        return jsonify({'access_token': token})

    # GET: renderiza o HTML de login
    return render_template('login.html')

@app.route('/video_feed')
@jwt_required(locations=['query_string'])  # ESSENCIAL
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/cameras')
@jwt_required()
def cameras():
    return jsonify({'cameras': list(CAMERAS.keys())})

@app.route('/select_camera', methods=['POST'])
@jwt_required()
def select_camera():
    global active_camera
    data = request.get_json()
    cam_id = int(data.get('camera'))
    if cam_id not in CAMERAS:
        return jsonify({'msg': 'Camera not found'}), 404
    active_camera = cam_id
    return jsonify({'active_camera': active_camera})

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')



if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
