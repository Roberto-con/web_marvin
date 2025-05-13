
// Obtener productos desde Flask API
if (document.getElementById("product-list")) {
    fetch("/api/productos")
        .then(res => res.json())
        .then(data => mostrarProductos(data));
}

function mostrarProductos(productos) {
    const contenedor = document.getElementById("product-list");
    const rol = localStorage.getItem("rol");

    productos.forEach(prod => {
        const card = document.createElement("div");
        card.className = "product-card mb-4";
        card.dataset.nombre = prod.nombre;
        card.dataset.codigo = prod.codigo;
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
            <div class="card h-100">
                <img src="${prod.imagen_url || 'https://via.placeholder.com/150'}" class="card-img-top" alt="${prod.nombre}" onerror="this.src='https://via.placeholder.com/150'">
                <div class="card-body d-flex flex-column justify-content-between">
                    <h5 class="card-title">${prod.nombre}</h5>
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
    const nombre_cliente = document.getElementById("nombreCliente")?.value || "";
    const telefono_cliente = document.getElementById("telefonoCliente")?.value || "";

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
        window.open(urlWhatsApp, "_blank");
        localStorage.removeItem("carrito");
        setTimeout(() => {
            window.location.href = "productos.html";
        }, 1000);
    });
}

// Búsqueda dinámica
if (document.getElementById("busqueda")) {
    document.getElementById("busqueda").addEventListener("input", e => {
        const termino = e.target.value.toLowerCase();
        const rol = localStorage.getItem("rol");
        const tarjetas = document.querySelectorAll("#product-list .product-card");

        tarjetas.forEach(card => {
            const nombre = card.dataset.nombre.toLowerCase();
            const codigo = card.dataset.codigo.toLowerCase();
            const coincide =
                rol === "admin"
                    ? nombre.includes(termino) || codigo.includes(termino)
                    : nombre.includes(termino);
            card.style.display = coincide ? "block" : "none";
        });
    });
}

function vaciarCarrito() {
    if (confirm("¿Estás seguro de que deseas vaciar el carrito?")) {
        localStorage.removeItem("carrito");
        location.reload();
    }
}