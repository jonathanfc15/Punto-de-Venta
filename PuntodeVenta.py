import hashlib
import hmac
import os
import sqlite3
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tienda.db")
IVA = 0
NOMBRE_TIENDA = "TIENDA"

# Pestañas permitidas por rol
PERMISOS = {
    "Administrador": ["Ventas", "Historial", "Inventario", "Clientes", "Usuarios"],
    "Vendedor": ["Ventas", "Historial", "Clientes"],
    "Almacenista": ["Inventario"],
}

# Colores
AZUL_CLARO = "#b3ebf2"
AZUL_BORDE = "#5086c1"
ROSA = "#d9a5a0"


# Base de datos
def hash_pw(password, salt=None):
    salt = salt or os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000).hex()
    return f"{salt}${h}"


def verificar_pw(password, guardado):
    salt, _ = guardado.split("$")
    return hmac.compare_digest(hash_pw(password, salt), guardado)


def conectar():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def iniciar_db():
    con = conectar()
    con.executescript(
        """
    CREATE TABLE IF NOT EXISTS usuarios(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            contrasena TEXT NOT NULL,
            rol TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS clientes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            telefono TEXT,
            correo TEXT,
            direccion TEXT
        );
        CREATE TABLE IF NOT EXISTS articulos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            tipo TEXT,
            cantidad INTEGER NOT NULL DEFAULT 0,
            precio REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS ventas(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            cliente_id INTEGER REFERENCES clientes(id),
            vendedor TEXT NOT NULL,
            subtotal REAL NOT NULL,
            iva REAL NOT NULL,
            total REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS detalle_venta(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id INTEGER NOT NULL REFERENCES ventas(id),
            articulo_id INTEGER NOT NULL REFERENCES articulos(id),
            cantidad INTEGER NOT NULL,
            precio_unitario REAL NOT NULL,
            importe REAL NOT NULL
        );
"""
    )
    if con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0:
        for u, p, r in [("admin", "admin123", "Administrador"),
                        ("vendedor", "vendedor123", "Vendedor"),
                        ("almacen", "almacen123", "Almacenista")]:
            con.execute("INSERT INTO usuarios(usuario, contrasena, rol) VALUES (?,?,?)",
                        (u, hash_pw(p), r))
    con.commit()
    con.close()


# Ticket
def generar_ticket(venta_id):
    con = conectar()
    v = con.execute(
        """SELECT v.id, v.fecha, COALESCE(c.nombre,'Público en general'), v.vendedor,
                  v.subtotal, v.iva, v.total
           FROM ventas v LEFT JOIN clientes c ON c.id = v.cliente_id
           WHERE v.id = ?""", (venta_id,)).fetchone()
    det = con.execute(
        """SELECT a.nombre, d.cantidad, d.precio_unitario, d.importe
           FROM detalle_venta d JOIN articulos a ON a.id = d.articulo_id
           WHERE d.venta_id = ?""", (venta_id,)).fetchall()
    con.close()

    w = 44
    L = []
    L.append(NOMBRE_TIENDA.center(w))
    L.append("NOTA DE VENTA".center(w))
    L.append("=" * w)
    L.append(f"Ticket No.: {v[0]:06d}")
    L.append(f"Fecha     : {v[1]}")
    L.append(f"Cliente   : {v[2]}")
    L.append(f"Atendió   : {v[3]}")
    L.append("-" * w)
    L.append(f"{'Producto':<20}{'Cant':>4}{'P.Unit':>9}{'Importe':>11}")
    L.append("-" * w)
    for nombre, cant, pu, imp in det:
        L.append(f"{nombre[:20]:<20}{cant:>4}{pu:>9.2f}{imp:>11.2f}")
    L.append("-" * w)
    L.append(f"{'Subtotal:':>33}{v[4]:>11.2f}")
    L.append(f"{'IVA (16%):':>33}{v[5]:>11.2f}")
    L.append(f"{'TOTAL:':>33}{v[6]:>11.2f}")
    L.append("=" * w)
    L.append("¡Gracias por su compra!".center(w))
    return "\n".join(L)


