// ⏱ Tiempo de expiración en milisegundos (15 minutos)
const TIEMPO_EXPIRACION = 15 * 60 * 1000;

let tiempoUltimaActividad = Date.now();

// Actualizar tiempo de actividad cuando el usuario hace algo
function renovarActividad() {
    tiempoUltimaActividad = Date.now();
}

// Monitorear eventos de actividad del usuario
['click', 'keydown', 'scroll', 'mousemove'].forEach(evt =>
    document.addEventListener(evt, renovarActividad)
);

// Verificar cada 10 segundos si la sesión debe cerrarse
setInterval(() => {
    if (Date.now() - tiempoUltimaActividad > TIEMPO_EXPIRACION) {
        cerrarSesion(true);
    }
}, 10000); // cada 10 segundos



function cerrarSesion(auto = false) {
    localStorage.removeItem("token");
    localStorage.removeItem("rol");
    if (auto) alert("Sesión cerrada por inactividad");
    window.location.href = "login.html";
}