
from flask import Flask, jsonify, request, send_from_directory
import mysql.connector
import pandas as pd
import io
import bcrypt
import os
import jwt

import json
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import random
import string
import threading
from functools import wraps
from flask import send_file
import tempfile
from datetime import datetime, timedelta
from io import BytesIO
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

load_dotenv()
import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

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
        port=int(os.getenv("DB_PORT")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        buffered=True
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

def token_requerido(f):
    @wraps(f)
    def decorador(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return jsonify({"mensaje": "Token requerido"}), 401
        try:
            datos = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"mensaje": "Token expirado"}), 403
        except jwt.InvalidTokenError:
            return jsonify({"mensaje": "Token inválido"}), 403
        return f(datos, *args, **kwargs)
    return decorador
    
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    usuario = data.get("usuario", "").strip()
    contrasena = data.get("contrasena")

    if usuario == "invitado" or usuario == "":
        try:
            with open("token_invitado.json", "r") as f:
                token_data = json.load(f)
                if contrasena == token_data.get("token"):
                    rol = "invitado"
                    token = jwt.encode({
                        "usuario": "invitado",
                        "rol": rol,
                        "exp": datetime.utcnow() + timedelta(hours=3)
                    }, SECRET_KEY, algorithm="HS256")
                    return jsonify({"token": token, "rol": rol})
        except Exception as e:
            return jsonify({"mensaje": f"Error al verificar token dinámico: {str(e)}"}), 500

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
            "exp": datetime.utcnow() + timedelta(hours=3)
        }, SECRET_KEY, algorithm="HS256")
        return jsonify({"token": token, "rol": user["rol"]})
    else:
        return jsonify({"mensaje": "Credenciales inválidas"}), 401

@app.route('/api/productos', methods=['GET'])
def obtener_productos():
    pagina = int(request.args.get("pagina", 1))
    limite = int(request.args.get("limite", 20))
    offset = (pagina - 1) * limite
    tipo = request.args.get("tipo")
    busqueda = request.args.get("busqueda")

    # ✅ Detectar rol desde el token (si está)
    rol = "invitado"  # valor por defecto
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
        try:
            decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            rol = decoded.get("rol", "invitado")
        except Exception as e:
            print("[ERROR] Token inválido:", e)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    condiciones = []
    valores = []

    if tipo and tipo.lower() != "todos":
        condiciones.append("tipo = %s")
        valores.append(tipo)

    if busqueda:
        condiciones.append("LOWER(nombre) LIKE %s")
        valores.append(f"%{busqueda.lower()}%")

    # 🚫 Si es invitado, no mostrar productos agotados
    if rol == "invitado":
        condiciones.append("disponible = 1")

    where_sql = "WHERE " + " AND ".join(condiciones) if condiciones else ""

    # Total para paginación
    cursor.execute(f"SELECT COUNT(*) AS total FROM productos {where_sql}", valores)
    total = cursor.fetchone()["total"]

    # Lista de productos paginados
    valores.extend([limite, offset])
    cursor.execute(f"""
        SELECT id, codigo, nombre, precio, tipo, sabor, cantidad, imagen_url, disponible, promocion
        FROM productos
        {where_sql}
        ORDER BY nombre
        LIMIT %s OFFSET %s
    """, valores)

    productos = cursor.fetchall()
    conn.close()

    return jsonify({
        "productos": productos,
        "pagina": pagina,
        "limite": limite,
        "total": total
    })
    
