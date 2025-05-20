
// Obtener productos desde Flask API

let paginaActual = 1;
const limitePorPagina = 20;
let tipoFiltro = "Todos";
let terminoBusqueda = ""; // valor global actual del filtro

if (document.getElementById("product-list")) {
    cargarProductos(paginaActual);
}


function cargarProductos(pagina, terminoBusqueda = "") {
    let url = `/api/productos?pagina=${pagina}&limite=${limitePorPagina}`;
    
    if (tipoFiltro !== "Todos") {
        url += `&tipo=${encodeURIComponent(tipoFiltro)}`;
    }

    if (terminoBusqueda) {
        url += `&busqueda=${encodeURIComponent(terminoBusqueda)}`;
    }

    fetch(url)
        .then(res => res.json())
        .then(data => {
            mostrarProductos(data.productos);
            mostrarPaginacion(data.total, data.pagina, data.limite);

            const ancla = document.getElementById("scroll-top-productos");
            if (ancla) {
                ancla.scrollIntoView({ behavior: "smooth", block: "start" });
            }
        });
}

function mostrarProductos(productos) {
    const contenedor = document.getElementById("product-list");
    contenedor.innerHTML = "";
    const rol = localStorage.getItem("rol");

    productos.forEach(prod => {
        const card = document.createElement("div");
        card.className = "product-card mb-4";
        card.dataset.nombre = prod.nombre;
        card.dataset.codigo = prod.codigo;

        // Si el producto está en oferta, agregar la etiqueta
        if (prod.oferta == 1 || prod.oferta === true) {
            const ofertaBadge = document.createElement("span");
            ofertaBadge.className = "oferta-badge";
            ofertaBadge.textContent = "Oferta";
            card.appendChild(ofertaBadge);
        }

        let contenidoBoton = "";

        if (rol === "admin") {
            contenidoBoton = `
                <a href="editar_producto.html?id=${prod.id}" class="btn btn-warning">Editar producto</a>
            `;
        } else if (prod.disponible) {
            contenidoBoton = `
                <button class="btn btn-primary" onclick="agregarAlCarrito(${prod.id}, '${prod.nombre}', ${prod.precio})">
                    Agregar al carrito
                </button>
            `;
        } else {
            contenidoBoton = `<span class="badge bg-danger">Agotado</span>`;
        }

        card.innerHTML = `
            <div class="card h-100 position-relative">
                ${prod.oferta == 1 || prod.oferta === true ? `
                    <span class="oferta-badge">Oferta</span>
                ` : ""}
                <img src="${prod.imagen_url || 'https://via.placeholder.com/150'}" class="card-img-top" alt="${prod.nombre}" onerror="this.src='https://via.placeholder.com/150'">
                <div class="card-body d-flex flex-column justify-content-between">
                    <h5 class="card-title">${prod.nombre} - ${prod.sabor}</h5>
                    <p class="card-text">${prod.cantidad}</p>
                    <p class="card-text">Precio: ${prod.precio} Bs</p>
                    ${contenidoBoton}
                </div>
            </div>
        `;
        contenedor.appendChild(card);
    });
}

function mostrarToast(mensaje) {
    const toast = document.createElement("div");
    toast.className = "toast align-items-center text-bg-success position-fixed bottom-0 end-0 m-4 show";
    toast.role = "alert";
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${mensaje}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" onclick="this.parentElement.parentElement.remove()"></button>
        </div>
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

function obtenerCarrito() {
    return JSON.parse(localStorage.getItem("carrito")) || [];
}

function guardarCarrito(carrito) {
    localStorage.setItem("carrito", JSON.stringify(carrito));
}

function agregarAlCarrito(id, nombre, precio) {
    const carrito = obtenerCarrito();
    const item = carrito.find(p => p.id === id);
    if (item) {
        item.cantidad += 1;
    } else {
        carrito.push({ id, nombre, precio, cantidad: 1 });
    }
    guardarCarrito(carrito);
    mostrarToast("Producto agregado al carrito");
    actualizarContadorCarrito();
}

function actualizarContadorCarrito() {
    const carrito = obtenerCarrito();
    const totalItems = carrito.reduce((sum, item) => sum + item.cantidad, 0);
    const contador = document.getElementById("contador-carrito");
    if (contador) {
        contador.textContent = totalItems;
        contador.style.display = totalItems > 0 ? "inline-block" : "none";
    }
}

// Ejecutar al cargar
actualizarContadorCarrito();

// Mostrar carrito
if (document.getElementById("carrito-lista")) {
    const lista = document.getElementById("carrito-lista");
    const totalElem = document.getElementById("carrito-total");
    const btnFinalizar = document.getElementById("btn-finalizar");
    let carrito = obtenerCarrito();
    let total = 0;

    if (carrito.length === 0) {
        lista.innerHTML = '<tr><td colspan="4" class="text-center text-muted">El carrito está vacío</td></tr>';
        totalElem.textContent = "0.00";
        btnFinalizar.disabled = true;
    } else {
        carrito.forEach((item, index) => {
            const subtotal = item.precio * item.cantidad;
            const fila = document.createElement("tr");
            fila.innerHTML = `
                <td>${item.nombre}</td>
                <td>${item.precio.toFixed(2)} Bs</td>
                <td><input type="number" min="1" value="${item.cantidad}" onchange="actualizarCantidad(${index}, this.value)" class="form-control form-control-sm" style="max-width: 70px;"></td>
                <td>${subtotal.toFixed(2)} Bs</td>
            `;
            lista.appendChild(fila);
            total += subtotal;
        });
        totalElem.textContent = total.toFixed(2);
        btnFinalizar.disabled = false;
    }
}

function actualizarCantidad(index, nuevaCantidad) {
    const carrito = obtenerCarrito();
    carrito[index].cantidad = parseInt(nuevaCantidad) || 1;
    guardarCarrito(carrito);
    location.reload();
}

function enviarPedido() {
    const carrito = obtenerCarrito();
    if (carrito.length === 0) return;

    const total = carrito.reduce((sum, item) => sum + item.precio * item.cantidad, 0);
    const nombre_cliente = document.getElementById("nombreCliente")?.value.trim();
    const telefono_cliente = document.getElementById("telefonoCliente")?.value.trim();

    if (!nombre_cliente || !telefono_cliente) {
        alert("⚠️ Por favor, completa tu nombre y teléfono antes de realizar el pedido.");
        return;
    }

    const mensaje = `📦 *Nuevo pedido desde la página web*

🛒 Productos:
${carrito.map(p =>
    `• ${p.nombre} — ${p.cantidad} unidades — ${p.precio} Bs c/u`
).join("\n")}

💵 Total: ${total.toFixed(2)} Bs
👤 Cliente: ${nombre_cliente}
📞 Tel: ${telefono_cliente}
✅ Por favor, confirma este pedido.`;

    const urlWhatsApp = "https://wa.me/59171016195?text=" + encodeURIComponent(mensaje);

    // 👉 abrir WhatsApp inmediatamente tras clic
    window.open(urlWhatsApp, "_blank");

    // Luego registrar el pedido en el backend
    fetch("/api/pedido", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            productos: carrito,
            total: total.toFixed(2),
            nombre_cliente,
            telefono_cliente
        })
    })
    .then(res => res.json())
    .then(() => {
        localStorage.removeItem("carrito");
        setTimeout(() => {
            window.location.href = "productos.html";
        }, 1000);
    });
}