def mostrar_ticket(master, venta_id):
    texto = generar_ticket(venta_id)
    win = tk.Toplevel(master)
    win.title(f"Ticket {venta_id:06d}")
    win.configure(bg=AZUL_CLARO)
    txt = tk.Text(win, font=("Courier New", 10), width=46, height=min(30, texto.count("\n") + 2))
    txt.insert("1.0", texto)
    txt.configure(state="disabled")
    txt.pack(padx=10, pady=10)

    def guardar():
        ruta = filedialog.asksaveasfilename(
            defaultextension=".txt", initialfile=f"ticket_{venta_id:06d}.txt",
            filetypes=[("Texto", "*.txt")])
        if ruta:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(texto)
            messagebox.showinfo("Ticket", "Ticket guardado.", parent=win)

    bar = ttk.Frame(win)
    bar.pack(pady=(0, 10))
    ttk.Button(bar, text="Guardar como .txt", command=guardar).pack(side="left", padx=4)
    ttk.Button(bar, text="Cerrar", command=win.destroy).pack(side="left", padx=4)


# Formulario CRUD genérico (Inventario y Clientes)
class Crud(ttk.Frame):

    def __init__(self, master, tabla, campos, titulo_resumen):
        super().__init__(master, padding=8)
        self.tabla = tabla
        self.campos = campos
        self.vars = {c: tk.StringVar() for c, _, _ in campos}
        self.id_var = tk.StringVar()
        self.resumen = tk.StringVar(value="(ninguno)")

        # Izquierda: tabla + resumen
        izq = ttk.Frame(self)
        izq.pack(side="left", fill="both", expand=True)

        cols = ["id"] + [c for c, _, _ in campos]
        self.tree = ttk.Treeview(izq, columns=cols, show="headings", height=13, selectmode="browse")
        for c in cols:
            self.tree.heading(c, text=c.upper())
            self.tree.column(c, width=50 if c == "id" else 110, anchor="center")
        sb = ttk.Scrollbar(izq, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="top", fill="both", expand=True)
        sb.place(relx=1.0, rely=0, relheight=0.8, anchor="ne")
        self.tree.bind("<<TreeviewSelect>>", self.seleccionar)

        res = ttk.LabelFrame(izq, text=titulo_resumen, padding=8)
        res.pack(fill="x", pady=(8, 0))
        ttk.Label(res, textvariable=self.resumen).pack(anchor="w")

        # Derecha: opciones
        der = ttk.LabelFrame(self, text="Opciones", padding=10)
        der.pack(side="right", fill="y", padx=(8, 0))
        ttk.Label(der, text="ID:").pack(anchor="w")
        ttk.Entry(der, textvariable=self.id_var, state="readonly", width=28).pack(pady=(0, 6))
        for c, etiqueta, _ in campos:
            ttk.Label(der, text=etiqueta + ":").pack(anchor="w")
            ttk.Entry(der, textvariable=self.vars[c], width=28).pack(pady=(0, 6))
        for texto, cmd in [("Agregar", self.agregar), ("Actualizar", self.actualizar),
                           ("Eliminar", self.eliminar), ("Limpiar", self.limpiar)]:
            ttk.Button(der, text=texto, command=cmd).pack(fill="x", pady=2)

        self.refrescar()

    # utilidades
    def _fmt(self, valor, tipo):
        return f"{valor:.2f}" if tipo is float and valor is not None else ("" if valor is None else valor)

    def refrescar(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        con = conectar()
        cols = ", ".join(c for c, _, _ in self.campos)
        for fila in con.execute(f"SELECT id, {cols} FROM {self.tabla} ORDER BY id"):
            vals = [fila[0]] + [self._fmt(v, t) for v, (_, _, t) in zip(fila[1:], self.campos)]
            self.tree.insert("", "end", iid=str(fila[0]), values=vals)
        con.close()

    def seleccionar(self, _e=None):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0], "values")
        self.id_var.set(vals[0])
        for (c, _, _), v in zip(self.campos, vals[1:]):
            self.vars[c].set(v)
        self.resumen.set("   |   ".join(f"{e}: {v}" for (_, e, _), v in zip(self.campos, vals[1:])))

    def limpiar(self):
        self.id_var.set("")
        for v in self.vars.values():
            v.set("")
        self.resumen.set("(ninguno)")
        self.tree.selection_remove(self.tree.selection())

    def leer(self):
        datos = []
        for c, etiqueta, tipo in self.campos:
            v = self.vars[c].get().strip()
            if c == "nombre" and not v:
                messagebox.showwarning("Datos incompletos", "El nombre es obligatorio.")
                return None
            if tipo in (int, float):
                try:
                    n = tipo(v)
                    if n < 0:
                        raise ValueError
                except ValueError:
                    messagebox.showwarning("Dato inválido", f"'{etiqueta}' debe ser un número válido y no negativo.")
                    return None
                datos.append(n)
            else:
                datos.append(v)
        return datos

    def agregar(self):
        datos = self.leer()
        if datos is None:
            return
        cols = [c for c, _, _ in self.campos]
        con = conectar()
        con.execute(f"INSERT INTO {self.tabla}({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", datos)
        con.commit()
        con.close()
        self.limpiar()
        self.refrescar()

    def actualizar(self):
        if not self.id_var.get():
            messagebox.showinfo("Actualizar", "Seleccione un registro de la tabla.")
            return
        datos = self.leer()
        if datos is None:
            return
        sets = ", ".join(f"{c}=?" for c, _, _ in self.campos)
        con = conectar()
        con.execute(f"UPDATE {self.tabla} SET {sets} WHERE id=?", datos + [int(self.id_var.get())])
        con.commit()
        con.close()
        self.refrescar()
        self.tree.selection_set(self.id_var.get())

    def eliminar(self):
        if not self.id_var.get():
            messagebox.showinfo("Eliminar", "Seleccione un registro de la tabla.")
            return
        if not messagebox.askyesno("Eliminar", "¿Eliminar el registro seleccionado?"):
            return
        con = conectar()
        try:
            con.execute(f"DELETE FROM {self.tabla} WHERE id=?", (int(self.id_var.get()),))
            con.commit()
        except sqlite3.IntegrityError:
            messagebox.showerror("No se puede eliminar", "El registro está relacionado con ventas ya realizadas.")
        finally:
            con.close()
        self.limpiar()
        self.refrescar()