@app.route('/api/productos/promociones', methods=['GET'])
def obtener_promociones():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT id, codigo, nombre, precio, tipo, sabor, cantidad, imagen_url, disponible, promocion
        FROM productos
        WHERE promocion IS NOT NULL AND promocion != '' AND disponible = 1
        ORDER BY nombre
    """)
    
    productos = cursor.fetchall()
    conn.close()
    return jsonify({"productos": productos})
    
@app.route('/api/pedido', methods=['POST'])
def guardar_pedido():
    data = request.get_json()
    productos = data.get("productos")
    total = data.get("total")
    nombre_cliente = data.get("nombre_cliente")
    telefono_cliente = data.get("telefono_cliente")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO pedidos (productos_json, total, nombre_cliente, telefono_cliente) VALUES (%s, %s, %s, %s)",
        (json.dumps(productos), total, nombre_cliente, telefono_cliente)
    )
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "Pedido recibido correctamente"}), 200

import cloudinary.uploader


@app.route('/api/agregar_producto', methods=['POST'])
def agregar_producto():
    if not verificar_token_admin():
        return jsonify({"mensaje": "Acceso denegado"}), 403

    codigo = request.form.get("codigo")
    nombre = request.form.get("nombre")
    precio = request.form.get("precio")
    tipo = request.form.get("tipo")
    sabor = request.form.get("sabor")
    cantidad = request.form.get("cantidad")
    disponible = request.form.get("disponible", "true").lower() == "true"
    imagen = request.files.get("imagen")

    if not imagen:
        return jsonify({"mensaje": "No se subió ninguna imagen"}), 400

    try:
        resultado = cloudinary.uploader.upload(
            imagen,
            folder="productos_delizia",
            use_filename=True,
            unique_filename=True
        )
        imagen_url = resultado.get("secure_url")
    except Exception as e:
        return jsonify({"mensaje": f"Error al subir imagen a Cloudinary: {str(e)}"}), 500

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO productos (codigo, nombre, precio, tipo, sabor, cantidad, imagen_url, disponible)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (codigo, nombre, precio, tipo, sabor, cantidad, imagen_url, disponible))
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
    sabor = request.form.get("sabor")
    promocion = request.form.get("promocion", "").strip()  # ⬅️ nuevo campo

    disponible = request.form.get("disponible", "true").lower() == "true"

    imagen = request.files.get("imagen")
    imagen_url = None

    conn = get_db_connection()
    cursor = conn.cursor()

    if imagen:
        try:
            resultado = cloudinary.uploader.upload(
                imagen,
                folder="productos_delizia",
                public_id=f"{codigo or nombre}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                resource_type="image"
            )
            imagen_url = resultado.get("secure_url")
        except Exception as e:
            return jsonify({"mensaje": f"Error al subir imagen: {str(e)}"}), 500

        cursor.execute(
            "UPDATE productos SET codigo=%s, nombre=%s, precio=%s, sabor=%s, imagen_url=%s, disponible=%s, promocion=%s WHERE id=%s",
            (codigo, nombre, precio, sabor, imagen_url, disponible, promocion, id_producto)
        )
    else:
        cursor.execute(
            "UPDATE productos SET codigo=%s, nombre=%s, precio=%s, sabor=%s, disponible=%s, promocion=%s WHERE id=%s",
            (codigo, nombre, precio, sabor, disponible, promocion, id_producto)
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

from datetime import datetime, timedelta

@app.route('/api/pedidos', methods=['GET'])
def obtener_pedidos():
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if decoded["rol"] != "admin":
            return jsonify({"mensaje": "No autorizado"}), 403
    except:
        return jsonify({"mensaje": "Token inválido"}), 401

    # Leer filtros de fechas desde la URL
    fecha_inicio = request.args.get("fecha_inicio")
    fecha_fin = request.args.get("fecha_fin")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    condiciones = []
    valores = []

    if fecha_inicio:
        try:
            fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d") + timedelta(hours=4)
            condiciones.append("fecha >= %s")
            valores.append(fecha_inicio_dt)
        except ValueError:
            return jsonify({"mensaje": "Formato de fecha inválido en fecha_inicio"}), 400

    if fecha_fin:
        try:
            # Incluir todo el día seleccionado (hasta las 23:59:59 Bolivia = 03:59:59 UTC del día siguiente)
            fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d") + timedelta(days=1, hours=4)
            condiciones.append("fecha < %s")
            valores.append(fecha_fin_dt)
        except ValueError:
            return jsonify({"mensaje": "Formato de fecha inválido en fecha_fin"}), 400

    where_sql = "WHERE " + " AND ".join(condiciones) if condiciones else ""

    cursor.execute(f"""
        SELECT productos_json, total, nombre_cliente, telefono_cliente, fecha
        FROM pedidos
        {where_sql}
        ORDER BY fecha DESC
    """, valores)

    pedidos = cursor.fetchall()
    conn.close()
    return jsonify(pedidos)
    
# Token dinámico con tiempo restante
def generar_token():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def guardar_token():
    token = generar_token()
    creado_en = datetime.utcnow().isoformat()
    with open("token_invitado.json", "w") as f:
        json.dump({"token": token, "creado_en": creado_en}, f)

def iniciar_token_automatico():
    guardar_token()
    threading.Timer(2700, iniciar_token_automatico).start()


@app.route('/api/token')
def obtener_token_actual():
    print("[INFO] Petición GET /api/token recibida")

    datos = verificar_token_admin()
    if not datos:
        print("[ERROR] No autorizado")
        return jsonify({"mensaje": "No autorizado"}), 403

    try:
        token_path = "token_invitado.json"

        if not os.path.exists(token_path):
            print("[INFO] Archivo no existe, generando...")
            guardar_token()

        print("[INFO] Leyendo token...")
        with open(token_path, "r") as f:
            info = json.load(f)

        print("[INFO] Contenido del token:", info)
        token = info.get("token")
        creado_en_str = info.get("creado_en")

        if not token or not creado_en_str:
            print("[ERROR] Token o fecha inválidos")
            return jsonify({"mensaje": "Token inválido"}), 400

        creado_en = datetime.fromisoformat(creado_en_str)
        ahora = datetime.utcnow()
        expiracion = creado_en + timedelta(minutes=120)

        if ahora >= expiracion:
            print("[INFO] Token expirado, regenerando...")
            guardar_token()
            with open(token_path, "r") as f:
                info = json.load(f)
            token = info.get("token")
            creado_en = datetime.fromisoformat(info.get("creado_en"))
            expiracion = creado_en + datetime.timedelta(minutes=120)

        restante = int((expiracion - ahora).total_seconds())
        restante = max(0, restante)

        print(f"[OK] Token válido: {token}, restante: {restante}s")

        return jsonify({
            "token": token,
            "restante": restante
        })

    except Exception as e:
        print(f"[ERROR FATAL EN TOKEN]: {e}")
        return jsonify({"mensaje": "Error interno al leer el token"}), 500
        
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

@app.route('/api/limpiar_pedidos', methods=['DELETE'])
def limpiar_pedidos():
    datos = verificar_token_admin()
    if not datos:
        return jsonify({"mensaje": "No autorizado"}), 403

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pedidos")
        conn.commit()
        conn.close()
        return jsonify({"mensaje": "Todos los pedidos han sido eliminados"}), 200
    except Exception as e:
        return jsonify({"mensaje": f"Error al eliminar pedidos: {str(e)}"}), 500

@app.route('/api/importar_productos', methods=['POST'])
@token_requerido
def importar_productos(usuario_data):
    if usuario_data["rol"] != "admin":
        return jsonify({"mensaje": "Acceso no autorizado"}), 403

    archivo = request.files.get("archivo")
    if not archivo:
        return jsonify({"mensaje": "Archivo no recibido"}), 400

    try:
        df = pd.read_excel(archivo, engine="openpyxl")

        # ✅ Incluye 'disponible' como columna esperada
        columnas_esperadas = {"codigo", "nombre", "precio", "tipo", "sabor", "cantidad", "imagen_url", "disponible", "promocion"}
        if not columnas_esperadas.issubset(df.columns):
            return jsonify({"mensaje": "Formato incorrecto. Verifica los encabezados de las columnas."}), 400

        for index, row in df.iterrows():
            if pd.isna(row["nombre"]):
                return jsonify({"mensaje": f"Falta el nombre en la fila {index + 2}"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        for _, row in df.iterrows():
            nombre = row["nombre"]
            sabor = row["sabor"] if pd.notna(row.get("sabor")) else ""
            nueva_imagen = row["imagen_url"] if pd.notna(row.get("imagen_url")) else ""

            # ✅ Procesar el valor de 'disponible'
            raw_disponible = str(row.get("disponible")).strip().lower()
            disponible = 1 if raw_disponible in ["1", "true", "sí", "si", "disponible"] else 0

            # Verificar si ya existe
            cursor.execute("SELECT id, imagen_url FROM productos WHERE nombre = %s AND sabor = %s", (nombre, sabor))
            producto_existente = cursor.fetchone()

            if producto_existente:
                imagen_actual = producto_existente[1]
                imagen_final = imagen_actual if imagen_actual else nueva_imagen

                cursor.execute("""
                    UPDATE productos
                    SET codigo = %s,
                        precio = %s,
                        tipo = %s,
                        cantidad = %s,
                        imagen_url = %s,
                        disponible = %s,
                        promocion = %s
                    WHERE nombre = %s AND sabor = %s
                """, (
                    row["codigo"] if pd.notna(row.get("codigo")) else None,
                    row["precio"] if pd.notna(row.get("precio")) else 0.00,
                    row["tipo"] if pd.notna(row.get("tipo")) else "",
                    row["cantidad"] if pd.notna(row.get("cantidad")) else 0,
                    imagen_final,
                    disponible,
                    row["promocion"] if pd.notna(row.get("promocion")) else "",
                    nombre,
                    sabor
                ))
            else:
                cursor.execute("""
                    INSERT INTO productos (codigo, nombre, precio, tipo, sabor, cantidad, imagen_url, disponible, promocion)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)                """, (
                    row["codigo"] if pd.notna(row.get("codigo")) else None,
                    nombre,
                    row["precio"] if pd.notna(row.get("precio")) else 0.00,
                    row["tipo"] if pd.notna(row.get("tipo")) else "",
                    sabor,
                    row["cantidad"] if pd.notna(row.get("cantidad")) else 0,
                    nueva_imagen,
                    disponible,
                    row["promocion"] if pd.notna(row.get("promocion")) else ""
                ))

        conn.commit()
        conn.close()
        return jsonify({"mensaje": "Productos importados y actualizados correctamente"}), 200

    except Exception as e:
        return jsonify({"mensaje": f"Error al procesar el archivo: {str(e)}"}), 500


@app.route('/api/exportar_productos', methods=['GET'])
@token_requerido
def exportar_productos(usuario_data):
    if usuario_data['rol'] != 'admin':
        return jsonify({"mensaje": "Acceso no autorizado"}), 403

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT codigo, nombre, precio, tipo, sabor, cantidad, imagen_url, disponible, promocion FROM productos")
        productos = cursor.fetchall()
        conn.close()

        df = pd.DataFrame(productos)

        # Crear archivo temporal Excel
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            df.to_excel(tmp.name, index=False, engine="openpyxl")
            tmp.seek(0)
            return send_file(
                tmp.name,
                as_attachment=True,
                download_name="productos_exportados.xlsx",
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        return jsonify({"mensaje": f"Error al exportar productos: {str(e)}"}), 500

@app.route('/api/imagenes/<nombre>')
def obtener_imagen(nombre):
    return send_from_directory(images_dir, nombre)


@app.route('/api/eliminar_base_datos', methods=['POST'])
@token_requerido
def eliminar_base_datos(usuario_data):
    if usuario_data["rol"] != "admin":
        return jsonify({"mensaje": "Acceso denegado"}), 403

    datos = request.get_json()
    contrasena = datos.get("contrasena")

    # Verificar contraseña
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT password_hash FROM usuarios WHERE usuario = %s", (usuario_data["usuario"],))
    usuario = cursor.fetchone()

    if not usuario or not bcrypt.checkpw(contrasena.encode(), usuario["password_hash"].encode()):
        conn.close()
        return jsonify({"mensaje": "Contraseña incorrecta"}), 401

    # Borrar tabla de productos
    cursor.execute("DELETE FROM productos")
    conn.commit()
    conn.close()

    return jsonify({"mensaje": "Base de datos eliminada correctamente"}), 200

@app.route('/api/eliminar_producto', methods=['DELETE'])
@token_requerido
def eliminar_producto(usuario_data):
    if usuario_data["rol"] != "admin":
        return jsonify({"mensaje": "Acceso denegado"}), 403

    data = request.get_json()
    producto_id = data.get("id")

    if not producto_id:
        return jsonify({"mensaje": "ID de producto requerido"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM productos WHERE id = %s", (producto_id,))
        conn.commit()
        conn.close()
        return jsonify({"mensaje": "Producto eliminado correctamente"}), 200
    except Exception as e:
        return jsonify({"mensaje": f"Error al eliminar producto: {str(e)}"}), 500
        
# Para busqueda con paginacion
@app.route('/api/producto/<int:producto_id>', methods=['GET'])
def obtener_producto_por_id(producto_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, codigo, nombre, precio, tipo, sabor, cantidad, imagen_url, disponible, promocion
        FROM productos
        WHERE id = %s
    """, (producto_id,))
    producto = cursor.fetchone()
    conn.close()

    if producto:
        return jsonify(producto)
    else:
        return jsonify({"error": "Producto no encontrado"}), 404

