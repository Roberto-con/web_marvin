
from flask import Flask, jsonify, request, send_from_directory
import mysql.connector
import bcrypt
import os
import jwt
import datetime
import json
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import random
import string
import threading

load_dotenv()

SECRET_KEY = 'supersecreto'

base_dir = os.path.abspath(os.path.dirname(__file__))
static_dir = os.path.join(base_dir, '../web')
images_dir = os.path.join(static_dir, 'images')

app = Flask(__name__, static_folder=os.path.join(base_dir, '../web'), static_url_path='/')
app.config['UPLOAD_FOLDER'] = images_dir
CORS(app)

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )

def verificar_token_admin():
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ")[1]
    try:
        datos = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if datos.get("rol") == "admin":
            return datos
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    return None

usuarios = {
    "admin": {"password": "admin123", "rol": "admin"}
}


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    usuario = data.get("usuario")
    contrasena = data.get("contrasena")

    if usuario == "invitado":
        try:
            with open("token_invitado.json", "r") as f:
                token_data = json.load(f)
                if contrasena == token_data.get("token"):
                    rol = "invitado"
                    token = jwt.encode({
                        "usuario": usuario,
                        "rol": rol,
                        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=3)
                    }, SECRET_KEY, algorithm="HS256")
                    return jsonify({"token": token, "rol": rol})
        except:
            return jsonify({"mensaje": "Error al verificar token dinámico"}), 500

    # Login desde base de datos MySQL
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT usuario, password_hash, rol FROM usuarios WHERE usuario = %s", (usuario,))
    user = cursor.fetchone()
    conn.close()

    if user and bcrypt.checkpw(contrasena.encode(), user["password_hash"].encode()):
        token = jwt.encode({
            "usuario": user["usuario"],
            "rol": user["rol"],
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=3)
        }, SECRET_KEY, algorithm="HS256")
        return jsonify({"token": token, "rol": user["rol"]})
    else:
        return jsonify({"mensaje": "Credenciales inválidas"}), 401

@app.route('/api/productos', methods=['GET'])
def obtener_productos():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, codigo, nombre, precio, imagen_url, disponible FROM productos")
    productos = cursor.fetchall()
    conn.close()
    return jsonify(productos)

@app.route('/api/pedido', methods=['POST'])
def guardar_pedido():
    data = request.get_json()
    productos = data.get("productos")
    total = data.get("total")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO pedidos (productos_json, total) VALUES (%s, %s)",
        (json.dumps(productos), total)
    )
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "Pedido recibido correctamente"}), 200

@app.route('/api/agregar_producto', methods=['POST'])
def agregar_producto():
    if not verificar_token_admin():
        return jsonify({"mensaje": "Acceso denegado"}), 403

    codigo = request.form.get("codigo")
    nombre = request.form.get("nombre")
    precio = request.form.get("precio")
    disponible = request.form.get("disponible", "true").lower() == "true"
    imagen = request.files.get("imagen")

    if not imagen:
        return jsonify({"mensaje": "No se subió ninguna imagen"}), 400

    filename_original = secure_filename(imagen.filename)
    extension = os.path.splitext(filename_original)[1]
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    nombre_archivo = f"{os.path.splitext(filename_original)[0]}_{timestamp}{extension}"
    ruta_archivo = os.path.join(app.config['UPLOAD_FOLDER'], nombre_archivo)
    imagen.save(ruta_archivo)

    imagen_url = f"images/{nombre_archivo}"

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO productos (codigo, nombre, precio, imagen_url, disponible) VALUES (%s, %s, %s, %s, %s)",
                   (codigo, nombre, precio, imagen_url, disponible))
    conn.commit()
    conn.close()

    return jsonify({"mensaje": "Producto agregado correctamente"}), 200