function vaciarCarrito() {
    if (confirm("¿Estás seguro de que deseas vaciar el carrito?")) {
        localStorage.removeItem("carrito");
        location.reload();
    }
}

function mostrarPaginacion(total, pagina, limite) {
    const totalPaginas = Math.ceil(total / limite);
    const contenedor = document.getElementById("paginacion");
    contenedor.innerHTML = "";

    if (totalPaginas <= 1) return;

    const crearBoton = (texto, paginaDestino, activo = false, deshabilitado = false) => {
        const btn = document.createElement("button");
        btn.textContent = texto;
        btn.className = `btn btn-sm mx-1 ${activo ? 'btn-primary' : 'btn-outline-primary'}`;
        btn.disabled = deshabilitado;
        if (!deshabilitado) {
            btn.onclick = () => cargarProductos(paginaDestino, terminoBusqueda);
        }
        return btn;
    };

    // ‹ Anterior
    contenedor.appendChild(crearBoton("‹", pagina - 1, false, pagina === 1));

    // Rangos
    let start = Math.max(1, pagina - 2);
    let end = Math.min(totalPaginas, pagina + 2);

    if (start > 1) {
        contenedor.appendChild(crearBoton("1", 1));
        if (start > 2) {
            const puntos = document.createElement("span");
            puntos.textContent = "...";
            contenedor.appendChild(puntos);
        }
    }

    for (let i = start; i <= end; i++) {
        contenedor.appendChild(crearBoton(i, i, i === pagina));
    }

    if (end < totalPaginas) {
        if (end < totalPaginas - 1) {
            const puntos = document.createElement("span");
            puntos.textContent = "...";
            contenedor.appendChild(puntos);
        }
        contenedor.appendChild(crearBoton(totalPaginas, totalPaginas));
    }

    // Siguiente ›
    contenedor.appendChild(crearBoton("›", pagina + 1, false, pagina === totalPaginas));
}

let debounceTimer;
const inputBusqueda = document.getElementById("busqueda");

if (inputBusqueda) {
    inputBusqueda.addEventListener("input", () => {
        clearTimeout(debounceTimer); // Reinicia el temporizador
        debounceTimer = setTimeout(() => {
            terminoBusqueda = inputBusqueda.value.trim();
            paginaActual = 1;
            cargarProductos(paginaActual, terminoBusqueda);
        }, 200); // Espera 400ms después de la última tecla
    });
}

function filtrarPedidos() {
    const fechaInicio = document.getElementById("fecha-inicio").value;
    const fechaFin = document.getElementById("fecha-fin").value;

    let url = "/api/pedidos";
    const params = [];

    if (fechaInicio) params.push(`fecha_inicio=${fechaInicio}`);
    if (fechaFin) params.push(`fecha_fin=${fechaFin}`);

    if (params.length > 0) {
        url += "?" + params.join("&");
    }

    fetch(url)
        .then(res => res.json())
        .then(mostrarPedidos)
        .catch(err => {
            console.error("Error al filtrar pedidos:", err);
            document.getElementById("tabla-pedidos").innerHTML = `
                <tr><td colspan="6" class="text-danger text-center">⚠️ No se pudieron filtrar los pedidos</td></tr>
            `;
        });
}

function mostrarPedidos(pedidos) {
    const tbody = document.getElementById("tabla-pedidos");
    tbody.innerHTML = "";

    pedidos.forEach((pedido, index) => {
        const fila = document.createElement("tr");
        const productosTexto = JSON.parse(pedido.productos_json)
            .map(p => `📌 <strong>${p.nombre}</strong> — ${p.cantidad} und. — ${p.precio} Bs`)
            .join("<br>");
        fila.innerHTML = `
            <td>${index + 1}</td>
            <td class="text-start">${productosTexto}</td>
            <td><strong>${pedido.total} Bs</strong></td>
            <td>${pedido.nombre_cliente || "-"}</td>
            <td>${pedido.telefono_cliente || "-"}</td>
            <td>${new Date(pedido.fecha).toLocaleString()}</td>
        `;
        tbody.appendChild(fila);
    });
}