@app.route('/api/pedidos/reporte', methods=['GET'])
def generar_reporte_mensual():
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if decoded["rol"] != "admin":
            return jsonify({"mensaje": "No autorizado"}), 403
    except:
        return jsonify({"mensaje": "Token inválido"}), 401

    ahora = datetime.utcnow()
    inicio_mes = ahora.replace(day=1).strftime("%Y-%m-%d")
    siguiente_mes = (ahora.replace(day=28) + timedelta(days=4)).replace(day=1)
    fin_mes = siguiente_mes.strftime("%Y-%m-%d")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT productos_json, total, nombre_cliente, telefono_cliente, fecha
        FROM pedidos
        WHERE fecha >= %s AND fecha < %s
        ORDER BY fecha ASC
    """, (inicio_mes, fin_mes))
    pedidos = cursor.fetchall()
    conn.close()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    elementos = []
    estilos = getSampleStyleSheet()

    elementos.append(Paragraph("Reporte de pedidos del mes actual", estilos["Heading2"]))
    elementos.append(Spacer(1, 12))

    data = [[
        "#", "Producto", "Sabor", "Unidades", "Precio Unit.", "Subtotal", "Cliente", "Teléfono", "Fecha"
    ]]

    contador = 1
    def ajustar_fecha_a_bolivia(fecha_str):
        fecha_utc = datetime.strptime(fecha_str, "%Y-%m-%d %H:%M:%S")
        fecha_bolivia = fecha_utc - timedelta(hours=4)
        return fecha_bolivia.strftime("%d/%m/%Y %H:%M")

    from collections import defaultdict
    total_pedidos = 0
    total_unidades = 0
    total_facturado = 0.0
    clientes = set()
    pedidos_por_dia = defaultdict(int)

    for pedido in pedidos:
        total_pedidos += 1
        clientes.add(pedido.get("nombre_cliente", "-"))
        fecha_solo_dia = str(pedido["fecha"])[:10]
        pedidos_por_dia[fecha_solo_dia] += 1

        productos = json.loads(pedido["productos_json"])
        for prod in productos:
            cantidad = prod["cantidad"]
            subtotal = cantidad * prod["precio"]
            total_unidades += cantidad
            total_facturado += subtotal

            data.append([
                contador,
                prod["nombre"],
                prod.get("sabor", "-"),
                prod["cantidad"],
                f"{prod['precio']} Bs",
                f"{subtotal:.2f} Bs",
                pedido.get("nombre_cliente", "-"),
                pedido.get("telefono_cliente", "-"),
                ajustar_fecha_a_bolivia(str(pedido["fecha"]))
            ])
            contador += 1

    tabla = Table(data, repeatRows=1)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#004AAD")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
    ]))
    elementos.append(tabla)

    promedio = total_facturado / total_pedidos if total_pedidos else 0
    dia_max_pedidos = max(pedidos_por_dia, key=pedidos_por_dia.get)
    dia_max_pedidos_fmt = datetime.strptime(dia_max_pedidos, "%Y-%m-%d").strftime("%d/%m/%Y")

    resumen_data = [[
        "Total pedidos",
        "Productos vendidos",
        "Clientes únicos",
        "Total facturado",
        "Promedio por pedido",
        "Día con más pedidos"
    ], [
        str(total_pedidos),
        str(total_unidades),
        str(len(clientes)),
        f"{total_facturado:.2f} Bs",
        f"{promedio:.2f} Bs",
        dia_max_pedidos_fmt
    ]]

    resumen_tabla = Table(resumen_data)
    resumen_tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
    ]))

    elementos.append(Spacer(1, 24))
    elementos.append(Paragraph("Resumen del mes", estilos["Heading3"]))
    elementos.append(resumen_tabla)

    doc.build(elementos)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="reporte_pedidos_mes_actual.pdf",
        mimetype="application/pdf"
    )

if __name__ == '__main__':
    try:
        conn = get_db_connection()
        print("✅ Conectado correctamente a Railway.")
        conn.close()
    except Exception as e:
        print("❌ Error de conexión:", e)

    app.run(debug=True)