@app.route('/api/editar_producto', methods=['POST'])
def editar_producto():
    if not verificar_token_admin():
        return jsonify({"mensaje": "Acceso denegado"}), 403

    id_producto = request.form.get("id")
    codigo = request.form.get("codigo")
    nombre = request.form.get("nombre")
    precio = request.form.get("precio")
    disponible = request.form.get("disponible", "true").lower() == "true"
    imagen = request.files.get("imagen")

    conn = get_db_connection()
    cursor = conn.cursor()

    if imagen:
        filename_original = secure_filename(imagen.filename)
        extension = os.path.splitext(filename_original)[1]
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        nombre_archivo = f"{os.path.splitext(filename_original)[0]}_{timestamp}{extension}"
        ruta_archivo = os.path.join(app.config['UPLOAD_FOLDER'], nombre_archivo)
        imagen.save(ruta_archivo)
        imagen_url = f"images/{nombre_archivo}"

        cursor.execute(
            "UPDATE productos SET codigo=%s, nombre=%s, precio=%s, imagen_url=%s, disponible=%s WHERE id=%s",
            (codigo, nombre, precio, imagen_url, disponible, id_producto)
        )
    else:
        cursor.execute(
            "UPDATE productos SET codigo=%s, nombre=%s, precio=%s, disponible=%s WHERE id=%s",
            (codigo, nombre, precio, disponible, id_producto)
        )

    conn.commit()
    conn.close()
    return jsonify({"mensaje": "Producto actualizado correctamente"}), 200

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/images/<path:filename>')
def serve_images(filename):
    return send_from_directory(os.path.join(app.static_folder, 'images'), filename)

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

@app.route('/api/pedidos', methods=['GET'])
def obtener_pedidos():
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if decoded["rol"] != "admin":
            return jsonify({"mensaje": "No autorizado"}), 403
    except:
        return jsonify({"mensaje": "Token inválido"}), 401

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT productos_json, total FROM pedidos")
    pedidos = cursor.fetchall()
    conn.close()
    return jsonify(pedidos)

# Token dinámico con tiempo restante
def generar_token():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def guardar_token():
    token = generar_token()
    creado_en = datetime.datetime.utcnow().isoformat()
    with open("token_invitado.json", "w") as f:
        json.dump({"token": token, "creado_en": creado_en}, f)

def iniciar_token_automatico():
    guardar_token()
    threading.Timer(2700, iniciar_token_automatico).start()

iniciar_token_automatico()

@app.route('/api/token')
def obtener_token_actual():
    datos = verificar_token_admin()
    if not datos:
        return jsonify({"mensaje": "No autorizado"}), 403

    try:
        with open("token_invitado.json", "r") as f:
            info = json.load(f)
            token = info.get("token")
            creado_en = datetime.datetime.fromisoformat(info.get("creado_en"))
            ahora = datetime.datetime.utcnow()
            expiracion = creado_en + datetime.timedelta(minutes=45)
            restante = int((expiracion - ahora).total_seconds())
            restante = max(0, restante)

            return jsonify({
                "token": token,
                "restante": restante
            })
    except Exception as e:
        return jsonify({"mensaje": "Error al leer el token"}), 500

@app.route('/api/cambiar_contrasena', methods=['POST'])
def cambiar_contrasena():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"mensaje": "No autorizado"}), 403

    token = auth_header.split(" ")[1]
    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if decoded["rol"] != "admin":
            return jsonify({"mensaje": "No autorizado"}), 403
        usuario_actual = decoded["usuario"]
    except:
        return jsonify({"mensaje": "Token inválido"}), 401

    data = request.get_json()
    actual = data.get("actual")
    nueva = data.get("nueva")
    nuevo_usuario = data.get("nuevo_usuario", "").strip()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT password_hash FROM usuarios WHERE usuario = %s", (usuario_actual,))
    user = cursor.fetchone()

    if not user or not bcrypt.checkpw(actual.encode(), user["password_hash"].encode()):
        conn.close()
        return jsonify({"mensaje": "Contraseña actual incorrecta"}), 400

    nuevo_hash = bcrypt.hashpw(nueva.encode(), bcrypt.gensalt()).decode()

    if nuevo_usuario:
        # Verificar que no exista ya ese usuario
        cursor.execute("SELECT id FROM usuarios WHERE usuario = %s", (nuevo_usuario,))
        if cursor.fetchone():
            conn.close()
            return jsonify({"mensaje": "El nuevo nombre de usuario ya está en uso"}), 409

        cursor.execute("UPDATE usuarios SET usuario = %s, password_hash = %s WHERE usuario = %s",
                       (nuevo_usuario, nuevo_hash, usuario_actual))
    else:
        cursor.execute("UPDATE usuarios SET password_hash = %s WHERE usuario = %s",
                       (nuevo_hash, usuario_actual))

    conn.commit()
    conn.close()

    return jsonify({"mensaje": "Credenciales actualizadas correctamente"})

if __name__ == '__main__':
    app.run(debug=True)