# Ventas
class Ventas(ttk.Frame):
    def __init__(self, master, usuario):
        super().__init__(master, padding=8)
        self.usuario = usuario
        self.carrito = {}      # articulo_id -> [nombre, cantidad, precio]
        self.arts = {}         # articulo_id -> (nombre, stock, precio)

        sup = ttk.LabelFrame(self, text="Datos de la venta", padding=8)
        sup.pack(fill="x")

        ttk.Label(sup, text="Cliente:").grid(row=0, column=0, sticky="w")
        self.cb_cliente = ttk.Combobox(sup, state="readonly", width=40)
        self.cb_cliente.grid(row=0, column=1, padx=6, pady=3, sticky="w")

        ttk.Label(sup, text="Artículo:").grid(row=1, column=0, sticky="w")
        self.cb_art = ttk.Combobox(sup, state="readonly", width=60)
        self.cb_art.grid(row=1, column=1, padx=6, pady=3, sticky="w")

        ttk.Label(sup, text="Cantidad:").grid(row=1, column=2, sticky="e")
        self.sp_cant = ttk.Spinbox(sup, from_=1, to=9999, width=6)
        self.sp_cant.set(1)
        self.sp_cant.grid(row=1, column=3, padx=6)
        ttk.Button(sup, text="Agregar al ticket", command=self.agregar).grid(row=1, column=4, padx=4)

        cols = ("producto", "cantidad", "precio", "importe")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=10)
        for c, w in zip(cols, (300, 90, 110, 120)):
            self.tree.heading(c, text=c.capitalize() if c != "precio" else "Precio unitario")
            self.tree.column(c, width=w, anchor="center" if c != "producto" else "w")
        self.tree.pack(fill="both", expand=True, pady=8)

        inf = ttk.Frame(self)
        inf.pack(fill="x")
        bt = ttk.Frame(inf)
        bt.pack(side="left")
        ttk.Button(bt, text="Quitar seleccionado", command=self.quitar).pack(side="left", padx=2)
        ttk.Button(bt, text="Cancelar venta", command=self.cancelar).pack(side="left", padx=2)
        ttk.Button(bt, text="Finalizar venta", command=self.finalizar).pack(side="left", padx=2)

        tot = ttk.Frame(inf)
        tot.pack(side="right")
        self.lbl_sub = tk.StringVar(value="0.00")
        self.lbl_iva = tk.StringVar(value="0.00")
        self.lbl_tot = tk.StringVar(value="0.00")
        for i, (t, v) in enumerate((("Subtotal:", self.lbl_sub), ("IVA (16%):", self.lbl_iva), ("Total:", self.lbl_tot))):
            ttk.Label(tot, text=t, font=("Segoe UI", 10, "bold")).grid(row=i, column=0, sticky="e")
            ttk.Label(tot, textvariable=v, width=12, anchor="e").grid(row=i, column=1)

        self.refrescar()

    def refrescar(self):
        con = conectar()
        self.clientes = {0: "Público en general"}
        for i, n in con.execute("SELECT id, nombre FROM clientes ORDER BY nombre"):
            self.clientes[i] = n
        self.arts = {i: (n, c, p) for i, n, c, p in
                     con.execute("SELECT id, nombre, cantidad, precio FROM articulos ORDER BY nombre")}
        con.close()
        self.cb_cliente["values"] = [f"{i} - {n}" for i, n in self.clientes.items()]
        if not self.cb_cliente.get():
            self.cb_cliente.current(0)
        self.cb_art["values"] = [f"{i} - {n}  (${p:.2f}, existencia: {c})" for i, (n, c, p) in self.arts.items()]

    def agregar(self):
        if not self.cb_art.get():
            messagebox.showinfo("Venta", "Seleccione un artículo.")
            return
        try:
            cant = int(self.sp_cant.get())
            if cant <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Venta", "La cantidad debe ser un entero mayor a cero.")
            return
        aid = int(self.cb_art.get().split(" - ")[0])
        nombre, stock, precio = self.arts[aid]
        ya = self.carrito.get(aid, [nombre, 0, precio])[1]
        if ya + cant > stock:
            messagebox.showwarning("Existencia insuficiente",
                                   f"Solo hay {stock} pieza(s) de '{nombre}' (ya agregadas: {ya}).")
            return
        self.carrito[aid] = [nombre, ya + cant, precio]
        self.pintar()

    def quitar(self):
        sel = self.tree.selection()
        if sel:
            self.carrito.pop(int(sel[0]), None)
            self.pintar()

    def cancelar(self):
        self.carrito.clear()
        self.pintar()

    def pintar(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        sub = 0.0
        for aid, (n, c, p) in self.carrito.items():
            imp = c * p
            sub += imp
            self.tree.insert("", "end", iid=str(aid), values=(n, c, f"{p:.2f}", f"{imp:.2f}"))
        iva = round(sub * IVA, 2)
        self.lbl_sub.set(f"{sub:.2f}")
        self.lbl_iva.set(f"{iva:.2f}")
        self.lbl_tot.set(f"{sub + iva:.2f}")

    def finalizar(self):
        if not self.carrito:
            messagebox.showinfo("Venta", "El ticket está vacío.")
            return
        cliente_id = int(self.cb_cliente.get().split(" - ")[0]) or None
        con = conectar()
        try:
            # Revalidar existencias
            for aid, (n, c, p) in self.carrito.items():
                stock = con.execute("SELECT cantidad FROM articulos WHERE id=?", (aid,)).fetchone()
                if not stock or stock[0] < c:
                    messagebox.showerror("Existencia insuficiente", f"'{n}' ya no tiene existencia suficiente.")
                    return
            sub = round(sum(c * p for _, c, p in self.carrito.values()), 2)
            iva = round(sub * IVA, 2)
            total = round(sub + iva, 2)
            cur = con.execute(
                "INSERT INTO ventas(fecha, cliente_id, vendedor, subtotal, iva, total) VALUES (?,?,?,?,?,?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), cliente_id, self.usuario, sub, iva, total))
            vid = cur.lastrowid
            for aid, (n, c, p) in self.carrito.items():
                con.execute(
                    "INSERT INTO detalle_venta(venta_id, articulo_id, cantidad, precio_unitario, importe) "
                    "VALUES (?,?,?,?,?)", (vid, aid, c, p, round(c * p, 2)))
                con.execute("UPDATE articulos SET cantidad = cantidad - ? WHERE id=?", (c, aid))
            con.commit()
        except Exception as e:
            con.rollback()
            messagebox.showerror("Error", f"No se pudo registrar la venta:\n{e}")
            return
        finally:
            con.close()
        self.carrito.clear()
        self.pintar()
        self.refrescar()
        mostrar_ticket(self, vid)


# Historial
class Historial(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=8)
        ttk.Label(self, text="Doble clic en una venta para ver su ticket.").pack(anchor="w")
        cols = ("ticket", "fecha", "cliente", "vendedor", "total")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=16)
        for c, w in zip(cols, (80, 160, 220, 120, 110)):
            self.tree.heading(c, text=c.capitalize())
            self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill="both", expand=True, pady=6)
        self.tree.bind("<Double-1>", self.abrir)
        self.refrescar()

    def refrescar(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        con = conectar()
        for v in con.execute(
                """SELECT v.id, v.fecha, COALESCE(c.nombre,'Público en general'), v.vendedor, v.total
                   FROM ventas v LEFT JOIN clientes c ON c.id=v.cliente_id ORDER BY v.id DESC"""):
            self.tree.insert("", "end", iid=str(v[0]), values=(f"{v[0]:06d}", v[1], v[2], v[3], f"{v[4]:.2f}"))
        con.close()

    def abrir(self, _e=None):
        sel = self.tree.selection()
        if sel:
            mostrar_ticket(self, int(sel[0]))


# Usuarios (solo administrador)
class Usuarios(ttk.Frame):
    def __init__(self, master, usuario_actual):
        super().__init__(master, padding=8)
        self.actual = usuario_actual
        self.v_user, self.v_pw, self.v_rol = tk.StringVar(), tk.StringVar(), tk.StringVar(value="Vendedor")

        self.tree = ttk.Treeview(self, columns=("id", "usuario", "rol"), show="headings", height=13)
        for c, w in (("id", 50), ("usuario", 180), ("rol", 150)):
            self.tree.heading(c, text=c.capitalize())
            self.tree.column(c, width=w, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.seleccionar)

        der = ttk.LabelFrame(self, text="Opciones", padding=10)
        der.pack(side="right", fill="y", padx=(8, 0))
        ttk.Label(der, text="Usuario:").pack(anchor="w")
        ttk.Entry(der, textvariable=self.v_user, width=26).pack(pady=(0, 6))
        ttk.Label(der, text="Contraseña:").pack(anchor="w")
        ttk.Entry(der, textvariable=self.v_pw, show="•", width=26).pack(pady=(0, 6))
        ttk.Label(der, text="Rol:").pack(anchor="w")
        ttk.Combobox(der, textvariable=self.v_rol, values=list(PERMISOS), state="readonly", width=23).pack(pady=(0, 8))
        ttk.Button(der, text="Agregar usuario", command=self.agregar).pack(fill="x", pady=2)
        ttk.Button(der, text="Cambiar contraseña / rol", command=self.actualizar).pack(fill="x", pady=2)
        ttk.Button(der, text="Eliminar", command=self.eliminar).pack(fill="x", pady=2)
        self.refrescar()

    def refrescar(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        con = conectar()
        for r in con.execute("SELECT id, usuario, rol FROM usuarios ORDER BY id"):
            self.tree.insert("", "end", iid=str(r[0]), values=r)
        con.close()

    def seleccionar(self, _e=None):
        sel = self.tree.selection()
        if sel:
            _, u, r = self.tree.item(sel[0], "values")
            self.v_user.set(u)
            self.v_rol.set(r)
            self.v_pw.set("")

    def agregar(self):
        u, p = self.v_user.get().strip(), self.v_pw.get()
        if not u or len(p) < 4:
            messagebox.showwarning("Usuarios", "Indique usuario y una contraseña de al menos 4 caracteres.")
            return
        con = conectar()
        try:
            con.execute("INSERT INTO usuarios(usuario, contrasena, rol) VALUES (?,?,?)",
                        (u, hash_pw(p), self.v_rol.get()))
            con.commit()
        except sqlite3.IntegrityError:
            messagebox.showerror("Usuarios", "Ese usuario ya existe.")
        finally:
            con.close()
        self.v_pw.set("")
        self.refrescar()

    def actualizar(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Usuarios", "Seleccione un usuario.")
            return
        con = conectar()
        if self.v_pw.get():
            if len(self.v_pw.get()) < 4:
                messagebox.showwarning("Usuarios", "La contraseña debe tener al menos 4 caracteres.")
                con.close()
                return
            con.execute("UPDATE usuarios SET contrasena=?, rol=? WHERE id=?",
                        (hash_pw(self.v_pw.get()), self.v_rol.get(), int(sel[0])))
        else:
            con.execute("UPDATE usuarios SET rol=? WHERE id=?", (self.v_rol.get(), int(sel[0])))
        con.commit()
        con.close()
        self.v_pw.set("")
        self.refrescar()

    def eliminar(self):
        sel = self.tree.selection()
        if not sel:
            return
        _, u, _ = self.tree.item(sel[0], "values")
        if u == self.actual:
            messagebox.showwarning("Usuarios", "No puede eliminar su propio usuario.")
            return
        if messagebox.askyesno("Usuarios", f"¿Eliminar al usuario '{u}'?"):
            con = conectar()
            con.execute("DELETE FROM usuarios WHERE id=?", (int(sel[0]),))
            con.commit()
            con.close()
            self.refrescar()

# Ventana de inicio de sesión
class Login(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tienda - Inicio de sesión")
        self.resizable(False, False)
        self.configure(bg=AZUL_CLARO)
        self.usuario = None
        self.rol = None

        estilo = ttk.Style(self)
        estilo.theme_use("clam")
        estilo.configure("TFrame", background=AZUL_CLARO)
        estilo.configure("TLabel", background=AZUL_CLARO)
        estilo.configure("TLabelframe", background=AZUL_CLARO)
        estilo.configure("TLabelframe.Label", background=AZUL_CLARO, font=("Segoe UI", 10, "bold"))

        f = ttk.Frame(self, padding=25)
        f.pack()
        ttk.Label(f, text="🛒  TIENDA", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=2, pady=(0, 15))
        ttk.Label(f, text="Usuario:", font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="e", pady=4)
        self.e_user = ttk.Entry(f, width=26)
        self.e_user.grid(row=1, column=1, padx=8)
        ttk.Label(f, text="Contraseña:", font=("Segoe UI", 10, "bold")).grid(row=2, column=0, sticky="e", pady=4)
        self.e_pw = ttk.Entry(f, width=26, show="•")
        self.e_pw.grid(row=2, column=1, padx=8)
        ttk.Button(f, text="🔒 Iniciar sesión", command=self.entrar).grid(row=3, column=0, columnspan=2, pady=(15, 0))
        self.e_user.focus()
        self.bind("<Return>", lambda e: self.entrar())

    def entrar(self):
        u, p = self.e_user.get().strip(), self.e_pw.get()
        con = conectar()
        fila = con.execute("SELECT contrasena, rol FROM usuarios WHERE usuario=?", (u,)).fetchone()
        con.close()
        if fila and verificar_pw(p, fila[0]):
            self.usuario, self.rol = u, fila[1]
            self.destroy()
        else:
            messagebox.showerror("Acceso denegado", "Usuario o contraseña incorrectos.")
            self.e_pw.delete(0, "end")


# Ventana principal
class App(tk.Tk):
    def __init__(self, usuario, rol):
        super().__init__()
        self.title(f"Tienda - {usuario} ({rol})")
        self.geometry("1000x600")
        self.configure(bg=AZUL_CLARO)
        self.cerrar_sesion = False

        estilo = ttk.Style(self)
        estilo.theme_use("clam")
        for w in ("TFrame", "TLabel", "TLabelframe", "TNotebook"):
            estilo.configure(w, background=AZUL_CLARO)
        estilo.configure("TLabelframe.Label", background=AZUL_CLARO, font=("Segoe UI", 10, "bold"))
        estilo.configure("TNotebook.Tab", padding=(14, 5))
        estilo.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

        # Menú
        menu = tk.Menu(self)
        m_arch = tk.Menu(menu, tearoff=0)
        m_arch.add_command(label="Cerrar sesión", command=self.logout)
        m_arch.add_separator()
        m_arch.add_command(label="Salir", command=self.destroy)
        menu.add_cascade(label="Archivo", menu=m_arch)
        self.config(menu=menu)

        # Pestañas según rol
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=6, pady=6)
        constructores = {
            "Ventas": lambda: Ventas(self.nb, usuario),
            "Historial": lambda: Historial(self.nb),
            "Inventario": lambda: Crud(self.nb, "articulos", [
                ("nombre", "Nombre", str), ("tipo", "Tipo", str),
                ("cantidad", "Cantidad", int), ("precio", "Precio", float)], "Artículo seleccionado"),
            "Clientes": lambda: Crud(self.nb, "clientes", [
                ("nombre", "Nombre", str), ("telefono", "Teléfono", str),
                ("correo", "Correo", str), ("direccion", "Dirección", str)], "Cliente seleccionado"),
            "Usuarios": lambda: Usuarios(self.nb, usuario),
        }
        for nombre in PERMISOS[rol]:
            self.nb.add(constructores[nombre](), text=nombre)
        self.nb.bind("<<NotebookTabChanged>>", self.al_cambiar_pestana)

        self.status = tk.StringVar(value=f"Sesión: {usuario}   |   Rol: {rol}")
        tk.Label(self, textvariable=self.status, anchor="w", bg=AZUL_BORDE).pack(fill="x", side="bottom")

    def al_cambiar_pestana(self, _e=None):
        frame = self.nametowidget(self.nb.select())
        if hasattr(frame, "refrescar"):
            frame.refrescar()

    def logout(self):
        self.cerrar_sesion = True
        self.destroy()


def main():
    iniciar_db()
    while True:
        login = Login()
        login.mainloop()
        if not login.usuario:
            break
        app = App(login.usuario, login.rol)
        app.mainloop()
        if not app.cerrar_sesion:
            break


if __name__ == "__main__":
    main()
