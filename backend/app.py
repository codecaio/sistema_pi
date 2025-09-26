# --- Centroid Tracker Simples ---
from collections import OrderedDict
import numpy as np

class CentroidTracker:
    def __init__(self, maxDisappeared=40):
        self.nextObjectID = 0
        self.objects = OrderedDict()
        self.disappeared = OrderedDict()
        self.maxDisappeared = maxDisappeared

    def register(self, centroid):
        self.objects[self.nextObjectID] = centroid
        self.disappeared[self.nextObjectID] = 0
        self.nextObjectID += 1

    def deregister(self, objectID):
        del self.objects[objectID]
        del self.disappeared[objectID]

    def update(self, rects):
        if len(rects) == 0:
            for objectID in list(self.disappeared.keys()):
                self.disappeared[objectID] += 1
                if self.disappeared[objectID] > self.maxDisappeared:
                    self.deregister(objectID)
            return self.objects

        inputCentroids = np.zeros((len(rects), 2), dtype="int")
        for (i, (startX, startY, endX, endY)) in enumerate(rects):
            cX = int((startX + endX) / 2.0)
            cY = int((startY + endY) / 2.0)
            inputCentroids[i] = (cX, cY)

        if len(self.objects) == 0:
            for i in range(0, len(inputCentroids)):
                self.register(inputCentroids[i])
        else:
            objectIDs = list(self.objects.keys())
            objectCentroids = list(self.objects.values())
            D = np.linalg.norm(np.array(objectCentroids)[:, np.newaxis] - inputCentroids, axis=2)
            rows = D.min(axis=1).argsort()
            cols = D.argmin(axis=1)[rows]
            usedRows = set()
            usedCols = set()
            for (row, col) in zip(rows, cols):
                if row in usedRows or col in usedCols:
                    continue
                objectID = objectIDs[row]
                self.objects[objectID] = inputCentroids[col]
                self.disappeared[objectID] = 0
                usedRows.add(row)
                usedCols.add(col)
            unusedRows = set(range(0, D.shape[0])).difference(usedRows)
            unusedCols = set(range(0, D.shape[1])).difference(usedCols)
            if D.shape[0] >= D.shape[1]:
                for row in unusedRows:
                    objectID = objectIDs[row]
                    self.disappeared[objectID] += 1
                    if self.disappeared[objectID] > self.maxDisappeared:
                        self.deregister(objectID)
            else:
                for col in unusedCols:
                    self.register(inputCentroids[col])
        return self.objects

# --- Fim Centroid Tracker ---

# Instância global do tracker e histórico de cruzamentos
ct = CentroidTracker(maxDisappeared=20)
track_history = {}
total_in = 0
total_out = 0
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
    """Detecta pessoas, faz tracking e conta entradas/saídas na metade direita (ROI)."""
    global total_in, total_out, track_history
    if model is None:
        return frame

    results = model(frame)[0]
    alerta_ativo = False
    h, w = frame.shape[:2]
    # Linha de contagem: vertical no meio do frame
    line_x = w // 2
    cv2.line(frame, (line_x, 0), (line_x, h), (255, 0, 0), 2)

    rects = []
    for box in results.boxes.data.tolist():
        x1, y1, x2, y2, score, cls = box
        classe = int(cls)
        if classe == 0:  # pessoa
            rects.append((int(x1), int(y1), int(x2), int(y2)))
        # Alerta para faca/tesoura
        if classe in (43, 76):
            alerta_ativo = True
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)
            cv2.putText(frame, f"ALERTA: {int(cls)} {score:.2f}", (int(x1), int(y1) - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)

    objects = ct.update(rects)
    # Para cada objeto rastreado
    for objectID, centroid in objects.items():
        text = f"ID {objectID}"
        cv2.putText(frame, text, (centroid[0] - 10, centroid[1] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        cv2.circle(frame, (centroid[0], centroid[1]), 4, (0, 255, 0), -1)
        prev = track_history.get(objectID, None)
        # Se já tem histórico, verifica cruzamento da linha
        if prev is not None:
            if prev < line_x and centroid[0] >= line_x:
                total_in += 1
            elif prev >= line_x and centroid[0] < line_x:
                total_out += 1
        track_history[objectID] = centroid[0]

    if alerta_ativo:
        print("🚨 OBJETO PERIGOSO DETECTADO! (faca ou tesoura)")
        cv2.putText(frame, "!!! ALERTA: OBJETO DETECTADO !!!", (50, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)

    # Exibe contadores
    cv2.putText(frame, f'Entradas: {total_in}', (50, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,255,0), 3)
    cv2.putText(frame, f'Saidas: {total_out}', (50, 150),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0,0,255), 3)
    cv2.putText(frame, f'Dentro: {total_in - total_out}', (50, 200),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255,255,0), 3)
    return frame


def gen_frames(rtsp_url=None):
    # Se não passar URL ou se a URL não for RTSP, usa webcam local
    use_webcam = False
    if not rtsp_url or rtsp_url.strip() == '' or rtsp_url.startswith('http://'):
        use_webcam = True
    cap = cv2.VideoCapture(0) if use_webcam else cv2.VideoCapture(rtsp_url)
    # Se não conseguir abrir, faz fallback para webcam
    if not cap.isOpened() and not use_webcam:
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
    camera_id = request.args.get('camera_id', type=int)
    rtsp_url = None
    if camera_id:
        camera = Camera.query.get(camera_id)
        if camera:
            rtsp_url = camera.rtsp_url
    return Response(gen_frames(rtsp_url), mimetype='multipart/x-mixed-replace; boundary=frame')

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
